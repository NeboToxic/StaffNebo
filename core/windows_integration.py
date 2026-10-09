import os
import sys

APP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_NAME = "NeboProject"


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
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
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


def set_taskbar_hidden(window, hidden: bool) -> bool:
    """Hide/show the app from the Windows taskbar while keeping the tray icon."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = wintypes.HWND(int(window.winId()))
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
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
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        SWP_NOACTIVATE = 0x0010
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE)
        return True
    except Exception as exc:
        print(f"[ERROR] Не удалось изменить режим панели задач: {exc}")
        return False
