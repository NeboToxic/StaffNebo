from __future__ import annotations

from typing import Optional
from urllib.parse import quote


def normalize_proxy_type(value: str) -> str:
    value = (value or 'none').strip().lower()
    if value in {'http', 'socks5'}:
        return value
    return 'none'


def build_proxy_url(proxy_type: str, host: str, port: str, username: str = '', password: str = '') -> Optional[str]:
    proxy_type = normalize_proxy_type(proxy_type)
    host = (host or '').strip()
    port = (str(port or '')).strip()
    if proxy_type == 'none':
        return None
    if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('Для прокси укажите адрес и порт.')
    if any(c in host for c in ('/', '@', '?', '#', ' ')):
        raise ValueError('Укажите только адрес прокси без схемы и пути.')
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'  # IPv6 literal
    scheme = 'http' if proxy_type == 'http' else 'socks5h'
    auth = ''
    if username:
        auth = quote(username, safe='')
        if password:
            auth += ':' + quote(password, safe='')
        auth += '@'
    return f'{scheme}://{auth}{host}:{int(port)}'


def requests_proxies(proxy_url: Optional[str]):
    if not proxy_url:
        return None
    return {'http': proxy_url, 'https': proxy_url}


def telebot_proxy(proxy_url: Optional[str]):
    if not proxy_url:
        return None
    return {'http': proxy_url, 'https': proxy_url}
