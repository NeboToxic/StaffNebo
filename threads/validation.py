from PyQt5.QtCore import pyqtSignal
from threads.base import StoppableThread


class ValidationThread(StoppableThread):

    finished = pyqtSignal(bool, str)

    def __init__(self, validation_data: dict, old_bot_id: str, old_chat_id: str,
                 verified_bot_id: str, verified_chat_id: str, parent=None):
        super().__init__(parent)
        self.validation_data = validation_data
        self.old_bot_id = old_bot_id
        self.old_chat_id = old_chat_id
        self.verified_bot_id = verified_bot_id
        self.verified_chat_id = verified_chat_id
        self.owner = parent

    def run(self):
        if self.should_stop:
            return

        try:
            bot_id = self.validation_data['bot_id']
            chat_id = self.validation_data['chat_id']
            nick = self.validation_data['nick']

            if self.should_stop:
                return

            if not self._validate_nick(nick):
                if not self.should_stop:
                    self.finished.emit(False, "Ошибка авторизации: неверный ник")
                return

            if self.should_stop:
                return

            is_telegram = self.validation_data.get('platform', 'Telegram') in ('Telegram', 'telegram')
            if is_telegram and self._need_bot_check(bot_id, chat_id) and not self.should_stop:
                need_message = True
                result = self.owner.check_bot_and_chat(bot_id, chat_id, need_message)

                if not result["success"]:
                    if not self.should_stop:
                        self.finished.emit(False, result["message"])
                    return

                self.owner.save_verification_info(bot_id, chat_id)
            elif not self.should_stop:
                print("Bot ID и Chat ID не изменились, повторная проверка не требуется")

            if not self.should_stop:
                self.finished.emit(True, "Все проверки пройдены успешно")

        except Exception as e:
            if not self.should_stop:
                self.finished.emit(False, f"Ошибка при проверке: {str(e)}")

    def _need_bot_check(self, bot_id: str, chat_id: str) -> bool:
        if bot_id != self.old_bot_id or chat_id != self.old_chat_id:
            return True
        if self.verified_bot_id is None or self.verified_chat_id is None:
            return True
        if bot_id != self.verified_bot_id or chat_id != self.verified_chat_id:
            return True
        return False

    def _validate_nick(self, nick: str) -> bool:
        try:
            return bool(nick and nick.strip())
        except Exception:
            return False