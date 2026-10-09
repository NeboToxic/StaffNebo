import json
from pathlib import Path
from PyQt5.QtCore import pyqtSignal
from threads.base import StoppableThread
from core import history
from domain.notifier import SendPayload, TelegramNotifier, VkNotifier
from domain.events import PunishmentType


class DeliveryThread(StoppableThread):
    finished_signal = pyqtSignal(bool,str)

    def __init__(self, record_id, without_photo=False):
        super().__init__()
        self.record_id=record_id
        self.without_photo=without_photo

    def run(self):
        if self.should_stop or not history.claim(self.record_id):
            self.finished_signal.emit(False,'Событие уже отправлено или обрабатывается')
            return
        try:
            row=history.get_event(self.record_id);settings=history.event_settings(row)
            data=json.loads(row['payload_json'])
            if self.without_photo:
                data['needs_photo']=False
                history.omit_photo(self.record_id)
            filename=row['screenshot_path']
            if data.get('needs_photo') and (not filename or not Path(filename).is_file()):
                raise RuntimeError('Скриншот отсутствует. Повторите отправку без фото; восстановить прежний кадр нельзя.')
            if row['event_type']=='screenshot':
                if not filename or not Path(filename).is_file():raise RuntimeError('Файл скриншота отсутствует')
                if settings.platform=='telegram':
                    ok,msg=TelegramNotifier().send_screenshot(filename,settings.bot_id,settings.chat_id,
                        should_stop=lambda:self.should_stop,settings=settings)
                else:
                    ok,msg=VkNotifier().send_screenshot(filename,settings.vk_user_id,
                        should_stop=lambda:self.should_stop,settings=settings,delivery_id=row['delivery_id'])
            else:
                allowed=SendPayload.__dataclass_fields__
                payload=SendPayload(**{k:v for k,v in data.items() if k in allowed})
                payload.event_type=PunishmentType(payload.event_type)
                payload.settings_override=settings;payload.record_id=row['id'];payload.delivery_id=row['delivery_id']
                if settings.platform=='telegram':ok,msg=TelegramNotifier().send_punishment(payload,lambda:self.should_stop)
                else:ok,msg=VkNotifier().send_punishment(payload,settings.vk_user_id,lambda:self.should_stop)
            if self.should_stop and not ok:msg='Отправка отменена. Можно повторить из центра уведомлений.'
            history.finish(self.record_id,ok,msg)
        except Exception as exc:
            ok=False;msg=str(exc)
            history.finish(self.record_id,False,msg)
        self.finished_signal.emit(ok,msg)
