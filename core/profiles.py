import json
import uuid
from dataclasses import asdict
from core.database import connect, get_meta, set_meta, init_schema
from core.secrets import seal_dict, open_dict, FIELDS


def init_profiles():
    init_schema()
    with connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, settings_json TEXT NOT NULL)')


def encoded(settings):
    data = asdict(settings)
    data['verified_bot_id'] = ''  # No duplicate token copies.
    for key,value in getattr(settings,'_locked_secret_values',{}).items():
        if key in FIELDS and not data.get(key):data[key]=value
    return json.dumps(seal_dict(data), ensure_ascii=False)


def sync_active(settings):
    init_profiles()
    active = get_meta('active_profile')
    if active:
        with connect() as conn:
            conn.execute('UPDATE profiles SET settings_json=? WHERE id=?', (encoded(settings), active))


def ensure_default():
    init_profiles()
    with connect() as conn:
        row = conn.execute('SELECT id FROM profiles ORDER BY rowid LIMIT 1').fetchone()
    if row is None:
        from core.settings import load_settings
        key = save_profile('Основной', load_settings())
        set_meta('active_profile', key)
    elif not get_meta('active_profile'):
        set_meta('active_profile', row['id'])


def list_profiles():
    init_profiles()
    with connect() as conn:
        return [dict(r) for r in conn.execute('SELECT id,name FROM profiles ORDER BY name')]


def load_profile(key):
    init_profiles()
    with connect() as conn:
        row = conn.execute('SELECT * FROM profiles WHERE id=?', (key,)).fetchone()
    if not row:
        raise ValueError('Профиль не найден')
    from core.settings import settings_from_dict
    return row['name'], settings_from_dict(open_dict(json.loads(row['settings_json'])))


def save_profile(name, settings, key=None):
    init_profiles()
    name = name.strip()
    if not name:
        raise ValueError('Введите название профиля')
    key = key or uuid.uuid4().hex
    with connect() as conn:
        conn.execute('INSERT INTO profiles(id,name,settings_json) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, settings_json=excluded.settings_json', (key,name,encoded(settings)))
    return key


def activate(key):
    name, settings = load_profile(key)
    from core.settings import save_settings
    # Save the previous profile before changing the active identifier.
    previous = get_meta('active_profile')
    set_meta('active_profile', key)
    try:
        save_settings(settings)
    except Exception:
        if previous:
            set_meta('active_profile', previous)
        raise
    return name, settings


def delete_profile(key):
    if key == get_meta('active_profile'):
        raise ValueError('Нельзя удалить активный профиль. Сначала переключитесь на другой.')
    with connect() as conn:
        conn.execute('DELETE FROM profiles WHERE id=?',(key,))


def clear_profile_secrets():
    init_profiles()
    with connect() as conn:
        for row in conn.execute('SELECT id, settings_json FROM profiles').fetchall():
            data = json.loads(row['settings_json'])
            for key in (*FIELDS, 'verified_bot_id'):
                data[key] = ''
            conn.execute('UPDATE profiles SET settings_json=? WHERE id=?', (json.dumps(data),row['id']))
        # Outbox snapshots must not retain deleted tokens either.
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone()
        if exists:
            for row in conn.execute('SELECT id, settings_json FROM events').fetchall():
                data=json.loads(row['settings_json'])
                for key in (*FIELDS,'verified_bot_id'): data[key]=''
                conn.execute('UPDATE events SET settings_json=? WHERE id=?',(json.dumps(data),row['id']))
