import ctypes
import sys
from ctypes import wintypes
from PIL import ImageGrab


def monitors():
    if sys.platform!='win32':return []
    result=[]
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
    def visit(handle,dc,rect,data):
        r=rect.contents;result.append((r.left,r.top,r.right,r.bottom));return True
    ctypes.windll.user32.EnumDisplayMonitors(None,None,callback(visit),0)
    return result


def windows():
    if sys.platform!='win32':return []
    user=ctypes.windll.user32; result=[]
    # HWND is pointer-sized; explicit prototypes prevent truncation on x64.
    for name in ('IsWindowVisible','IsIconic'):
        function=getattr(user,name);function.argtypes=[wintypes.HWND];function.restype=wintypes.BOOL
    user.GetWindowTextLengthW.argtypes=[wintypes.HWND];user.GetWindowTextLengthW.restype=ctypes.c_int
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int];user.GetWindowTextW.restype=ctypes.c_int
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(hwnd,data):
        if user.IsWindowVisible(hwnd) and not user.IsIconic(hwnd):
            length=user.GetWindowTextLengthW(hwnd)
            if length:
                text=ctypes.create_unicode_buffer(length+1);user.GetWindowTextW(hwnd,text,length+1)
                result.append((int(hwnd),text.value))
        return True
    user.EnumWindows(callback(visit),0)
    return result


def capture_image(settings):
    box=None
    if settings.capture_mode=='monitor':
        items=monitors()
        if not 0<=int(settings.capture_monitor)<len(items):raise RuntimeError('Выбранный монитор недоступен')
        box=items[int(settings.capture_monitor)]
    elif settings.capture_mode=='window':
        match=[(h,t) for h,t in windows() if settings.capture_window_title.casefold() in t.casefold()]
        if not settings.capture_window_title or not match:raise RuntimeError('Окно захвата не найдено или свёрнуто')
        user=ctypes.windll.user32; rect=wintypes.RECT(); point=wintypes.POINT()
        hwnd=wintypes.HWND(match[0][0])
        if not user.GetClientRect(hwnd,ctypes.byref(rect)) or not user.ClientToScreen(hwnd,ctypes.byref(point)):
            raise RuntimeError('Не удалось определить область окна')
        box=(point.x,point.y,point.x+rect.right,point.y+rect.bottom)
    elif settings.capture_mode!='screen':raise ValueError('Неизвестный режим захвата')
    if box and (box[2]<=box[0] or box[3]<=box[1]):raise RuntimeError('Область захвата пуста')
    return ImageGrab.grab(bbox=box,all_screens=True)
