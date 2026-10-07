from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PunishmentType(str, Enum):
    MUTE = 'mute'
    WARN = 'warn'
    KICK = 'kick'


@dataclass
class ModerationEvent:
    event_type: PunishmentType
    line: str
    moderator_html: str
    target_html: str
    reason: str
    needs_screenshot: bool
    dating: Optional[str] = None
    timing: Optional[str] = None


LABELS = {
    PunishmentType.MUTE: {
        'ru': 'Мут',
        'vk_title': '🛑 Мут',
        'sent_tg': '[SYSTEM] Мут отправлен в Telegram',
        'sent_vk': '[SYSTEM] Мут отправлен во ВКонтакте',
        'fail_tg': 'мут в Telegram',
        'fail_vk': 'мут во ВКонтакте',
        'tg_attempts': 10,
        'vk_attempts': 3,
        'tg_sleep': 1,
        'vk_sleep': 2,
    },
    PunishmentType.WARN: {
        'ru': 'Предупреждение',
        'vk_title': '⚠️ Предупреждение',
        'sent_tg': '[SYSTEM] Варн отправлен в Telegram',
        'sent_vk': '[SYSTEM] Варн отправлен во ВКонтакте',
        'fail_tg': 'варн в Telegram',
        'fail_vk': 'варн во ВКонтакте',
        'tg_attempts': 10,
        'vk_attempts': 3,
        'tg_sleep': 1,
        'vk_sleep': 2,
    },
    PunishmentType.KICK: {
        'ru': 'Кик',
        'vk_title': '👢 Кик',
        'sent_tg': '[SYSTEM] Кик отправлен в Telegram',
        'sent_vk': '[SYSTEM] Кик отправлен во ВКонтакте',
        'fail_tg': 'кик в Telegram',
        'fail_vk': 'кик во ВКонтакте',
        'tg_attempts': 10,
        'vk_attempts': 3,
        'tg_sleep': 1,
        'vk_sleep': 2,
    },
}
