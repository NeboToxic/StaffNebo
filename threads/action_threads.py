import datetime
import random
import re
import time as tm

import pyautogui as pag
from PyQt5.QtCore import QThread, pyqtSignal
from tzlocal import get_localzone

import core.globals as g
from core.helpers import add_timezone_to_str, pressing_key
from core.paths import screenshot_path
from domain.events import ModerationEvent, PunishmentType
from domain.notifier import SendPayload


class CaptureThread(QThread):
    """Open chat, wait, take screenshot, emit SendPayload for mute/warn."""

    finished_signal = pyqtSignal(object)

    def __init__(self, event: ModerationEvent):
        super().__init__()
        self.event = event
        self.should_stop = False

    def stop(self):
        self.should_stop = True
        if self.isRunning():
            self.wait(1000)

    def run(self):
        if self.should_stop:
            return
        tm.sleep(0.2)
        if self.should_stop:
            return

        pressing_key('t')
        current_date = datetime.datetime.now(get_localzone()).strftime('%d.%m.%Y')

        if self.should_stop:
            return
        tm.sleep(g.screenshot_delay)

        if self.should_stop:
            return
        screenshot = pag.screenshot()
        randid = int(datetime.datetime.now().timestamp() * 1000) + random.randint(1, 999)
        screenshot.save(screenshot_path(str(randid)))

        time_match = re.search(r'\[(\d{2}:\d{2}:\d{2})', self.event.line)
        timesi = time_match.group(1) if time_match else '00:00:00'
        last_time = add_timezone_to_str(timesi)

        if not self.should_stop:
            self.finished_signal.emit(SendPayload(
                event_type=self.event.event_type,
                user_id=str(g.my_id),
                moderator_html=self.event.moderator_html,
                target_html=self.event.target_html,
                reason=self.event.reason,
                dating=current_date,
                timing=last_time,
                photoid=str(randid),
            ))


class KickPrepareThread(QThread):
    """Kick has no screenshot; just package payload on a worker thread."""

    finished_signal = pyqtSignal(object)

    def __init__(self, event: ModerationEvent):
        super().__init__()
        self.event = event
        self.should_stop = False

    def stop(self):
        self.should_stop = True
        if self.isRunning():
            self.wait(1000)

    def run(self):
        if self.should_stop:
            return
        self.finished_signal.emit(SendPayload(
            event_type=PunishmentType.KICK,
            user_id=str(g.my_id),
            moderator_html=self.event.moderator_html,
            target_html=self.event.target_html,
            reason=self.event.reason,
            dating=self.event.dating or datetime.datetime.now(get_localzone()).strftime('%d.%m.%Y'),
            timing=self.event.timing or '00:00:00 (UTC+0)',
            photoid=None,
        ))


class ScreenshotThread(QThread):
    finished_signal = pyqtSignal(bool, str, str)

    def __init__(self):
        super().__init__()
        self.should_stop = False

    def stop(self):
        self.should_stop = True
        if self.isRunning():
            self.wait(1000)

    def run(self):
        if self.should_stop:
            return
        try:
            filename = screenshot_path(
                f'screenshot_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
            )
            if not self.should_stop:
                screenshot = pag.screenshot()
                screenshot.save(filename)
            if not self.should_stop:
                self.finished_signal.emit(True, f'[SYSTEM] Скриншот создан: {filename}', filename)
        except Exception as e:
            if not self.should_stop:
                self.finished_signal.emit(False, f'[ERROR] Ошибка при создании скриншота: {e}', '')
