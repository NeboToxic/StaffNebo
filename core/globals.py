from core.settings import load_settings


main_window = None
gui_ready = False
gui_messages_buffer = []

bot_id = None
chat_id = None
logs = None
my_nickname = None
using_sounds_in_program = None
platform = 'telegram'
vk_user_id = ''
vk_token = ''
screenshot_delay = 0.7
log_display_mode = 'all'

all_mutes = 0
all_warns = 0
all_kicks = 0

previous_sender = None
last_line_access = ''
last_line_access2 = ''
access = True

my_id = 0
put_do_logov = ""


def apply_settings(settings=None):
    global platform, vk_user_id, vk_token, chat_id, bot_id, logs, my_nickname
    global using_sounds_in_program, screenshot_delay, log_display_mode
    global my_id, put_do_logov

    if settings is None:
        settings = load_settings()

    platform = settings.platform or 'telegram'
    vk_user_id = settings.vk_user_id or ''
    vk_token = settings.vk_token or ''
    chat_id = settings.chat_id or '0'
    bot_id = settings.bot_id or '0:default'
    logs = settings.logs or ''
    my_nickname = settings.nick or ''
    using_sounds_in_program = settings.use_sound
    screenshot_delay = settings.screenshot_delay if settings.screenshot_delay is not None else 0.7
    log_display_mode = settings.log_display_mode or 'all'
    put_do_logov = logs

    try:
        my_id = int(chat_id) if chat_id and str(chat_id).isdigit() else 0
    except (ValueError, TypeError):
        my_id = 0

    print("[SYSTEM] Глобальные переменные загружены из SQLite")
    print(f"[SYSTEM] platform={platform}, vk_user_id={vk_user_id}, chat_id={chat_id}")
    return settings


def reload_globals_from_config():
    try:
        apply_settings()
    except Exception as e:
        print(f"[ERROR] Ошибка загрузки настроек из БД: {e}")
