import sys
import os


def _get_data_dir():
    if sys.platform == 'win32':
        # Windows: C:\Users\<User>\AppData\Roaming\HelperTool
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        # Mac/Linux: ~/.helpertool
        base = os.path.expanduser('~')
    return os.path.join(base, 'StaffControl')


DATA_DIR = _get_data_dir()
SCREENSHOTS_DIR = os.path.join(DATA_DIR, 'screenshots')
DB_PATH = os.path.join(DATA_DIR, 'staffcontrol.db')


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def data_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def screenshot_path(photoid_or_filename: str) -> str:
    name = photoid_or_filename
    if not str(name).lower().endswith('.png'):
        name = f'screenshot_{name}.png'
    return os.path.join(SCREENSHOTS_DIR, name)