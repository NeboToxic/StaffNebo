import os
from dataclasses import dataclass
from typing import Optional

from core.database import connect, get_meta, init_schema, set_meta
from core.paths import data_path


@dataclass
class AppSettings:
    nick: str = ''
    logs: str = ''
    platform: str = 'telegram'
    bot_id: str = ''
    chat_id: str = ''
    vk_user_id: str = ''
    vk_token: str = ''
    use_sound: bool = True
    screenshot_delay: float = 0.7
    log_display_mode: str = 'all'
    theme: str = 'Небо'
    bind_keycode: Optional[int] = None
    bind_key: Optional[str] = None
    verified_bot_id: str = ''
    verified_chat_id: str = ''
    tg_proxy_type: str = 'none'
    tg_proxy_host: str = ''
    tg_proxy_port: str = ''
    tg_proxy_username: str = ''
    tg_proxy_password: str = ''


_COLUMNS = (
    'nick', 'logs', 'platform', 'bot_id', 'chat_id', 'vk_user_id', 'vk_token',
    'use_sound', 'screenshot_delay', 'log_display_mode', 'theme',
    'bind_keycode', 'bind_key', 'verified_bot_id', 'verified_chat_id',
    'tg_proxy_type', 'tg_proxy_host', 'tg_proxy_port', 'tg_proxy_username', 'tg_proxy_password',
)


def init_settings():
    init_schema()
    _migrate_legacy_files_once()
    return load_settings()


def load_settings() -> AppSettings:
    init_schema()
    with connect() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if row is None:
        return AppSettings()
    return AppSettings(
        nick=row['nick'] or '',
        logs=row['logs'] or '',
        platform=row['platform'] or 'telegram',
        bot_id=row['bot_id'] or '',
        chat_id=row['chat_id'] or '',
        vk_user_id=row['vk_user_id'] or '',
        vk_token=row['vk_token'] if 'vk_token' in row.keys() else '',
        use_sound=bool(row['use_sound']),
        screenshot_delay=float(row['screenshot_delay'] if row['screenshot_delay'] is not None else 0.7),
        log_display_mode=row['log_display_mode'] or 'all',
        theme=row['theme'] or 'Небо',
        bind_keycode=row['bind_keycode'],
        bind_key=row['bind_key'] if 'bind_key' in row.keys() else None,
        verified_bot_id=row['verified_bot_id'] or '',
        verified_chat_id=row['verified_chat_id'] or '',
        tg_proxy_type=row['tg_proxy_type'] if 'tg_proxy_type' in row.keys() else 'none',
        tg_proxy_host=row['tg_proxy_host'] if 'tg_proxy_host' in row.keys() else '',
        tg_proxy_port=row['tg_proxy_port'] if 'tg_proxy_port' in row.keys() else '',
        tg_proxy_username=row['tg_proxy_username'] if 'tg_proxy_username' in row.keys() else '',
        tg_proxy_password=row['tg_proxy_password'] if 'tg_proxy_password' in row.keys() else '',
    )


def save_settings(settings: AppSettings) -> AppSettings:
    init_schema()
    values = (
        settings.nick or '',
        settings.logs or '',
        settings.platform or 'telegram',
        settings.bot_id or '',
        settings.chat_id or '',
        settings.vk_user_id or '',
        settings.vk_token or '',
        1 if settings.use_sound else 0,
        float(settings.screenshot_delay) if settings.screenshot_delay is not None else 0.7,
        settings.log_display_mode or 'all',
        settings.theme or 'Небо',
        settings.bind_keycode,
        settings.verified_bot_id or '',
        settings.verified_chat_id or '',
        settings.tg_proxy_type or 'none',
        settings.tg_proxy_host or '',
        settings.tg_proxy_port or '',
        settings.tg_proxy_username or '',
        settings.tg_proxy_password or '',
    )
    assignments = ', '.join(f'{col} = ?' for col in _COLUMNS)
    with connect() as conn:
        conn.execute(f"UPDATE settings SET {assignments} WHERE id = 1", values)
    try:
        import core.globals as g
        g.apply_settings(settings)
    except Exception:
        pass
    return settings


def update_settings(**changes) -> AppSettings:
    settings = load_settings()
    for key, value in changes.items():
        if not hasattr(settings, key):
            raise AttributeError(f'Unknown setting: {key}')
        setattr(settings, key, value)
    return save_settings(settings)


def _parse_legacy_yml(path: str) -> dict:
    data = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
    return data


def _migrate_legacy_files_once():
    if get_meta('legacy_migrated') == '1':
        return

    settings = load_settings()
    yml_path = data_path('config.yml')
    if os.path.exists(yml_path):
        try:
            data = _parse_legacy_yml(yml_path)
            if data.get('nick'):
                settings.nick = data['nick']
            if 'logs' in data:
                settings.logs = data['logs']
            if data.get('platform'):
                settings.platform = data['platform']
            if 'bot_id' in data:
                settings.bot_id = data['bot_id']
            if 'chat_id' in data:
                settings.chat_id = data['chat_id']
            if 'vk_user_id' in data:
                settings.vk_user_id = data['vk_user_id']
            if data.get('use_sound'):
                settings.use_sound = data['use_sound'].lower() == 'true'
            if data.get('screenshot_delay'):
                try:
                    settings.screenshot_delay = float(data['screenshot_delay'])
                except (ValueError, TypeError):
                    pass
            if data.get('log_display_mode'):
                settings.log_display_mode = data['log_display_mode']
        except Exception as e:
            print(f"[ERROR] Не удалось прочитать config.yml: {e}")

    theme_path = data_path('theme.txt')
    if os.path.exists(theme_path):
        try:
            with open(theme_path, 'r', encoding='utf-8') as f:
                theme = f.read().strip()
            if theme:
                settings.theme = theme
        except Exception as e:
            print(f"[ERROR] Не удалось прочитать theme.txt: {e}")

    binds_path = data_path('binds.txt')
    if os.path.exists(binds_path):
        try:
            with open(binds_path, 'r', encoding='utf-8') as f:
                raw = f.read().strip()
            if raw:
                settings.bind_keycode = int(raw)
        except Exception as e:
            print(f"[ERROR] Не удалось прочитать binds.txt: {e}")

    verified_path = data_path('verified_settings.txt')
    if os.path.exists(verified_path):
        try:
            with open(verified_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('bot_id:'):
                        settings.verified_bot_id = line.split(':', 1)[1].strip()
                    elif line.startswith('chat_id:'):
                        settings.verified_chat_id = line.split(':', 1)[1].strip()
        except Exception as e:
            print(f"[ERROR] Не удалось прочитать verified_settings.txt: {e}")

    bot_verified_path = data_path('bot_verified.txt')
    if os.path.exists(bot_verified_path) and not (settings.verified_bot_id or settings.verified_chat_id):
        try:
            with open(bot_verified_path, 'r', encoding='utf-8') as f:
                raw = f.read().strip()
            if '|' in raw:
                bot_part, chat_part = raw.split('|', 1)
                settings.verified_bot_id = bot_part
                settings.verified_chat_id = chat_part
        except Exception as e:
            print(f"[ERROR] Не удалось прочитать bot_verified.txt: {e}")

    save_settings(settings)
    set_meta('legacy_migrated', '1')
    print("[SYSTEM] Настройки перенесены в SQLite")
