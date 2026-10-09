import csv
import datetime as dt
import json
import secrets
from dataclasses import asdict
from html import unescape
import re
from core.database import connect, get_meta, init_schema
from core.profiles import encoded
from core.secrets import open_dict, redact, FIELDS


def init_history():
    init_schema()
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL,
            event_type TEXT NOT NULL, target TEXT NOT NULL, moderator TEXT NOT NULL,
            reason TEXT NOT NULL, dating TEXT NOT NULL, timing TEXT NOT NULL,
            profile_id TEXT NOT NULL DEFAULT '', profile_name TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL, screenshot_path TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL,
            settings_json TEXT NOT NULL, delivery_id INTEGER NOT NULL,
            sent_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS events_status_created ON events(status,created);
        CREATE INDEX IF NOT EXISTS events_profile_created ON events(profile_id,created);
        """)


def recover_interrupted():
    init_history()
    with connect() as conn:
        conn.execute("UPDATE events SET status='pending', error='Отправка прервана завершением приложения' WHERE status='sending'")


def plain(text):
    return unescape(re.sub(r'<.*?>','',text or ''))


def create_event(payload, settings, screenshot='', event_type=None, status='pending'):
    init_history()
    data = {key: value for key,value in asdict(payload).items() if key not in ('settings_override','record_id','delivery_id')}
    data['event_type'] = payload.event_type.value
    data['needs_photo'] = bool(getattr(payload,'needs_photo',False))
    key = get_meta('active_profile','') or ''
    with connect() as conn:
        profile = conn.execute('SELECT name FROM profiles WHERE id=?',(key,)).fetchone() if key else None
        cursor = conn.execute('INSERT INTO events(created,event_type,target,moderator,reason,dating,timing,profile_id,profile_name,platform,screenshot_path,status,payload_json,settings_json,delivery_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (dt.datetime.now().astimezone().isoformat(timespec='seconds'),event_type or payload.event_type.value,
             plain(payload.target_html),plain(payload.moderator_html),payload.reason,payload.dating,payload.timing,
             key,profile['name'] if profile else 'Основной',settings.platform,screenshot,status,
             json.dumps(data,ensure_ascii=False),encoded(settings),secrets.randbelow(2**31-1)+1))
        return cursor.lastrowid


def update_payload(key,payload,screenshot=''):
    data={k:v for k,v in asdict(payload).items() if k not in ('settings_override','record_id','delivery_id')}
    data['event_type']=payload.event_type.value
    with connect() as conn:
        conn.execute('UPDATE events SET payload_json=?, screenshot_path=?, dating=?, timing=? WHERE id=?',
                     (json.dumps(data,ensure_ascii=False),screenshot,payload.dating,payload.timing,key))


def get_event(key):
    init_history()
    with connect() as conn:
        row=conn.execute('SELECT * FROM events WHERE id=?',(key,)).fetchone()
    if not row: raise ValueError('Событие не найдено')
    return dict(row)


def event_settings(row):
    from core.settings import settings_from_dict
    return settings_from_dict(open_dict(json.loads(row['settings_json'])))


def claim(key):
    with connect() as conn:
        return conn.execute("UPDATE events SET status='sending', attempts=attempts+1 WHERE id=? AND status IN ('pending','failed')",(key,)).rowcount == 1


def finish(key,success,message=''):
    row=get_event(key)
    try:
        cfg=event_settings(row)
        safe=redact(message,[getattr(cfg,k) for k in FIELDS])
    except Exception: safe=redact(message)
    with connect() as conn:
        conn.execute('UPDATE events SET status=?, error=?, sent_at=? WHERE id=?',
            ('sent' if success else 'failed','' if success else safe,
             dt.datetime.now().astimezone().isoformat(timespec='seconds') if success else '',key))


def list_events(query='',kind='',status='',since='',until='',profile='',limit=1000):
    init_history()
    sql='SELECT * FROM events WHERE 1=1'; values=[]
    if query:
        sql+=' AND (target LIKE ? ESCAPE "!" OR reason LIKE ? ESCAPE "!" OR moderator LIKE ? ESCAPE "!")'
        term='%'+query.replace('!','!!').replace('%','!%').replace('_','!_')+'%';values.extend([term]*3)
    for column,value in [('event_type',kind),('status',status),('profile_id',profile)]:
        if value: sql+=f' AND {column}=?';values.append(value)
    if since: sql+=' AND substr(created,1,10)>=?';values.append(since)
    if until: sql+=' AND substr(created,1,10)<=?';values.append(until)
    sql+=' ORDER BY id DESC'
    if limit is not None: sql+=' LIMIT ?';values.append(int(limit))
    with connect() as conn: return [dict(r) for r in conn.execute(sql,values)]


def export_csv(path,**filters):
    columns=('id','created','event_type','target','moderator','reason','profile_name','platform','status','attempts','error','screenshot_path')
    rows=list_events(limit=None,**filters)
    with open(path,'w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader()
        for row in rows:
            # Avoid spreadsheet formula injection in exported chat text.
            safe={k:row[k] for k in columns}
            for key,value in safe.items():
                if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):safe[key]="'"+value
            writer.writerow(safe)
    return len(rows)


def statistics(profile=''):
    init_history(); today=dt.date.today(); week=today-dt.timedelta(days=6)
    result={}
    with connect() as conn:
        for label,start in [('day',today),('week',week)]:
            where='substr(created,1,10)>=?';args=[str(start)]
            if profile:where+=' AND profile_id=?';args.append(profile)
            rows=conn.execute(f'SELECT event_type,count(*) count FROM events WHERE {where} GROUP BY event_type',args)
            result[label]={r['event_type']:r['count'] for r in rows}
            count=conn.execute(f"SELECT sum(status='sent') sent, sum(status IN ('sent','failed')) completed FROM events WHERE {where}",args).fetchone()
            result[label]['success_rate']=round(100*(count['sent'] or 0)/(count['completed'] or 1),1)
        result['reasons']=[dict(r) for r in conn.execute("SELECT reason,count(*) count FROM events WHERE event_type!='screenshot'"+(' AND profile_id=?' if profile else '')+' GROUP BY reason ORDER BY count DESC LIMIT 10',[profile] if profile else [])]
    return result


def replace_delivery_settings(key,settings):
    row=get_event(key)
    if row['status'] not in ('pending','failed'):raise ValueError('Можно изменить только неотправленное событие')
    data=json.loads(row['payload_json']);data['user_id']=str(settings.chat_id or '0')
    with connect() as conn:
        conn.execute('UPDATE events SET settings_json=?,platform=?,payload_json=? WHERE id=? AND status IN (\'pending\',\'failed\')',
            (encoded(settings),settings.platform,json.dumps(data,ensure_ascii=False),key))


def omit_photo(key):
    row=get_event(key);data=json.loads(row['payload_json']);data['needs_photo']=False
    with connect() as conn:conn.execute('UPDATE events SET payload_json=? WHERE id=?',(json.dumps(data,ensure_ascii=False),key))
