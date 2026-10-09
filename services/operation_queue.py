import time as tm
import datetime
from dataclasses import replace
from core.settings import load_settings
from core import history
from core.paths import screenshot_path
from domain.notifier import SendPayload
from threads.delivery import DeliveryThread
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
import core.globals as g
from domain.events import PunishmentType
from threads.action_threads import CaptureThread, KickPrepareThread
from threads.message_sender import MessageSenderThread


class OperationQueue(QObject):
    log_signal = pyqtSignal(str)
    sound_signal = pyqtSignal()
    stats_signal = pyqtSignal(str)
    warning_signal = pyqtSignal(str)
    capture_visibility = pyqtSignal(bool)
    history_changed = pyqtSignal()

    def __init__(self, parent=None, processing_delay=1.5):
        super().__init__(parent)
        self.processing_delay = processing_delay
        self._queue = []
        self._busy = False
        self._worker = None
        self._sender = None
        self._active_threads = set()
        self._recent_keys = {}
        self._dedupe_sec = 3.0
        self._prepare_handled = False
        self._stopped = False
        self._pending_event = None
        self._record_id = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_pending)

    @staticmethod
    def _event_key(event):
        return f'{event.event_type.value}|{event.target_html}|{event.reason}|{event.line}'

    @property
    def is_busy(self):
        return self._busy

    def enqueue(self, event):
        if self._stopped:
            return
        settings=load_settings()
        kind=event.event_type.value
        enabled=getattr(settings,'notify_'+kind)
        event=replace(event,needs_screenshot=getattr(settings,'photo_'+kind))
        key = self._event_key(event)
        now = tm.monotonic()
        last = self._recent_keys.get(key)
        if last is not None and now - last < self._dedupe_sec:
            return
        self._recent_keys = {k: ts for k, ts in self._recent_keys.items() if now - ts < self._dedupe_sec}
        self._recent_keys[key] = now
        now=datetime.datetime.now().astimezone()
        payload=SendPayload(event.event_type,str(settings.chat_id or '0'),event.moderator_html,event.target_html,
                            event.reason,event.dating or now.strftime('%d.%m.%Y'),event.timing or now.strftime('%H:%M:%S'),
                            needs_photo=event.needs_screenshot)
        record=history.create_event(payload,settings,status='pending' if enabled else 'disabled')
        self.history_changed.emit()
        if not enabled:
            return
        self._queue.append((event,record,settings))
        self._process_next()

    def stop(self):
        self._stopped = True
        self._timer.stop()
        self._pending_event = None
        self._queue.clear()
        for thread in tuple(self._active_threads):
            thread.stop()
        self._busy = False

    def has_running_threads(self):
        return any(t.isRunning() for t in self._active_threads)

    def _track(self, thread):
        self._active_threads.add(thread)
        thread.finished.connect(lambda t=thread: self._release(t))

    def _release(self, thread):
        self._active_threads.discard(thread)
        thread.deleteLater()

    def _process_next(self):
        if self._stopped or self._busy or not self._queue:
            return
        self._pending_event = self._queue.pop(0)
        self._busy = True
        self._timer.start(max(0, int(self.processing_delay * 1000)))

    def _start_pending(self):
        event, self._pending_event = self._pending_event, None
        if event is not None and not self._stopped:
            self._start(*event)

    def _start(self, event, record_id=None, settings=None):
        if self._stopped:
            return
        try:
            self._prepare_handled = False
            self._record_id=record_id
            settings=settings or load_settings()
            if event.needs_screenshot and settings.hide_before_capture:
                self.capture_visibility.emit(True)
            self._worker = CaptureThread(event,settings) if event.needs_screenshot else KickPrepareThread(event,settings)
            self._track(self._worker)
            self._worker.finished_signal.connect(self._on_prepared)
            if event.needs_screenshot:
                self._worker.error_signal.connect(self._on_prepare_error)
            self._worker.start()
        except Exception as exc:
            self._on_prepare_error(f'[ERROR] Ошибка запуска операции: {exc}')

    def _on_prepare_error(self, message):
        self.capture_visibility.emit(False)
        if self._record_id:
            history.finish(self._record_id,False,message)
            self.history_changed.emit()
        if not self._stopped:
            self.log_signal.emit(message)
            self._finish_and_continue()

    def _on_prepared(self, payload):
        self.capture_visibility.emit(False)
        if self._stopped or self._prepare_handled:
            return
        self._prepare_handled = True
        try:
            if payload.event_type == PunishmentType.MUTE:
                g.all_mutes += 1
            elif payload.event_type == PunishmentType.WARN:
                g.all_warns += 1
            elif payload.event_type == PunishmentType.KICK:
                g.all_kicks += 1
            self.stats_signal.emit(payload.event_type.value)
            if g.using_sounds_in_program and payload.event_type != PunishmentType.KICK:
                self.sound_signal.emit()
            if self._record_id:
                history.update_payload(self._record_id,payload,screenshot_path(payload.photoid) if payload.photoid else '')
                self._sender = DeliveryThread(self._record_id)
            else:
                self._sender = MessageSenderThread(payload.event_type.value,g.platform,payload=payload,vk_user_id=g.vk_user_id)
            self._track(self._sender)
            self._sender.finished_signal.connect(self._on_sent)
            self._sender.start()
        except Exception as exc:
            self._on_prepare_error(f'[ERROR] Ошибка подготовки отправки: {exc}')

    def _on_sent(self, success, message):
        if self._stopped:
            return
        self.log_signal.emit(message)
        self.history_changed.emit()
        if not success:
            self.warning_signal.emit('[WARNING] Отправка завершилась с ошибкой; скриншот сохранён.')
        self._finish_and_continue()

    def _finish_and_continue(self):
        self._busy = False
        self._worker = None
        self._sender = None
        self._record_id = None
        self._prepare_handled = False
        self._process_next()
