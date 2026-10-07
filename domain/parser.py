import datetime
import re
from typing import Optional

try:
    from tzlocal import get_localzone
except ImportError:
    def get_localzone():
        return datetime.datetime.now().astimezone().tzinfo

from core.helpers import add_timezone_to_str
from domain.events import ModerationEvent, PunishmentType


def _format_target(nick: str, tag: Optional[str], strip_dot: bool = False) -> str:
    if tag:
        tag_value = tag.rstrip('.') if strip_dot else tag
        return f'{nick} ┃ <code>{tag_value}</code>'
    nick_value = nick.rstrip('.') if strip_dot else nick
    return f'<code>{nick_value}</code>'


def _format_moderator(prefix: str, role: str, nick: str) -> str:
    return f'{prefix} {role} <code>{nick}</code>'


def _extract_log_time(line: str) -> str:
    time_match = re.search(r'\[(\d{2}:\d{2}:\d{2})', line)
    timesi = time_match.group(1) if time_match else '00:00:00'
    return add_timezone_to_str(timesi)


def parse_moderation_line(line: str, nickname: str) -> Optional[ModerationEvent]:
    """Parse a Cristalix log line into a moderation event for the given nickname."""
    if not nickname or not line:
        return None

    escaped_nick = re.escape(nickname)
    tag_tail = r'\S*(?:\s+\S+)*'

    mute_pattern = (
        r'㰳\s+(\S+)\s+(\S+)\s+(' + escaped_nick + r')' + tag_tail +
        r'\s+замутил\s+игрока\s+(\S+)(?:\s+┃\s+(\S+))?.*причине:\s+(.+)'
    )
    mute_match = re.search(mute_pattern, line)
    if mute_match:
        return ModerationEvent(
            event_type=PunishmentType.MUTE,
            line=line,
            moderator_html=_format_moderator(
                mute_match.group(1), mute_match.group(2), mute_match.group(3)
            ),
            target_html=_format_target(mute_match.group(4), mute_match.group(5)),
            reason=mute_match.group(6),
            needs_screenshot=True,
        )

    warn_pattern = (
        r'(\S+)\s+(\S+)\s+(' + escaped_nick + r')' + tag_tail +
        r'\s+предупредил\s+игрока\s+(\S+)(?:\s+┃\s+(\S+))?.*причине:\s+(.+)'
    )
    warn_match = re.search(warn_pattern, line)
    if warn_match:
        return ModerationEvent(
            event_type=PunishmentType.WARN,
            line=line,
            moderator_html=_format_moderator(
                warn_match.group(1), warn_match.group(2), warn_match.group(3)
            ),
            target_html=_format_target(warn_match.group(4), warn_match.group(5), strip_dot=True),
            reason=warn_match.group(6),
            needs_screenshot=True,
        )

    kick_pattern = (
        r'㰳\s+(\S+)\s+(\S+)\s+(' + escaped_nick + r')' + tag_tail +
        r'\s+кикнул\s+игрока\s+(\S+)(?:\s+┃\s+(\S+))?.*причине:\s+(.+)'
    )
    kick_match = re.search(kick_pattern, line)
    if kick_match:
        return ModerationEvent(
            event_type=PunishmentType.KICK,
            line=line,
            moderator_html=_format_moderator(
                kick_match.group(1), kick_match.group(2), kick_match.group(3)
            ),
            target_html=_format_target(kick_match.group(4), kick_match.group(5)),
            reason=kick_match.group(6),
            needs_screenshot=False,
            dating=datetime.datetime.now(get_localzone()).strftime('%d.%m.%Y'),
            timing=_extract_log_time(line),
        )

    return None
