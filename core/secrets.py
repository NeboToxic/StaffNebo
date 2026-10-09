"""Windows user-bound DPAPI secrets; never silently fall back to plaintext."""
import base64
import ctypes
import json
import re
import sys
from ctypes import wintypes

FIELDS = ('bot_id', 'vk_token', 'tg_proxy_password')
PREFIX = 'dpapi:v1:'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if sys.platform != 'win32':
        raise RuntimeError('Защита секретов требует Windows DPAPI')
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    func.restype = wintypes.BOOL
    if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(dest.data)


def protect(value):
    if not value or value.startswith(PREFIX):
        return value or ''
    return PREFIX + base64.b64encode(_crypt(value.encode('utf-8'))).decode('ascii')


def reveal(value):
    if not value or not value.startswith(PREFIX):
        return value or ''  # Legacy plaintext is migrated by settings.load_settings.
    try:
        return _crypt(base64.b64decode(value[len(PREFIX):]), True).decode('utf-8')
    except Exception as exc:
        raise RuntimeError('Не удалось расшифровать секрет: нужен тот же аккаунт Windows. Удалите секрет и введите его заново.') from exc


def seal_dict(data):
    result = dict(data)
    for key in FIELDS:
        result[key] = protect(str(result.get(key) or ''))
    return result


def open_dict(data):
    result = dict(data)
    for key in FIELDS:
        result[key] = reveal(str(result.get(key) or ''))
    return result


def redact(text, known=()):
    text = str(text or '')
    for secret in sorted((s for s in known if s), key=len, reverse=True):
        text = text.replace(secret, '<SECRET>')
    text = re.sub(r'(bot)\d+:[A-Za-z0-9_-]+', r'\1<SECRET>', text)
    text = re.sub(r'vk1\.[A-Za-z0-9_-]+', '<SECRET>', text)
    return re.sub(r'(https?://|socks5h?://)[^/@\s]+:[^/@\s]*@', r'\1<AUTH>@', text)
