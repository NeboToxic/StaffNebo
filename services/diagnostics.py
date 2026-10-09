import datetime
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from config import VERSION
from core.dependency_versions import VERSIONS
from core import history,profiles
from core.paths import DB_PATH
from core.database import connect
from core.settings import load_settings
from core.secrets import redact,FIELDS


def export_diagnostics(path,state=None):
    known=[]
    for row in profiles.list_profiles():
        try:
            _,cfg=profiles.load_profile(row['id']);known.extend(getattr(cfg,f) for f in FIELDS)
        except Exception:pass
    cfg=load_settings();known.extend(getattr(cfg,f) for f in FIELDS)
    packages={}
    for name in ('PyQt5','Pillow','requests','pynput','pygame','tzlocal'):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=VERSIONS.get(name,'bundled') if getattr(sys,'frozen',False) else 'not installed'
    report={'app_version':VERSION,'created':datetime.datetime.now().astimezone().isoformat(),
        'system':platform.platform(),'python':platform.python_version(),'frozen':bool(getattr(sys,'frozen',False)),
        'dependencies':packages,'platform':cfg.platform,'proxy_type':cfg.tg_proxy_type,
        'profile_count':len(profiles.list_profiles()),'database_bytes':Path(DB_PATH).stat().st_size if Path(DB_PATH).exists() else 0,
        'monitor':state or {},'runtime_errors':runtime_errors(),'statistics':{k:v for k,v in history.statistics().items() if k!='reasons'},'recent_errors':[
            {'id':r['id'],'created':r['created'],'platform':r['platform'],'error':redact(r['error'],known)}
            for r in history.list_events(status='failed',limit=20)]}
    # Whole-output redaction covers an exception containing an embedded request.
    Path(path).write_text(redact(json.dumps(report,ensure_ascii=False,indent=2),known),encoding='utf-8')
    return path


def record_error(message):
    try:
        cfg=load_settings();message=redact(message,[getattr(cfg,f) for f in FIELDS])
        with connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS diagnostic_errors(id INTEGER PRIMARY KEY,created TEXT NOT NULL,message TEXT NOT NULL)')
            conn.execute('INSERT INTO diagnostic_errors(created,message) VALUES(?,?)',(datetime.datetime.now().astimezone().isoformat(),message))
            conn.execute('DELETE FROM diagnostic_errors WHERE id NOT IN (SELECT id FROM diagnostic_errors ORDER BY id DESC LIMIT 500)')
    except Exception:pass


def runtime_errors():
    with connect() as conn:
        exists=conn.execute("SELECT 1 FROM sqlite_master WHERE name='diagnostic_errors'").fetchone()
        if not exists:return []
        return [dict(r) for r in conn.execute('SELECT created,message FROM diagnostic_errors ORDER BY id DESC LIMIT 30')]
