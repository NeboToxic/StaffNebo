import os
import sys
import subprocess
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QMenu, QAction, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

from ui.title_bar import TitleBar
from ui.theme_manager import (
    THEMES, accent_button_style, bind_label_style, log_output_style,
    main_window_stylesheet, session_label_style, stat_label_style, toolbar_button_style,
)
from core.helpers import gui_print, make_sound
from core.settings import load_settings, update_settings
from core.globals import (
    gui_messages_buffer, platform, vk_user_id,
    my_nickname, using_sounds_in_program,
    log_display_mode, put_do_logov,
    all_mutes, all_warns, all_kicks, previous_sender
)
from config import APP_NAME, VERSION
from domain.parser import parse_moderation_line
from services.operation_queue import OperationQueue

from threads.log_monitor import LogMonitorThread
from threads.message_sender import MessageSenderThread
from threads.action_threads import ScreenshotThread


class MainWindow(QWidget):
    """Main panel content; lives inside the app shell stacked pages."""

    sound_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.themes = THEMES

        self.current_theme = self._load_theme()
        self.setStyleSheet(self._get_theme_stylesheet())

        self.ops = OperationQueue(self, processing_delay=1.5)
        self.ops.log_signal.connect(self.log_message)
        self.ops.sound_signal.connect(self._play_sound)
        self.ops.stats_signal.connect(lambda _t: self.update_stats())
        self.ops.warning_signal.connect(gui_print)

        self.session_start_time = datetime.datetime.now()
        self.session_timer = QTimer()
        self.session_timer.timeout.connect(self._update_session_timer)
        self.session_timer.start(1000)

        self.filter_new_messages = (log_display_mode == 'chat')

        self.current_bind_keycode = None
        self.setting_bind_mode = False
        self.keyboard_listener = None
        self._screenshot_busy = False
        self._hotkey_held = False
        self._hotkey_shot_armed = True

        self._init_ui()
        self._flush_message_buffer()

        self.sound_requested.connect(self._play_sound)

        self._load_bind()
        self._apply_theme(self.current_theme)
        self._load_platform()

        self.logs_path = put_do_logov
        self.log_monitor = LogMonitorThread(self.logs_path)
        self.log_monitor.update_signal.connect(self.log_message)
        self.log_monitor.log_line_signal.connect(self.process_log_line)

    def _load_theme(self):
        t = load_settings().theme
        if t in self.themes:
            return t
        return "Dark Orange"

    def _save_theme(self, tn):
        try:
            update_settings(theme=tn)
        except Exception as e:
            gui_print(f"[ERROR] Ошибка сохранения темы: {e}")

    def _get_theme_stylesheet(self):
        return main_window_stylesheet(self.current_theme)

    def _show_theme_menu(self):
        m = QMenu(self)
        m.setStyleSheet(self._get_theme_stylesheet())
        for tn in self.themes:
            a = QAction(tn, self)
            a.triggered.connect(lambda checked, n=tn: self._apply_theme(n))
            m.addAction(a)
        m.exec_(self.theme_btn.mapToGlobal(self.theme_btn.rect().bottomLeft()))

    def _apply_theme(self, tn):
        if tn not in self.themes:
            return
        self.current_theme = tn
        self.setStyleSheet(self._get_theme_stylesheet())
        self._update_theme_specific_styles()
        self._update_log_mode_btn_style()
        self._recolor_existing_messages()
        self._save_theme(tn)
        gui_print(f"[SYSTEM] Тема изменена на: {tn}")

    def _update_theme_specific_styles(self):
        if hasattr(self, 'title_bar'):
            self.title_bar.apply_theme(self.current_theme)
        toolbar = toolbar_button_style(self.current_theme)
        self.log_mode_btn.setStyleSheet(toolbar)
        self.theme_btn.setStyleSheet(toolbar)
        self.bind_label.setStyleSheet(bind_label_style(self.current_theme))
        stats = stat_label_style(self.current_theme)
        self.mutes_label.setStyleSheet(stats)
        self.warns_label.setStyleSheet(stats)
        self.kicks_label.setStyleSheet(stats)
        self.session_timer_label.setStyleSheet(session_label_style(self.current_theme))
        self.log_output.setStyleSheet(log_output_style(self.current_theme))
        self.update()

    def _load_platform(self):
        global platform, vk_user_id
        try:
            settings = load_settings()
            platform = settings.platform or 'telegram'
            vk_user_id = settings.vk_user_id or ''
        except Exception as e:
            gui_print(f"[ERROR] Ошибка загрузки платформы: {e}")

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(0)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)

        self.title_bar = TitleBar(f"{APP_NAME} v{VERSION} - Панель управления", self)
        self.title_label = self.title_bar.title_label

        self.log_mode_btn = QPushButton()
        self.log_mode_btn.setFixedSize(85, 24)
        self.log_mode_btn.setToolTip("Переключить режим отображения логов")
        self.log_mode_btn.clicked.connect(self._toggle_log_display_mode)
        self.title_bar.add_widget(self.log_mode_btn)

        self.theme_btn = QPushButton("Тема")
        self.theme_btn.setFixedSize(70, 24)
        self.theme_btn.setToolTip("Сменить тему")
        self.theme_btn.clicked.connect(self._show_theme_menu)
        self.title_bar.add_widget(self.theme_btn)


        self.minimize_btn = self.title_bar.minimize_btn
        self.maximize_btn = self.title_bar.maximize_btn
        self.close_btn = self.title_bar.close_btn
        main_layout.addWidget(self.title_bar)

        top_panel_layout = QHBoxLayout()
        stats_layout = QHBoxLayout()
        self.mutes_label = QLabel("Муты: 0")
        self.warns_label = QLabel("Варны: 0")
        self.kicks_label = QLabel("Кики: 0")
        for l in [self.mutes_label, self.warns_label, self.kicks_label]:
            stats_layout.addWidget(l)
        top_panel_layout.addLayout(stats_layout)
        top_panel_layout.addStretch()
        self.session_timer_label = QLabel("Сессия: 00:00")
        self.session_timer_label.setAlignment(Qt.AlignCenter)
        top_panel_layout.addWidget(self.session_timer_label)
        content_layout.addLayout(top_panel_layout)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.log_output, 1)

        buttons_layout = QHBoxLayout()
        self.bind_btn = QPushButton("Изменить бинд скриншота")
        self.bind_btn.clicked.connect(self._start_binding)
        buttons_layout.addWidget(self.bind_btn)
        self.clear_btn = QPushButton("Очистить логи")
        self.clear_btn.clicked.connect(self._clear_logs)
        buttons_layout.addWidget(self.clear_btn)
        content_layout.addLayout(buttons_layout)

        self.bind_label = QLabel("Текущий бинд: Не задан")
        content_layout.addWidget(self.bind_label)

        main_layout.addWidget(content_widget)

        self.allowed_keys = (
            list(range(Qt.Key_A, Qt.Key_Z + 1)) + list(range(Qt.Key_0, Qt.Key_9 + 1)) + list(range(Qt.Key_F1, Qt.Key_F24 + 1)) +
            [Qt.Key_Insert, Qt.Key_Delete, Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Print, Qt.Key_Pause,
             Qt.Key_Escape, Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt,
             Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Backspace,
             Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock, Qt.Key_Menu, Qt.Key_Backtab, Qt.Key_QuoteLeft,
             Qt.Key_Backslash, Qt.Key_BracketLeft, Qt.Key_BracketRight, Qt.Key_Semicolon, Qt.Key_Apostrophe, Qt.Key_Comma,
             Qt.Key_Period, Qt.Key_Slash, Qt.Key_Equal, Qt.Key_Minus, Qt.Key_AsciiTilde, Qt.Key_Exclam, Qt.Key_At,
             Qt.Key_NumberSign, Qt.Key_Dollar, Qt.Key_Percent, Qt.Key_Ampersand, Qt.Key_Asterisk, Qt.Key_Plus, Qt.Key_Less,
             Qt.Key_Greater, Qt.Key_Underscore, Qt.Key_Question, Qt.Key_ParenLeft, Qt.Key_ParenRight]
        )
        self._update_log_mode_btn_style()

    def setup_initial_display(self):
        global log_display_mode
        self.filter_new_messages = (log_display_mode == 'chat')
        self._update_log_mode_btn_style()
        self.log_message(f"[SYSTEM] Режим отображения новых логов: {'Только чат' if self.filter_new_messages else 'Все логи'}")

    def _flush_message_buffer(self):
        global gui_messages_buffer
        for m in gui_messages_buffer:
            self.log_message(m)
        gui_messages_buffer.clear()

    def update_stats(self):
        self.mutes_label.setText(f"Муты: {all_mutes}")
        self.warns_label.setText(f"Варны: {all_warns}")
        self.kicks_label.setText(f"Кики: {all_kicks}")

    def _update_session_timer(self):
        elapsed = datetime.datetime.now() - self.session_start_time
        ts = int(elapsed.total_seconds())
        d, h = ts // 86400, (ts % 86400) // 3600
        m, s = (ts % 3600) // 60, ts % 60
        if d > 0:
            self.session_timer_label.setText(f"Сессия: {d:02d}:{h:02d}:{m:02d}:{s:02d}")
        elif h > 0:
            self.session_timer_label.setText(f"Сессия: {h:02d}:{m:02d}:{s:02d}")
        else:
            self.session_timer_label.setText(f"Сессия: {m:02d}:{s:02d}")

    def _clear_logs(self):
        self.log_output.clear()

    def _toggle_log_display_mode(self):
        global log_display_mode
        log_display_mode = 'chat' if log_display_mode == 'all' else 'all'
        self.filter_new_messages = (log_display_mode == 'chat')
        self._update_log_mode_btn_style()
        self._save_log_display_mode()
        gui_print(f"[SYSTEM] Режим логов: {'Только чат' if self.filter_new_messages else 'Все логи'}")

    def _update_log_mode_btn_style(self):
        if hasattr(self, 'log_mode_btn'):
            self.log_mode_btn.setText("Все логи" if log_display_mode == 'all' else "Только чат")

    def _save_log_display_mode(self):
        global log_display_mode
        try:
            update_settings(log_display_mode=log_display_mode)
        except Exception as e:
            gui_print(f"[ERROR] Ошибка сохранения режима отображения: {e}")

    def log_message(self, message):
        if not isinstance(message, str):
            message = str(message)
        if self.filter_new_messages:
            if not any(t in message for t in ['[SYSTEM]', '[ERROR]', '[WARNING]', '[CHAT]']):
                if '[CHAT]' not in message:
                    return
        t = self.themes[self.current_theme]
        if self.current_theme == "Light White":
            if "[ERROR]" in message:
                cm = f'<span style="color: {t["error"]}; font-weight: bold;">{message}</span>'
            elif "[WARNING]" in message:
                cm = f'<span style="color: {t["warning"]}; font-weight: bold;">{message}</span>'
            elif "[SYSTEM]" in message:
                cm = f'<span style="color: {t["accent"]}; font-weight: bold;">{message}</span>'
            elif "[CHAT]" in message:
                cm = f'<span style="color: {t["chat"]}; font-weight: bold;">{message}</span>'
            else:
                cm = f'<span style="color: {t["text"]};">{message}</span>'
        else:
            if "[ERROR]" in message:
                cm = f'<span style="color: {t["error"]}; font-weight: bold;">{message}</span>'
            elif "[WARNING]" in message:
                cm = f'<span style="color: {t["warning"]}; font-weight: bold;">{message}</span>'
            elif "[SYSTEM]" in message:
                cm = f'<span style="color: {t["accent"]}; font-weight: bold;">{message}</span>'
            elif "[CHAT]" in message:
                cm = f'<span style="color: {t["chat"]}; font-weight: bold; text-shadow: 0 0 2px rgba(255,255,255,0.3);">{message}</span>'
            else:
                cm = f'<span style="color: {t["text"]};">{message}</span>'
        sb = self.log_output.verticalScrollBar()
        was_bottom = sb.value() == sb.maximum()
        self.log_output.append(cm)
        if was_bottom:
            sb.setValue(sb.maximum())

    def _recolor_existing_messages(self):
        if not self.log_output.toPlainText():
            return
        sb = self.log_output.verticalScrollBar()
        cp = sb.value()
        at_bottom = sb.value() == sb.maximum()
        pt = self.log_output.toPlainText()
        self.log_output.clear()
        t = self.themes[self.current_theme]
        for line in pt.split('\n'):
            if not line.strip():
                continue
            if self.current_theme == "Light White":
                if "[ERROR]" in line:
                    cm = f'<span style="color: {t["error"]}; font-weight: bold;">{line}</span>'
                elif "[WARNING]" in line:
                    cm = f'<span style="color: {t["warning"]}; font-weight: bold;">{line}</span>'
                elif "[SYSTEM]" in line:
                    cm = f'<span style="color: {t["accent"]}; font-weight: bold;">{line}</span>'
                elif "[CHAT]" in line:
                    cm = f'<span style="color: {t["chat"]}; font-weight: bold;">{line}</span>'
                else:
                    cm = f'<span style="color: {t["text"]};">{line}</span>'
            else:
                if "[ERROR]" in line:
                    cm = f'<span style="color: {t["error"]}; font-weight: bold;">{line}</span>'
                elif "[WARNING]" in line:
                    cm = f'<span style="color: {t["warning"]}; font-weight: bold;">{line}</span>'
                elif "[SYSTEM]" in line:
                    cm = f'<span style="color: {t["accent"]}; font-weight: bold;">{line}</span>'
                elif "[CHAT]" in line:
                    cm = f'<span style="color: {t["chat"]}; font-weight: bold; text-shadow: 0 0 2px rgba(255,255,255,0.3);">{line}</span>'
                else:
                    cm = f'<span style="color: {t["text"]};">{line}</span>'
            self.log_output.append(cm)
        if at_bottom:
            sb.setValue(sb.maximum())
        else:
            sb.setValue(cp)

    def process_log_line(self, line):
        global previous_sender, my_nickname
        if previous_sender == line:
            return
        if not self.filter_new_messages or '[CHAT]' in line:
            self.log_message(line)
        try:
            event = parse_moderation_line(line, my_nickname)
            if event is None:
                return
            previous_sender = line
            self.ops.enqueue(event)
        except Exception as e:
            self.log_message(f"[ERROR] Ошибка при обработке строки '{line}': {e}")

    def take_screenshot(self, e=None):
        # CaptureThread presses 't' for mute/warn — ignore hotkey during op.
        if getattr(self, 'ops', None) is not None and self.ops.is_busy:
            return
        if self._screenshot_busy or (
            hasattr(self, 'screenshot_thread') and self.screenshot_thread is not None
            and self.screenshot_thread.isRunning()
        ):
            gui_print("[SYSTEM] Предыдущий скриншот ещё обрабатывается...")
            return

        self._screenshot_busy = True
        self.screenshot_thread = ScreenshotThread()
        self.screenshot_thread.finished_signal.connect(
            self._on_screenshot_created, Qt.UniqueConnection
        )
        self.screenshot_thread.start()

    def _on_screenshot_created(self, success, message, filename):
        global platform
        self.log_message(message)
        if success and filename:
            self._load_platform()
            self.message_sender = MessageSenderThread('screenshot', platform, filename)
            self.message_sender.finished_signal.connect(
                self._on_screenshot_sent, Qt.UniqueConnection
            )
            self.message_sender.start()
            if using_sounds_in_program:
                self.sound_requested.emit()
        else:
            self._screenshot_busy = False

    def _on_screenshot_sent(self, success, message):
        self._screenshot_busy = False
        self.log_message(message)

    def _start_binding(self):
        if not self.setting_bind_mode:
            self.setting_bind_mode = True
            self.bind_btn.setText("Нажмите клавишу...")
            self.bind_btn.setEnabled(False)
            self.grabKeyboard()
            gui_print("[SYSTEM] Режим привязки: нажмите любую клавишу")

    def keyPressEvent(self, event):
        if self.setting_bind_mode:
            key = event.key()
            if key in [Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock]:
                event.accept()
                return
            if key in self.allowed_keys:
                self.current_bind_keycode = key
                key_name = self._get_key_name(key)
                try:
                    update_settings(bind_keycode=int(key))
                except Exception as e:
                    gui_print(f"[ERROR] Ошибка сохранения бинда: {e}")
                self.bind_label.setText(f"Текущий бинд: {key_name}")
                gui_print(f"[SYSTEM] Бинд установлен: {key_name}")
            self.setting_bind_mode = False
            self.bind_btn.setText("Изменить бинд скриншота")
            self.bind_btn.setEnabled(True)
            self.releaseKeyboard()
            self._setup_global_shortcut()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _load_bind(self):
        try:
            saved_key = load_settings().bind_keycode
            if saved_key is None:
                self.bind_label.setText("Текущий бинд: Не задан")
                return
            self.current_bind_keycode = int(saved_key)
            self.bind_label.setText(f"Текущий бинд: {self._get_key_name(self.current_bind_keycode)}")
            self._setup_global_shortcut()
        except Exception as e:
            self.bind_label.setText("Текущий бинд: Ошибка загрузки")
            gui_print(f"[ERROR] Ошибка загрузки бинда: {e}")

    def _setup_global_shortcut(self):
        import pynput.keyboard as pynput_kb
        try:
            if self.keyboard_listener is not None:
                try:
                    self.keyboard_listener.stop()
                except Exception:
                    pass
                self.keyboard_listener = None

            self._hotkey_held = False
            self._hotkey_shot_armed = True

            if self.current_bind_keycode is None:
                return

            pynput_key = self._qt_key_to_pynput(self.current_bind_keycode)
            if not pynput_key:
                return

            def _keys_match(key) -> bool:
                try:
                    if key == pynput_key:
                        return True
                    # Windows may emit both KeyCode(char=...) and vk variants.
                    if hasattr(key, 'vk') and hasattr(pynput_key, 'vk'):
                        if key.vk is not None and key.vk == pynput_key.vk:
                            return True
                    if hasattr(key, 'char') and hasattr(pynput_key, 'char'):
                        if key.char and pynput_key.char and key.char.lower() == pynput_key.char.lower():
                            return True
                except Exception:
                    return False
                return False

            def on_press(key):
                try:
                    if not _keys_match(key):
                        return
                    # Key-repeat while held must not queue more screenshots.
                    if self._hotkey_held or not self._hotkey_shot_armed:
                        return
                    self._hotkey_held = True
                    self._hotkey_shot_armed = False
                    QTimer.singleShot(0, self.take_screenshot)
                except Exception:
                    pass

            def on_release(key):
                try:
                    if _keys_match(key):
                        self._hotkey_held = False
                        self._hotkey_shot_armed = True
                except Exception:
                    pass

            self.keyboard_listener = pynput_kb.Listener(
                on_press=on_press,
                on_release=on_release,
                suppress=False,
            )
            self.keyboard_listener.start()
        except Exception as e:
            gui_print(f"[ERROR] Ошибка настройки горячей клавиши: {e}")

    def _qt_key_to_pynput(self, qt_key_code):
        import pynput.keyboard as pynput_kb
        from pynput.keyboard import Key
        if Qt.Key_A <= qt_key_code <= Qt.Key_Z:
            return pynput_kb.KeyCode.from_char(chr(qt_key_code).lower())
        if Qt.Key_0 <= qt_key_code <= Qt.Key_9:
            return pynput_kb.KeyCode.from_char(chr(qt_key_code))
        if Qt.Key_F1 <= qt_key_code <= Qt.Key_F24:
            return getattr(Key, f'f{qt_key_code - Qt.Key_F1 + 1}')
        mapping = {
            Qt.Key_Insert: Key.insert, Qt.Key_Delete: Key.delete,
            Qt.Key_Home: Key.home, Qt.Key_End: Key.end,
            Qt.Key_PageUp: Key.page_up, Qt.Key_PageDown: Key.page_down,
            Qt.Key_Print: Key.print_screen, Qt.Key_Pause: Key.pause,
            Qt.Key_Escape: Key.esc, Qt.Key_Left: Key.left,
            Qt.Key_Right: Key.right, Qt.Key_Up: Key.up, Qt.Key_Down: Key.down,
            Qt.Key_Shift: Key.shift, Qt.Key_Control: Key.ctrl,
            Qt.Key_Alt: Key.alt, Qt.Key_Space: Key.space,
            Qt.Key_Return: Key.enter, Qt.Key_Enter: Key.enter,
            Qt.Key_Tab: Key.tab, Qt.Key_Backspace: Key.backspace,
            Qt.Key_CapsLock: Key.caps_lock, Qt.Key_NumLock: Key.num_lock,
        }
        if qt_key_code in mapping:
            return mapping[qt_key_code]
        return None

    def _get_key_name(self, key_code):
        if key_code is None:
            return "Не задан"
        if Qt.Key_A <= key_code <= Qt.Key_Z:
            return chr(key_code)
        if Qt.Key_0 <= key_code <= Qt.Key_9:
            return chr(key_code)
        if Qt.Key_F1 <= key_code <= Qt.Key_F24:
            return f"F{key_code - Qt.Key_F1 + 1}"
        names = {
            Qt.Key_Insert: "Insert", Qt.Key_Delete: "Delete",
            Qt.Key_Home: "Home", Qt.Key_End: "End",
            Qt.Key_PageUp: "Page Up", Qt.Key_PageDown: "Page Down",
            Qt.Key_Print: "Print Screen", Qt.Key_Pause: "Pause",
            Qt.Key_Escape: "Esc", Qt.Key_Left: "←", Qt.Key_Right: "→",
            Qt.Key_Up: "↑", Qt.Key_Down: "↓", Qt.Key_Shift: "Shift",
            Qt.Key_Control: "Ctrl", Qt.Key_Alt: "Alt",
            Qt.Key_Space: "Space", Qt.Key_Return: "Enter",
            Qt.Key_Enter: "Enter", Qt.Key_Tab: "Tab",
            Qt.Key_Backspace: "Backspace", Qt.Key_CapsLock: "Caps Lock",
        }
        return names.get(key_code, f"Key_{key_code}")

    def _play_sound(self):
        make_sound()

    def shutdown(self):
        try:
            if hasattr(self, 'session_timer'):
                self.session_timer.stop()
            if hasattr(self, 'log_monitor'):
                self.log_monitor.stop()
            if hasattr(self, 'ops'):
                self.ops.stop()
            if hasattr(self, 'message_sender'):
                self.message_sender.stop()
            for attr in ['screenshot_thread', 'download_thread']:
                if hasattr(self, attr) and getattr(self, attr) is not None:
                    getattr(self, attr).quit()
            if hasattr(self, 'keyboard_listener') and self.keyboard_listener:
                self.keyboard_listener.stop()
        except Exception as e:
            gui_print(f"[ERROR] Ошибка при закрытии: {e}")