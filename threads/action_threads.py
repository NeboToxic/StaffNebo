import datetime
import uuid
import re
import time as tm

import pyautogui as pag
from PyQt5.QtCore import pyqtSignal
from threads.base import StoppableThread
from tzlocal import get_localzone

import core.globals as g
from core.helpers import add_timezone_to_str, pressing_key
from core.paths import screenshot_path
from core.settings import load_settings
from domain.capture import capture_image
from domain.events import ModerationEvent, PunishmentType
from domain.notifier import SendPayload


class CaptureThread(StoppableThread):
    """Open chat, wait, take screenshot, emit SendPayload for mute/warn."""

    finished_signal = pyqtSignal(object)

    def __init__(self, event: ModerationEvent, settings=None):
        super().__init__()
        self.event = event
        self.settings = settings or load_settings()

    error_signal = pyqtSignal(str)

    def run(self):
        try:
            if self.pause(0.2):
                return
            pressing_key('t')
            if self.pause(self.settings.screenshot_delay):
                return
            photoid = uuid.uuid4().hex
            capture_image(self.settings).save(screenshot_path(photoid))
            match = re.search(r'\[(\d{2}:\d{2}:\d{2})', self.event.line)
            if not self.should_stop:
                self.finished_signal.emit(SendPayload(
                    event_type=self.event.event_type, user_id=str(self.settings.chat_id or '0'),
                    moderator_html=self.event.moderator_html,
                    target_html=self.event.target_html, reason=self.event.reason,
                    dating=datetime.datetime.now(get_localzone()).strftime('%d.%m.%Y'),
                    timing=add_timezone_to_str(match.group(1) if match else '00:00:00'),
                    photoid=photoid, needs_photo=True, settings_override=self.settings,
                ))
        except Exception as exc:
            if not self.should_stop:
                self.error_signal.emit(f'[ERROR] Ошибка подготовки скриншота: {exc}')


class KickPrepareThread(StoppableThread):
    """Kick has no screenshot; just package payload on a worker thread."""

    finished_signal = pyqtSignal(object)

    def __init__(self, event: ModerationEvent, settings=None):
        super().__init__()
        self.event = event
        self.settings = settings or load_settings()

    def run(self):
        if self.should_stop:
            return
        self.finished_signal.emit(SendPayload(
            event_type=self.event.event_type,
            user_id=str(self.settings.chat_id or '0'),
            moderator_html=self.event.moderator_html,
            target_html=self.event.target_html,
            reason=self.event.reason,
            dating=self.event.dating or datetime.datetime.now(get_localzone()).strftime('%d.%m.%Y'),
            timing=self.event.timing or add_timezone_to_str((re.search(r'\[(\d{2}:\d{2}:\d{2})',self.event.line).group(1) if re.search(r'\[(\d{2}:\d{2}:\d{2})',self.event.line) else '00:00:00')),
            photoid=None, needs_photo=False, settings_override=self.settings,
        ))


class ScreenshotThread(StoppableThread):
    finished_signal = pyqtSignal(bool, str, str)

    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or load_settings()

    def run(self):
        if self.should_stop:
            return
        try:
            filename = screenshot_path(
                f'screenshot_{uuid.uuid4().hex}.png'
            )
            if not self.should_stop:
                screenshot = capture_image(self.settings)
                screenshot.save(filename)
            if not self.should_stop:
                self.finished_signal.emit(True, f'[SYSTEM] Скриншот создан: {filename}', filename)
        except Exception as e:
            if not self.should_stop:
                self.finished_signal.emit(False, f'[ERROR] Ошибка при создании скриншота: {e}', '')
