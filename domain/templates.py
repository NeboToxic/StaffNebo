from string import Formatter
from html import escape
from domain.events import LABELS

DEFAULT_TEMPLATE='Ник: {target}\nТип наказания: {type}\nПричина: {reason}\nДата: {date}\nВремя: {time}\nМодератор: {moderator}\n\nЛюбишь небо?'
FIELDS={'target','type','reason','date','time','moderator','profile'}


def validate_template(text):
    if not text.strip(): raise ValueError('Шаблон не может быть пустым')
    if len(text)>10000: raise ValueError('Шаблон слишком большой (максимум 10000 символов)')
    for _,field,spec,conversion in Formatter().parse(text):
        if field is not None and (field not in FIELDS or spec or conversion):
            raise ValueError('Допустимые поля: '+', '.join(sorted(FIELDS)))
    return text


def render_template(payload,settings,html=False):
    from core.history import plain
    template=validate_template(settings.notification_template or DEFAULT_TEMPLATE)
    values={'target':plain(payload.target_html),'moderator':plain(payload.moderator_html),
            'type':LABELS[payload.event_type]['ru'],'reason':payload.reason,'date':payload.dating,
            'time':payload.timing,'profile':settings.nick}
    text=template.format_map(values)
    return escape(text) if html else text
