import sqlite3
from contextlib import contextmanager

from core.paths import DB_PATH, ensure_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    nick TEXT NOT NULL DEFAULT '',
    logs TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT 'telegram',
    bot_id TEXT NOT NULL DEFAULT '',
    chat_id TEXT NOT NULL DEFAULT '',
    vk_user_id TEXT NOT NULL DEFAULT '',
    vk_token TEXT NOT NULL DEFAULT '',
    use_sound INTEGER NOT NULL DEFAULT 1,
    screenshot_delay REAL NOT NULL DEFAULT 0.7,
    log_display_mode TEXT NOT NULL DEFAULT 'all',
    theme TEXT NOT NULL DEFAULT 'Небо',
    bind_keycode INTEGER,
    verified_bot_id TEXT NOT NULL DEFAULT '',
    verified_chat_id TEXT NOT NULL DEFAULT '',
    tg_proxy_type TEXT NOT NULL DEFAULT 'none',
    tg_proxy_host TEXT NOT NULL DEFAULT '',
    tg_proxy_port TEXT NOT NULL DEFAULT '',
    tg_proxy_username TEXT NOT NULL DEFAULT '',
    tg_proxy_password TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def connect():
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    with connect() as conn:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE settings ADD COLUMN vk_token TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        for column, definition in (
            ('tg_proxy_type', "TEXT NOT NULL DEFAULT 'none'"),
            ('tg_proxy_host', "TEXT NOT NULL DEFAULT ''"),
            ('tg_proxy_port', "TEXT NOT NULL DEFAULT ''"),
            ('tg_proxy_username', "TEXT NOT NULL DEFAULT ''"),
            ('tg_proxy_password', "TEXT NOT NULL DEFAULT ''"),
        ):
            try:
                conn.execute(f"ALTER TABLE settings ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError:
                pass
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")


def get_meta(key: str, default: str = None):
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row['value']


def set_meta(key: str, value: str):
    with connect() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
