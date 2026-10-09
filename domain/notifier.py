import os
import re
import time as tm
import secrets
from html import escape, unescape

import requests
from dataclasses import dataclass
from typing import Optional


import core.globals as g
from core.paths import screenshot_path
from core.settings import load_settings
from core.telegram_proxy import build_proxy_url, requests_proxies
from domain.events import LABELS, PunishmentType
from domain.worker_client import send_vk_message


def _telegram_error(exc: Exception, bot_token: str = '') -> str:
    """Return a user-safe Telegram error without exposing the bot token."""
    text = str(exc)
    if bot_token:
        text = text.replace(bot_token, '<TOKEN>')
    text = re.sub(r'(bot)\d{6,}:[A-Za-z0-9_-]+', r'\1<TOKEN>', text)
    text = re.sub(r'(https?://|socks5h?://)[^/@\s]+:[^/@\s]*@', r'\1<AUTH>@', text)
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
    needs_photo: Optional[bool] = None
    settings_override: object = None
    record_id: int = 0
    delivery_id: int = 0

    def __post_init__(self):
        if self.needs_photo is None:
            self.needs_photo = self.event_type != PunishmentType.KICK


def clean_html(text: str) -> str:
    return unescape(re.sub(r'<.*?>', '', text or ''))


def build_telegram_user_text(payload: SendPayload) -> str:
    label = LABELS[payload.event_type]['ru']
    return (
        f'Ник: {payload.target_html}\n'
        f'Тип наказания: {label}\n'
        f'Причина: {escape(payload.reason)}\n'
        f'Дата: {escape(payload.dating)}\n'
        f'Время: {escape(payload.timing)}\n\n'
        f'<em>Любишь небо?</em>'
    )


def build_telegram_log_text(payload: SendPayload) -> str:
    label = LABELS[payload.event_type]['ru']
    return (
        f'Блюститель: {payload.moderator_html}\n\n'
        f'Ник: {payload.target_html}\n'
        f'Тип наказания: {label}\n'
        f'Причина: {escape(payload.reason)}\n'
        f'Дата: {escape(payload.dating)}\n'
        f'Время: {escape(payload.timing)}\n\n'
        f'<em>Любишь небо?</em>'
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
        f'Любишь небо?'
    )


def _pause(seconds, should_stop=None):
    deadline = tm.monotonic() + seconds
    while tm.monotonic() < deadline:
        if should_stop and should_stop():
            return True
        tm.sleep(min(0.1, max(0, deadline - tm.monotonic())))
    return bool(should_stop and should_stop())


def _delete_sent_file(filename, settings=None):
    if (settings or load_settings()).retain_screenshots:
        return
    if filename:
        try:
            os.remove(filename)
        except OSError:
            pass  # A successful delivery must not be retried because deletion failed.


def _proxy(settings):
    return build_proxy_url(settings.tg_proxy_type, settings.tg_proxy_host,
                           settings.tg_proxy_port, settings.tg_proxy_username,
                           settings.tg_proxy_password)


def _send_telegram_text(token, chat, text, proxy_url=None, parse_mode='html'):
    data = {'chat_id': int(chat), 'text': text}
    if parse_mode:
        data['parse_mode'] = parse_mode
    response = requests.post(_telegram_api_url(token, 'sendMessage'), data=data,
                             proxies=requests_proxies(proxy_url), timeout=(10, 30))
    response.raise_for_status()
    payload = response.json()
    if not payload.get('ok'):
        raise RuntimeError(payload.get('description') or 'Telegram API вернул ошибку')


