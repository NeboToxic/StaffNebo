import time as tm
import threading
import sys
import os
import atexit
import signal
import datetime
import tzlocal
from tzlocal import get_localzone
import core.globals as g
from core.paths import resource_path, SCREENSHOTS_DIR
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

def gui_print(message: str):
    if g.gui_ready and g.main_window and hasattr(g.main_window, 'log_message'):
        g.main_window.log_message(message)
    else:
        g.gui_messages_buffer.append(message)
        print(message)



def cleanup():
    gui_print("[SYSTEM] Выключение StaffControl...")

    try:
        if g.main_window:
            if hasattr(g.main_window, 'log_monitor'):
                g.main_window.log_monitor.stop()
            if hasattr(g.main_window, 'message_sender'):
                g.main_window.message_sender.stop()
    except Exception as e:
        print(f"Cleanup QThreads error: {e}")

    try:
        if g.main_window and hasattr(g.main_window, 'keyboard_listener'):
            g.main_window.keyboard_listener.stop()
    except Exception as e:
        print(f"Cleanup hotkeys error: {e}")

    try:
        tm.sleep(0.1)
        for thread in threading.enumerate():
            if (thread != threading.current_thread()
                    and thread != threading.main_thread()
                    and not thread.daemon
                    and hasattr(thread, 'name')
                    and thread.name
                    and any(name in thread.name for name in ['Thread', 'Helper', 'Log', 'Message', 'Monitor'])):
                if hasattr(thread, 'stop'):
                    try:
                        thread.stop()
                    except Exception:
                        pass
                elif hasattr(thread, 'join'):
                    try:
                        thread.join(timeout=0.1)
                    except Exception:
                        pass
    except Exception as e:
        print(f"Cleanup threads error: {e}")

    try:
        if os.path.isdir(SCREENSHOTS_DIR):
            for file in os.listdir(SCREENSHOTS_DIR):
                if file.startswith('screenshot_') and file.endswith('.png'):
                    try:
                        os.remove(os.path.join(SCREENSHOTS_DIR, file))
                    except Exception:
                        pass
    except Exception as e:
        print(f"Cleanup files error: {e}")

    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.quit()
    except Exception as e:
        print(f"Cleanup Qt error: {e}")

    def force_exit():
        os._exit(0)

    threading.Timer(1.0, force_exit).start()


def safe_cleanup(signum=None, frame=None):
    try:
        cleanup()
    except Exception as e:
        print(f"Safe cleanup error: {e}")
    finally:
        if signum is not None:
            sys.exit(0)


atexit.register(safe_cleanup)
signal.signal(signal.SIGINT, safe_cleanup)
signal.signal(signal.SIGTERM, safe_cleanup)



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
        print(f"Error pressing key: {e}")



def add_timezone_to_str(time_str: str) -> str:
    local_tz = get_localzone()
    now = datetime.datetime.now(local_tz)
    total_seconds = local_tz.utcoffset(now).total_seconds()
    utc_offset_hours = total_seconds / 3600

    hours = int(utc_offset_hours)
    minutes = int(abs(utc_offset_hours - hours) * 60)

    if minutes == 0:
        utc_str = f"UTC{hours:+d}"
    else:
        utc_str = f"UTC{hours:+d}:{minutes:02d}"

    return f"{time_str} ({utc_str})"



def init_local_storage():
    from core.settings import init_settings
    try:
        init_settings()
        return True
    except Exception as e:
        gui_print(f"[ERROR] Не удалось инициализировать базу настроек: {e}")
        return False