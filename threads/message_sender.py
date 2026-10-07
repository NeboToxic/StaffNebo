from PyQt5.QtCore import QThread, pyqtSignal

import core.globals as g
from domain.events import PunishmentType
from domain.notifier import SendPayload, TelegramNotifier, VkNotifier


class MessageSenderThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, send_type, platform_name, *args, payload: SendPayload = None, vk_user_id: str = ''):
        super().__init__()
        self.send_type = send_type
        self.platform = platform_name
        self.args = args
        self.payload = payload
        self.vk_user_id = vk_user_id or ''
        self.should_stop = False
        self._tg = TelegramNotifier()
        self._vk = VkNotifier()

    def stop(self):
        self.should_stop = True
        if self.isRunning():
            self.wait(2000)

    def _stopped(self):
        return self.should_stop

    def run(self):
        try:
            if self.send_type == 'screenshot':
                filename = self.args[0] if self.args else None
                if not filename:
                    self.finished_signal.emit(False, '[ERROR] Нет файла скриншота')
                    return
                if self.platform == 'telegram':
                    ok, msg = self._tg.send_screenshot(
                        filename, g.bot_id, g.chat_id, should_stop=self._stopped
                    )
                else:
                    ok, msg = self._vk.send_screenshot(
                        filename, self.vk_user_id or g.vk_user_id, should_stop=self._stopped
                    )
                if msg:
                    self.finished_signal.emit(ok, msg)
                return

            payload = self.payload
            if payload is None:
                payload = self._payload_from_legacy_args()

            if self.platform == 'telegram':
                ok, msg = self._tg.send_punishment(payload, should_stop=self._stopped)
            else:
                ok, msg = self._vk.send_punishment(
                    payload,
                    vk_user_id=self.vk_user_id or g.vk_user_id,
                    should_stop=self._stopped,
                )
            if msg:
                self.finished_signal.emit(ok, msg)
        except Exception as e:
            self.finished_signal.emit(False, f'[ERROR] Ошибка отправки: {e}')

    def _payload_from_legacy_args(self) -> SendPayload:
        event_type = PunishmentType(self.send_type)
        if event_type == PunishmentType.KICK:
            vk_uid, user_id, full_nick, nick, reason, dating, timing = self.args
            return SendPayload(
                event_type=event_type,
                user_id=str(user_id),
                moderator_html=full_nick,
                target_html=nick,
                reason=reason,
                dating=dating,
                timing=timing,
            )
        vk_uid, user_id, full_nick, photoid, nick, reason, dating, timing = self.args
        return SendPayload(
            event_type=event_type,
            user_id=str(user_id),
            moderator_html=full_nick,
            target_html=nick,
            reason=reason,
            dating=dating,
            timing=timing,
            photoid=str(photoid),
        )