class TelegramNotifier:
    def send_punishment(self, payload, should_stop=None):
        meta = LABELS[payload.event_type]
        photo = screenshot_path(payload.photoid) if payload.photoid else None
        settings = payload.settings_override or load_settings()
        from domain.templates import render_template
        text = render_template(payload, settings, html=True) if settings.notification_template else build_telegram_user_text(payload)
        # Long reasons cannot fit Telegram's photo caption; send plain text chunks.
        long_text = len(text) > (4096 if not payload.needs_photo or not photo else 1024)
        plain = clean_html(payload.target_html)
        plain = (f'Ник: {plain}\nТип наказания: {meta["ru"]}\n'
                 f'Причина: {payload.reason}\nДата: {payload.dating}\nВремя: {payload.timing}')
        if settings.notification_template:
            plain = render_template(payload, settings)
        chunks = [plain[i:i+4000] for i in range(0, len(plain), 4000)] if long_text else [text]
        photo_sent = False
        next_chunk = 0
        token = str(settings.bot_id or '')
        for attempt in range(1, meta['tg_attempts'] + 1):
            if should_stop and should_stop():
                return False, ''
            try:
                proxy_url = _proxy(settings)
                if payload.needs_photo and photo and not photo_sent:
                    _send_telegram_photo(photo, token, payload.user_id,
                                         '<em>Любишь небо?</em>' if long_text else text, proxy_url)
                    photo_sent = True
                if not payload.needs_photo or not photo or long_text:
                    while next_chunk < len(chunks):
                        if should_stop and should_stop():
                            return False, ''
                        _send_telegram_text(token, payload.user_id, chunks[next_chunk], proxy_url,
                                            parse_mode=None if long_text else 'html')
                        next_chunk += 1
                _delete_sent_file(photo if payload.needs_photo else None, settings)
                return True, meta['sent_tg']
            except Exception as exc:
                if attempt == meta['tg_attempts']:
                    return False, f"[ERROR] Не удалось отправить {meta['fail_tg']}: {_telegram_error(exc, token)}"
                if _pause(meta['tg_sleep'], should_stop):
                    return False, ''
        return False, meta['fail_tg']

    def send_screenshot(self, filename, bot_token, chat, should_stop=None, settings=None):
        settings = settings or load_settings()
        for attempt in range(1, 4):
            if should_stop and should_stop():
                return False, ''
            try:
                _send_telegram_photo(filename, str(bot_token), str(chat),
                                     '<em>Любишь небо?</em>', _proxy(settings))
                _delete_sent_file(filename, settings)
                return True, '[SYSTEM] Скриншот отправлен в Telegram'
            except Exception as exc:
                if attempt == 3:
                    return False, f'[ERROR] Не удалось отправить скриншот в Telegram: {_telegram_error(exc, str(bot_token))}'
                if _pause(3, should_stop):
                    return False, ''
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

        settings = payload.settings_override or load_settings()
        random_id = payload.delivery_id or secrets.randbelow(2**31 - 1) + 1
        for attempt in range(1, meta['vk_attempts'] + 1):
            if should_stop and should_stop():
                return False, ''
            try:
                peer_id = vk_user_id or settings.vk_user_id
                photo = photo_path if payload.needs_photo else None
                from domain.templates import render_template
                text = render_template(payload, settings) if settings.notification_template else build_vk_text(payload)
                send_vk_message(settings.vk_token, peer_id, text, photo, random_id=random_id, should_stop=should_stop)

                if photo_path and os.path.exists(photo_path):
                    _delete_sent_file(photo_path, settings)
                return True, meta['sent_vk']
            except Exception as e:
                if attempt == meta['vk_attempts']:
                    return False, f"[ERROR] Не удалось отправить {meta['fail_vk']}: {_telegram_error(RuntimeError(str(e)), str(settings.vk_token or ''))}"
                if _pause(meta['vk_sleep'], should_stop):
                    return False, ''
        return False, f"[ERROR] Не удалось отправить {meta['fail_vk']}"

    def send_screenshot(self, filename: str, vk_user_id: str = '', should_stop=None, settings=None, delivery_id=0) -> tuple:
        settings = settings or load_settings()
        random_id = delivery_id or secrets.randbelow(2**31 - 1) + 1
        for attempt in range(1, 4):
            if should_stop and should_stop():
                return False, ''
            try:
                send_vk_message(
                    settings.vk_token, vk_user_id or settings.vk_user_id,
                    '📸 Скриншот по запросу\nЛюбишь небо?',
                    filename,
                    random_id=random_id, should_stop=should_stop,
                )
                _delete_sent_file(filename, settings)
                return True, '[SYSTEM] Скриншот отправлен во ВКонтакте'
            except Exception as e:
                if attempt == 3:
                    # Keep the screenshot on disk if VK is unavailable.
                    return False, f'[ERROR] Не удалось отправить скриншот во ВКонтакте: {_telegram_error(RuntimeError(str(e)), str(settings.vk_token or ''))}'
                if _pause(1, should_stop):
                    return False, ''
        return False, '[ERROR] Не удалось отправить скриншот во ВКонтакте'
