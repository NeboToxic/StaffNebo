import time as tm
import threading
import sys
import os
import atexit
import datetime
import tzlocal
from tzlocal import get_localzone
import core.globals as g
from core.paths import resource_path, SCREENSHOTS_DIR
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

def gui_print(message: str):
    if g.gui_ready and g.main_window and hasattr(g.main_window, 'log_message'):
        g.main_window.log_requested.emit(message)
    else:
        g.gui_messages_buffer.append(message)
        print(message)



def cleanup():
    """Release listeners; unsent screenshots remain available on disk."""
    if g.main_window is not None:
        g.main_window.shutdown()


def safe_cleanup():
    try:
        cleanup()
    except Exception as exc:
        print(f"Cleanup error: {exc}")


atexit.register(safe_cleanup)


def make_sound():
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    import pygame

    sound_path = resource_path(os.path.join('path', 'click.mp3'))
    if not os.path.exists(sound_path):
        print(f"[WARNING] Звуковой файл не найден: {sound_path}")
        return

    try:
        pygame.mixer.init()
        pygame.mixer.music.load(sound_path)
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        print(f"[ERROR] Ошибка воспроизведения звука: {e}")



def pressing_key(key):
    import pynput.keyboard as pynput_kb

    try:
        keyboard = pynput_kb.Controller()
        keyboard.press(key)
        keyboard.release(key)
    except Exception as e:
        raise RuntimeError(f"Не удалось нажать клавишу: {e}") from e



def add_timezone_to_str(time_str: str) -> str:
    local_tz = get_localzone()
    now = datetime.datetime.now(local_tz)
    total_minutes = int(local_tz.utcoffset(now).total_seconds() / 60)
    sign = '+' if total_minutes >= 0 else '-'
    hours, minutes = divmod(abs(total_minutes), 60)
    utc_str = f'UTC{sign}{hours}' + (f':{minutes:02d}' if minutes else '')

    return f"{time_str} ({utc_str})"



def init_local_storage():
    from core.settings import init_settings
    try:
        init_settings()
        from core.profiles import ensure_default
        from core.history import recover_interrupted
        ensure_default()
        recover_interrupted()
        return True
    except Exception as e:
        gui_print(f"[ERROR] Не удалось инициализировать базу настроек: {e}")
        return False