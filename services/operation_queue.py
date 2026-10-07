import time as tm

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal

import core.globals as g
from domain.events import ModerationEvent, PunishmentType
from domain.notifier import SendPayload
from threads.action_threads import CaptureThread, KickPrepareThread
from threads.message_sender import MessageSenderThread


class OperationQueue(QObject):
    log_signal = pyqtSignal(str)
    sound_signal = pyqtSignal()
    stats_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)

    def __init__(self, parent=None, processing_delay: float = 1.5):
        super().__init__(parent)
        self.processing_delay = processing_delay
        self._queue = []
        self._busy = False
        self._worker = None
        self._sender = None
        self._recent_keys = {}
        self._dedupe_sec = 3.0
        self._prepare_handled = False

    @staticmethod
    def _event_key(event: ModerationEvent) -> str:
        return f'{event.event_type.value}|{event.target_html}|{event.reason}|{event.line}'

    @property
    def is_busy(self) -> bool:
        return self._busy

    def enqueue(self, event: ModerationEvent):
        key = self._event_key(event)
        now = tm.monotonic()
        last = self._recent_keys.get(key)
        if last is not None and now - last < self._dedupe_sec:
            return
        self._recent_keys[key] = now
        # Drop stale keys so the map does not grow forever.
        self._recent_keys = {
            k: ts for k, ts in self._recent_keys.items() if now - ts < self._dedupe_sec
        }

        self._queue.append(event)
        if not self._busy:
            self._process_next()

    def stop(self):
        for worker in (self._worker, self._sender):
            if worker is not None:
                try:
                    worker.stop()
                except Exception:
                    pass

    def _process_next(self):
        if self._busy or not self._queue:
            return
        event = self._queue.pop(0)
        self._busy = True
        QTimer.singleShot(int(self.processing_delay * 1000), lambda: self._start(event))

    def _start(self, event: ModerationEvent):
        try:
            self._prepare_handled = False
            if event.needs_screenshot:
                self._worker = CaptureThread(event)
            else:
                self._worker = KickPrepareThread(event)
            self._worker.finished_signal.connect(
                self._on_prepared, Qt.UniqueConnection
            )
            self._worker.start()
        except Exception as e:
            self.log_signal.emit(f'[ERROR] Ошибка при запуске операции {event.event_type.value}: {e}')
            self._finish_and_continue()

    def _on_prepared(self, payload: SendPayload):
        if self._prepare_handled:
            return
        self._prepare_handled = True

        event_key = payload.event_type.value
        if payload.event_type == PunishmentType.MUTE:
            g.all_mutes += 1
        elif payload.event_type == PunishmentType.WARN:
            g.all_warns += 1
        elif payload.event_type == PunishmentType.KICK:
            g.all_kicks += 1

        self.stats_signal.emit(event_key)

        if g.using_sounds_in_program and payload.event_type != PunishmentType.KICK:
            self.sound_signal.emit()

        self._sender = MessageSenderThread(
            event_key,
            g.platform,
            payload=payload,
            vk_user_id=g.vk_user_id,
        )
        self._sender.finished_signal.connect(
            lambda ok, msg, et=event_key: self._on_sent(ok, msg, et)
        )
        self._sender.start()

    def _on_sent(self, success: bool, message: str, operation_type: str):
        self.log_signal.emit(message)
        if not success:
            self.warning_signal.emit(
                f'[WARNING] Отправка {operation_type} завершилась с ошибкой'
            )
        self._finish_and_continue()

    def _finish_and_continue(self):
        self._busy = False
        self._worker = None
        self._prepare_handled = False
        QTimer.singleShot(500, self._process_next)
