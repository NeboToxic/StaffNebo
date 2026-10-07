import os
import sys

APP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_NAME = "NeboProject"
CRISTALIX_RUN_NAME = "NeboProjectCristalixWatcher"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "main.py"))
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return f'"{pythonw}" "{main_py}"'


def set_startup_enabled(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_RUN_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as exc:
        print(f"[ERROR] Не удалось изменить автозапуск Windows: {exc}")
        return False


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, APP_RUN_NAME)
            return bool(value)
    except Exception:
        return False



def _watcher_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --cristalix-watch'
    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "main.py"))
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return f'"{pythonw}" "{main_py}" --cristalix-watch'


def set_cristalix_startup_enabled(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, CRISTALIX_RUN_NAME, 0, winreg.REG_SZ, _watcher_command())
            else:
                try:
                    winreg.DeleteValue(key, CRISTALIX_RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as exc:
        print(f"[ERROR] Не удалось изменить автозапуск с Cristalix: {exc}")
        return False


def is_cristalix_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, CRISTALIX_RUN_NAME)
            return bool(value)
    except Exception:
        return False


def set_taskbar_hidden(window, hidden: bool) -> bool:
    """Hide/show the top-level window from the Windows taskbar while keeping tray access."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = wintypes.HWND(int(window.winId()))
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        SW_HIDE = 0
        SW_SHOW = 5
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        SWP_FRAMECHANGED = 0x0020
        HWND_TOP = 0
        user32 = ctypes.windll.user32
        get_long = user32.GetWindowLongW
        set_long = user32.SetWindowLongW
        get_long.restype = wintypes.LONG
        set_long.restype = wintypes.LONG
        style = get_long(hwnd, GWL_EXSTYLE)
        if hidden:
            style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        else:
            style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        set_long(hwnd, GWL_EXSTYLE, style)
        # Recreate the shell/taskbar registration deterministically.
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        user32.ShowWindow(hwnd, SW_SHOW)
        return True
    except Exception as exc:
        print(f"[ERROR] Не удалось изменить режим панели задач: {exc}")
        return False

