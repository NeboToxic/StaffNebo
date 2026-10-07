import os
import re
import time as tm

import requests
from dataclasses import dataclass
from typing import Optional

import telebot

import core.globals as g
from core.paths import screenshot_path
from core.settings import load_settings
from core.telegram_proxy import build_proxy_url, requests_proxies, telebot_proxy
from domain.events import LABELS, PunishmentType
from domain.worker_client import send_vk_message


def _telegram_error(exc: Exception, bot_token: str = '') -> str:
    """Return a user-safe Telegram error without exposing the bot token."""
    text = str(exc)
    if bot_token:
        text = text.replace(bot_token, '<TOKEN>')
    text = re.sub(r'(bot)\d{6,}:[A-Za-z0-9_-]+', r'\1<TOKEN>', text)
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return 'Не удалось подключиться к api.telegram.org: превышено время ожидания. Проверьте интернет, VPN/прокси или firewall.'
    if isinstance(exc, requests.exceptions.ConnectionError):
        return 'Не удалось подключиться к Telegram API. Проверьте интернет, VPN/прокси или firewall.'
    if isinstance(exc, requests.exceptions.Timeout):
        return 'Telegram API не ответил вовремя. Проверьте интернет, VPN/прокси или firewall.'
    return text


def _telegram_api_url(token: str, method: str) -> str:
    base = os.getenv('NEBO_TELEGRAM_API_URL', 'https://api.telegram.org').rstrip('/')
    return f'{base}/bot{token}/{method}'


def _send_telegram_photo(filename: str, token: str, chat: str, caption: str, proxy_url=None) -> None:
    # requests respects HTTPS_PROXY/HTTP_PROXY from the environment, which also
    # makes the app usable on PCs where direct access to Telegram is blocked.
    with open(filename, 'rb') as photo_file:
        response = requests.post(
            _telegram_api_url(str(token), 'sendPhoto'),
            data={'chat_id': int(chat), 'caption': caption, 'parse_mode': 'html'},
            files={'photo': (os.path.basename(filename), photo_file, 'image/png')},
            timeout=(10, 45),
            proxies=requests_proxies(proxy_url),
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get('ok'):
        raise RuntimeError(payload.get('description') or 'Telegram API вернул ошибку')



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
                settings = load_settings()
                proxy_url = build_proxy_url(
                    settings.tg_proxy_type, settings.tg_proxy_host, settings.tg_proxy_port,
                    settings.tg_proxy_username, settings.tg_proxy_password
                )
                telebot.apihelper.proxy = telebot_proxy(proxy_url)
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
                _send_telegram_photo(
                    filename, str(bot_token), str(chat),
                    '<em>С любовью, NeboProject</em>',
                    proxy_url=build_proxy_url(
                        load_settings().tg_proxy_type, load_settings().tg_proxy_host, load_settings().tg_proxy_port,
                        load_settings().tg_proxy_username, load_settings().tg_proxy_password
                    ),
                )
                try:
                    os.remove(filename)
                except Exception:
                    pass
                return True, '[SYSTEM] Скриншот отправлен в Telegram'
            except Exception as e:
                if attempt == 3:
                    # Do NOT delete the screenshot when Telegram is unreachable.
                    # It can be sent again after the network is restored.
                    return False, f'[ERROR] Не удалось отправить скриншот в Telegram: {_telegram_error(e, str(bot_token))}'
                tm.sleep(3)
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
