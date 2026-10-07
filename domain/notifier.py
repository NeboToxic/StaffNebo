import os
import re
import time as tm
from dataclasses import dataclass
from typing import Optional

import telebot

import core.globals as g
from core.paths import screenshot_path
from core.settings import load_settings
from domain.events import LABELS, PunishmentType
from domain.worker_client import send_vk_message


@dataclass
class SendPayload:
    event_type: PunishmentType
    user_id: str
    moderator_html: str
    target_html: str
    reason: str
    dating: str
    timing: str
    photoid: Optional[str] = None


def clean_html(text: str) -> str:
    return re.sub(r'<.*?>', '', text or '')


def build_telegram_user_text(payload: SendPayload) -> str:
    label = LABELS[payload.event_type]['ru']
    return (
        f'Ник: {payload.target_html}\n'
        f'Тип наказания: {label}\n'
        f'Причина: {payload.reason}\n'
        f'Дата: {payload.dating}\n'
        f'Время: {payload.timing}\n\n'
        f'<em>С любовью, NeboProject</em>'
    )


def build_telegram_log_text(payload: SendPayload) -> str:
    label = LABELS[payload.event_type]['ru']
    return (
        f'Блюститель: {payload.moderator_html}\n\n'
        f'Ник: {payload.target_html}\n'
        f'Тип наказания: {label}\n'
        f'Причина: {payload.reason}\n'
        f'Дата: {payload.dating}\n'
        f'Время: {payload.timing}\n\n'
        f'<em>С любовью, NeboProject</em>'
    )


def build_vk_text(payload: SendPayload) -> str:
    title = LABELS[payload.event_type]['vk_title']
    return (
        f'{title}\n\n'
        f'Блюститель: {clean_html(payload.moderator_html)}\n'
        f'Ник: {clean_html(payload.target_html)}\n'
        f'Причина: {payload.reason}\n'
        f'Дата: {payload.dating}\n'
        f'Время: {payload.timing}\n\n'
        f'С любовью, NeboProject'
    )


class TelegramNotifier:
    def send_punishment(self, payload: SendPayload, should_stop=None) -> tuple:
        meta = LABELS[payload.event_type]
        photo_path = screenshot_path(payload.photoid) if payload.photoid else None

        for attempt in range(1, meta['tg_attempts'] + 1):
            if should_stop and should_stop():
                return False, ''
            try:
                bot = telebot.TeleBot(str(g.bot_id))
                chat_id = int(payload.user_id)
                text_main = build_telegram_user_text(payload)
                text_log = build_telegram_log_text(payload)

                if payload.event_type == PunishmentType.KICK:
                    bot.send_message(chat_id, text_main, parse_mode='html')
                else:
                    with open(photo_path, 'rb') as photo_file:
                        bot.send_photo(chat_id, photo_file, text_main, parse_mode='html')
                    os.remove(photo_path)

                return True, meta['sent_tg']
            except Exception as e:
                if attempt == meta['tg_attempts']:
                    return False, f"[ERROR] Не удалось отправить {meta['fail_tg']}: {e}"
                tm.sleep(meta['tg_sleep'])
        return False, f"[ERROR] Не удалось отправить {meta['fail_tg']}"

    def send_screenshot(self, filename: str, bot_token: str, chat: str, should_stop=None) -> tuple:
        for attempt in range(1, 4):
            if should_stop and should_stop():
                return False, ''
            try:
                bot = telebot.TeleBot(str(bot_token))
                with open(filename, 'rb') as photo_file:
                    bot.send_photo(
                        int(chat), photo_file,
                        '<em>С любовью, NeboProject</em>',
                        parse_mode='html',
                    )
                try:
                    os.remove(filename)
                except Exception:
                    pass
                return True, '[SYSTEM] Скриншот отправлен в Telegram'
            except Exception as e:
                if attempt == 3:
                    try:
                        os.remove(filename)
                    except Exception:
                        pass
                    return False, f'[ERROR] Не удалось отправить скриншот в Telegram: {e}'
                tm.sleep(2)
        return False, '[ERROR] Не удалось отправить скриншот в Telegram'


class VkNotifier:
    def _peer_id(self, explicit_vk_id: str = '') -> str:
        if explicit_vk_id:
            return explicit_vk_id
        try:
            return load_settings().vk_user_id or ''
        except Exception as e:
            print(f'[ERROR] Не удалось прочитать vk_user_id: {e}')
            return ''

    def send_punishment(self, payload: SendPayload, vk_user_id: str = '', should_stop=None) -> tuple:
        meta = LABELS[payload.event_type]
        photo_path = screenshot_path(payload.photoid) if payload.photoid else None

        for attempt in range(1, meta['vk_attempts'] + 1):
            if should_stop and should_stop():
                return False, ''
            try:
                peer_id = self._peer_id(vk_user_id)
                photo = None if payload.event_type == PunishmentType.KICK else photo_path
                send_vk_message(load_settings().vk_token, peer_id, build_vk_text(payload), photo)

                if photo_path and os.path.exists(photo_path):
                    os.remove(photo_path)
                return True, meta['sent_vk']
            except Exception as e:
                if attempt == meta['vk_attempts']:
                    return False, f"[ERROR] Не удалось отправить {meta['fail_vk']}: {e}"
                tm.sleep(meta['vk_sleep'])
        return False, f"[ERROR] Не удалось отправить {meta['fail_vk']}"

    def send_screenshot(self, filename: str, vk_user_id: str = '', should_stop=None) -> tuple:
        for attempt in range(1, 4):
            if should_stop and should_stop():
                return False, ''
            try:
                send_vk_message(
                    load_settings().vk_token, self._peer_id(vk_user_id),
                    '📸 Скриншот по запросу\nС любовью, NeboProject',
                    filename,
                )
                try:
                    os.remove(filename)
                except Exception:
                    pass
                return True, '[SYSTEM] Скриншот отправлен во ВКонтакте'
            except Exception as e:
                if attempt == 3:
                    try:
                        os.remove(filename)
                    except Exception:
                        pass
                    return False, f'[ERROR] Не удалось отправить скриншот во ВКонтакте: {e}'
                tm.sleep(2)
        return False, '[ERROR] Не удалось отправить скриншот во ВКонтакте'
