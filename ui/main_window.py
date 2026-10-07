import os
import sys
import subprocess
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QMenu, QAction, QSizePolicy, QFrame, QCheckBox, QSlider, QSystemTrayIcon, QStyle
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QDateTime
from PyQt5.QtGui import QPainter, QPixmap, QIcon

from ui.title_bar import TitleBar
from ui.theme_manager import (
    THEMES, accent_button_style, bind_label_style, log_output_style,
    main_window_stylesheet, session_label_style, stat_label_style, toolbar_button_style,
)
from core.helpers import gui_print, make_sound
from core.settings import load_settings, update_settings
from core.windows_integration import set_taskbar_hidden
from core.paths import resource_path
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
    bind_captured = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.themes = {'Небо': THEMES['Небо']}
        settings = load_settings()
        self.current_theme = 'Небо'
        self.panel_opacity = max(0, min(100, int(getattr(settings, 'panel_opacity', 78))))
        self.hide_from_taskbar = bool(getattr(settings, 'hide_from_taskbar', False))
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
        self._binding_listener_active = False
        self.tray_icon = None
        self.tray_menu = None

        self._init_ui()
        self._flush_message_buffer()

        self.sound_requested.connect(self._play_sound)

        self.bind_captured.connect(self._on_bind_captured)
        self._load_bind()
        self._apply_theme(self.current_theme)
        QTimer.singleShot(0, self._apply_taskbar_mode)
        self._load_platform()

        self.logs_path = put_do_logov
        self.log_monitor = LogMonitorThread(self.logs_path)
        self.log_monitor.update_signal.connect(self.log_message)
        self.log_monitor.log_line_signal.connect(self.process_log_line)

    def _apply_taskbar_mode(self):
        top = self.window()
        if hasattr(top, 'apply_taskbar_mode'):
            top.apply_taskbar_mode(self.hide_from_taskbar)
        else:
            set_taskbar_hidden(top, self.hide_from_taskbar)

    def minimize_to_tray(self):
        top = self.window()
        if hasattr(top, 'minimize_to_tray'):
            top.minimize_to_tray()
        else:
            top.showMinimized()

    def _load_theme(self):
        t = load_settings().theme
        if t in self.themes:
            return t
        return "Небо"

    def _save_theme(self, tn):
        try:
            update_settings(theme=tn)
        except Exception as e:
            gui_print(f"[ERROR] Ошибка сохранения темы: {e}")

    def _get_theme_stylesheet(self):
        return main_window_stylesheet(self.current_theme, self.panel_opacity)

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
        self.bind_label.setStyleSheet(bind_label_style(self.current_theme))
        t = self.themes[self.current_theme]
        alpha = max(0, min(100, self.panel_opacity)) * 255 // 100
        stat_bg = f"rgba(17,17,22,{alpha})" if self.current_theme == 'Небо' else t['secondary']
        stat_base = (f"background: {stat_bg}; border: 1px solid {t['secondary_hover']}; "
                     f"border-radius: 12px; padding: 13px 15px; min-height: 52px; font-size: 12px; font-weight: 800;")
        self.mutes_label.setStyleSheet(stat_base + f"color: {t['accent']};")
        self.warns_label.setStyleSheet(stat_base + f"color: {t['warning']};")
        self.kicks_label.setStyleSheet(stat_base + f"color: {t['error']};")
        self.session_timer_label.setStyleSheet(session_label_style(self.current_theme))
        self.log_output.setStyleSheet(log_output_style(self.current_theme, self.panel_opacity))
        if hasattr(self, 'status_label'):
            self.status_label.setStyleSheet(f"color: {self.themes[self.current_theme]['accent']}; background: transparent; font-size: 10px; font-weight: bold; padding: 4px 8px;")
        if hasattr(self, 'bind_label'):
            self.bind_label.setStyleSheet(bind_label_style(self.current_theme))
        if hasattr(self, 'opacity_slider'):
            self.opacity_slider.setStyleSheet(f"QSlider::groove:horizontal {{ height: 5px; background: #3B1A20; border-radius: 3px; }} QSlider::sub-page:horizontal {{ background: #FF1738; border-radius: 3px; }} QSlider::handle:horizontal {{ background: #FF1738; width: 15px; height: 15px; margin: -5px 0; border-radius: 8px; }}")
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
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = TitleBar(f"Небо  •  NeboProject  •  v{VERSION}", self)
        self.title_label = self.title_bar.title_label

        self.status_label = QLabel("●  ОНЛАЙН")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.title_bar.add_widget(self.status_label)

        self.log_mode_btn = QPushButton()
        self.log_mode_btn.setFixedSize(96, 28)
        self.log_mode_btn.setToolTip("Переключить режим отображения логов")
        self.log_mode_btn.clicked.connect(self._toggle_log_display_mode)
        self.title_bar.add_widget(self.log_mode_btn)

        self.minimize_btn = self.title_bar.minimize_btn
        self.maximize_btn = self.title_bar.maximize_btn
        self.close_btn = self.title_bar.close_btn
        main_layout.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(22, 14, 22, 20)
        body_layout.setSpacing(18)

        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        hero = QHBoxLayout()
        hero.setSpacing(12)
        hero_title_box = QVBoxLayout()
        hero_title_box.setSpacing(2)
        header = QLabel("Панель управления")
        header.setObjectName("pageTitle")
        hero_title_box.addWidget(header)
        subtitle = QLabel("Небо любит Нику")
        subtitle.setObjectName("pageSubtitle")
        hero_title_box.addWidget(subtitle)
        hero.addLayout(hero_title_box, 1)
        project_badge = QLabel("Н Е Б О   P R O J E C T")
        project_badge.setObjectName("projectBadge")
        project_badge.setAlignment(Qt.AlignCenter)
        hero.addWidget(project_badge)
        self.session_timer_label = QLabel("Сессия: 00:00")
        self.session_timer_label.setObjectName("sessionCard")
        self.session_timer_label.setAlignment(Qt.AlignCenter)
        hero.addWidget(self.session_timer_label)
        content_layout.addLayout(hero)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.mutes_label = QLabel("◉  МУТЫ\n0")
        self.warns_label = QLabel("⚠  ВАРНЫ\n0")
        self.kicks_label = QLabel("➜  КИКИ\n0")
        self.mutes_label.setObjectName("statMutes")
        self.warns_label.setObjectName("statWarns")
        self.kicks_label.setObjectName("statKicks")
        for label in (self.mutes_label, self.warns_label, self.kicks_label):
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            stats_row.addWidget(label, 1)
        content_layout.addLayout(stats_row)

        log_header = QHBoxLayout()
        log_title = QLabel("⌁  Журнал событий")
        log_title.setObjectName("sectionTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.setFixedHeight(32)
        self.clear_btn.clicked.connect(self._clear_logs)
        log_header.addWidget(self.clear_btn)
        content_layout.addLayout(log_header)

        self.log_output = QTextEdit()
        self.log_output.setObjectName("logOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_output.setPlaceholderText("Здесь появятся события мониторинга…")
        content_layout.addWidget(self.log_output, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.bind_btn = QPushButton("⌨  Изменить бинд")
        self.bind_btn.setObjectName("primaryButton")
        self.bind_btn.setFixedHeight(40)
        self.bind_btn.clicked.connect(self._start_binding)
        bottom.addWidget(self.bind_btn)

        self.bind_label = QLabel("Текущий бинд: Не задан")
        self.bind_label.setObjectName("bindLabel")
        self.bind_label.setAlignment(Qt.AlignCenter)
        self.bind_label.setMinimumWidth(190)
        bottom.addWidget(self.bind_label)

        shot_btn = QPushButton("▣  Сделать скриншот")
        shot_btn.setObjectName("secondaryButton")
        shot_btn.setFixedHeight(40)
        shot_btn.clicked.connect(self.take_screenshot)
        bottom.addWidget(shot_btn)
        content_layout.addLayout(bottom)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addStretch()
        opacity_title = QLabel("Фон панелей:")
        opacity_title.setObjectName("panelControlLabel")
        controls.addWidget(opacity_title)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(self.panel_opacity)
        self.opacity_slider.setFixedWidth(130)
        self.opacity_slider.valueChanged.connect(self._on_panel_opacity_changed)
        controls.addWidget(self.opacity_slider)
        self.opacity_value = QLabel(f"{self.panel_opacity}%")
        self.opacity_value.setMinimumWidth(42)
        self.opacity_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        controls.addWidget(self.opacity_value)
        self.tray_checkbox = QCheckBox("Скрывать в панели задач")
        self.tray_checkbox.setChecked(self.hide_from_taskbar)
        self.tray_checkbox.stateChanged.connect(self._on_tray_mode_changed)
        controls.addWidget(self.tray_checkbox)
        content_layout.addLayout(controls)
        body_layout.addWidget(content, 1)

        # Правая панель в стиле референса: статус, часы, быстрые действия, статистика и цитата.
        sidebar = QFrame()
        sidebar.setObjectName("sidePanel")
        sidebar.setMinimumWidth(270)
        sidebar.setMaximumWidth(315)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(12)

        status_card = QFrame()
        status_card.setObjectName("sideCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        online = QLabel("●  ОНЛАЙН")
        online.setObjectName("onlineTitle")
        status_layout.addWidget(online)
        status_text = QLabel("Подключение активно")
        status_text.setObjectName("mutedText")
        status_layout.addWidget(status_text)
        self.clock_label = QLabel(QDateTime.currentDateTime().toString("dd.MM.yyyy\nHH:mm"))
        self.clock_label.setObjectName("bigClock")
        status_layout.addWidget(self.clock_label)
        self.clock_day_label = QLabel(QDateTime.currentDateTime().toString("dddd").capitalize())
        self.clock_day_label.setObjectName("mutedText")
        status_layout.addWidget(self.clock_day_label)
        side_layout.addWidget(status_card)

        day_card = QFrame()
        day_card.setObjectName("sideCard")
        day_layout = QVBoxLayout(day_card)
        day_layout.setContentsMargins(14, 14, 14, 14)
        day_title = QLabel("Статистика за день")
        day_title.setObjectName("sideTitle")
        day_layout.addWidget(day_title)
        self.day_mutes = QLabel("◉   Муты                                      0")
        self.day_warns = QLabel("⚠   Варны                                     0")
        self.day_kicks = QLabel("➜   Кики                                      0")
        for w in (self.day_mutes, self.day_warns, self.day_kicks):
            w.setObjectName("sideStat")
            day_layout.addWidget(w)
        side_layout.addWidget(day_card)

        quote = QFrame()
        quote.setObjectName("quoteCard")
        ql = QVBoxLayout(quote)
        ql.setContentsMargins(16, 16, 16, 16)
        q = QLabel("«Порядок рождается\nиз дисциплины.»\n\n— Небо")
        q.setObjectName("quoteText")
        ql.addWidget(q)
        side_layout.addWidget(quote)
        side_layout.addStretch(1)

        body_layout.addWidget(sidebar)
        main_layout.addWidget(body, 1)
        self._update_log_mode_btn_style()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        pixmap = getattr(self, '_nebo_bg_pixmap', None)
        if pixmap is None:
            pixmap = QPixmap(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'path', 'nebo_red_bg.png'))
            self._nebo_bg_pixmap = pixmap
        if not pixmap.isNull():
            painter.drawPixmap(self.rect(), pixmap)
            painter.fillRect(self.rect(), Qt.black if False else Qt.transparent)
        super().paintEvent(event)

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
        self.mutes_label.setText(f"◉  МУТЫ\n{all_mutes}")
        self.warns_label.setText(f"⚠  ВАРНЫ\n{all_warns}")
        self.kicks_label.setText(f"➜  КИКИ\n{all_kicks}")
        if hasattr(self, 'day_mutes'):
            self.day_mutes.setText(f"◉   Муты                                      {all_mutes}")
            self.day_warns.setText(f"⚠   Варны                                     {all_warns}")
            self.day_kicks.setText(f"➜   Кики                                      {all_kicks}")

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
        if hasattr(self, 'clock_label'):
            now = QDateTime.currentDateTime()
            self.clock_label.setText(now.toString("dd.MM.yyyy\nHH:mm"))
            self.clock_day_label.setText(now.toString("dddd").capitalize())

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
        """Enter global key-capture mode.

        Binding is captured with pynput rather than Qt key events. This makes
        the bind independent of the current keyboard layout and lets us
        distinguish physical left/right modifier keys (Alt/Ctrl/Shift/Win),
        CapsLock, media keys and other keys exposed by Windows.
        """
        if self.setting_bind_mode:
            return
        self.setting_bind_mode = True
        self.bind_btn.setText("Нажмите любую клавишу...")
        self.bind_btn.setEnabled(False)
        gui_print("[SYSTEM] Режим привязки: нажмите любую клавишу")
        self._ensure_keyboard_listener()

    def _on_bind_captured(self, key):
        if not self.setting_bind_mode:
            return
        try:
            descriptor = self._serialize_pynput_key(key)
            if not descriptor:
                gui_print("[ERROR] Не удалось определить нажатую клавишу")
                return

            self.current_bind_keycode = self._legacy_qt_key_from_pynput(key)
            key_name = self._pynput_key_name(key)
            update_settings(
                bind_keycode=self.current_bind_keycode,
                bind_key=descriptor,
            )
            self.bind_label.setText(f"Текущий бинд: {key_name}")
            gui_print(f"[SYSTEM] Бинд установлен: {key_name}")
        except Exception as e:
            gui_print(f"[ERROR] Ошибка сохранения бинда: {e}")
        finally:
            self.setting_bind_mode = False
            self.bind_btn.setText("Изменить бинд")
            self.bind_btn.setEnabled(True)
            self._hotkey_held = True
            self._hotkey_shot_armed = False

    def keyPressEvent(self, event):
        # Global pynput listener handles binding so keyboard layout does not
        # affect the result. Keep normal Qt handling for all other keys.
        super().keyPressEvent(event)

    def _load_bind(self):
        try:
            settings = load_settings()
            if settings.bind_key:
                self.current_bind_keycode = settings.bind_keycode
                name = self._descriptor_name(settings.bind_key)
                self.bind_label.setText(f"Текущий бинд: {name}")
                self._setup_global_shortcut()
                return

            # Backward compatibility with versions that stored only Qt keycode.
            saved_key = settings.bind_keycode
            if saved_key is None:
                self.bind_label.setText("Текущий бинд: Не задан")
                self._setup_global_shortcut()
                return

            self.current_bind_keycode = int(saved_key)
            pynput_key = self._qt_key_to_pynput(self.current_bind_keycode)
            if pynput_key is not None:
                descriptor = self._serialize_pynput_key(pynput_key)
                update_settings(bind_key=descriptor)
                name = self._pynput_key_name(pynput_key)
            else:
                name = self._get_key_name(self.current_bind_keycode)
            self.bind_label.setText(f"Текущий бинд: {name}")
            self._setup_global_shortcut()
        except Exception as e:
            self.bind_label.setText("Текущий бинд: Ошибка загрузки")
            gui_print(f"[ERROR] Ошибка загрузки бинда: {e}")

    def _ensure_keyboard_listener(self):
        """Start one global listener used for both binding and hotkey firing."""
        import pynput.keyboard as pynput_kb
        try:
            if self.keyboard_listener is not None:
                # Listener is already running in normal mode.
                return

            def on_press(key):
                try:
                    if self.setting_bind_mode:
                        self.bind_captured.emit(key)
                        return
                    if not self._key_matches_saved(key):
                        return
                    if self._hotkey_held or not self._hotkey_shot_armed:
                        return
                    self._hotkey_held = True
                    self._hotkey_shot_armed = False
                    QTimer.singleShot(0, self.take_screenshot)
                except Exception:
                    pass

            def on_release(key):
                try:
                    if self.setting_bind_mode:
                        return
                    if self._key_matches_saved(key):
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
            gui_print(f"[ERROR] Ошибка запуска клавиатурного слушателя: {e}")

    def _setup_global_shortcut(self):
        # Recreate the listener so a newly saved bind is picked up immediately.
        try:
            if self.keyboard_listener is not None:
                self.keyboard_listener.stop()
                self.keyboard_listener = None
        except Exception:
            self.keyboard_listener = None
        self._hotkey_held = False
        self._hotkey_shot_armed = True
        self._ensure_keyboard_listener()

    @staticmethod
    def _serialize_pynput_key(key):
        """Return a stable, layout-independent descriptor for a physical key."""
        try:
            vk = getattr(key, 'vk', None)
            if vk is not None:
                return f"vk:{int(vk)}"
        except Exception:
            pass
        try:
            name = getattr(key, 'name', None)
            if name:
                return f"name:{name}"
        except Exception:
            pass
        try:
            char = getattr(key, 'char', None)
            if char:
                return f"char:{ord(char)}"
        except Exception:
            pass
        return None

    @staticmethod
    def _descriptor_to_pynput(descriptor):
        import pynput.keyboard as pynput_kb
        from pynput.keyboard import Key
        if not descriptor:
            return None
        try:
            if descriptor.startswith('vk:'):
                return pynput_kb.KeyCode.from_vk(int(descriptor.split(':', 1)[1]))
            if descriptor.startswith('name:'):
                return getattr(Key, descriptor.split(':', 1)[1], None)
            if descriptor.startswith('char:'):
                return pynput_kb.KeyCode.from_char(chr(int(descriptor.split(':', 1)[1])))
        except Exception:
            return None
        return None

    def _key_matches_saved(self, key):
        descriptor = load_settings().bind_key
        if not descriptor:
            # Old installs may still have only a Qt keycode.
            target = self._qt_key_to_pynput(self.current_bind_keycode)
            return self._pynput_keys_equal(key, target)
        target = self._descriptor_to_pynput(descriptor)
        return self._pynput_keys_equal(key, target)

    @staticmethod
    def _pynput_keys_equal(a, b):
        if a is None or b is None:
            return False
        try:
            avk, bvk = getattr(a, 'vk', None), getattr(b, 'vk', None)
            if avk is not None and bvk is not None:
                return int(avk) == int(bvk)
        except Exception:
            pass
        try:
            return a == b
        except Exception:
            return False

    @staticmethod
    def _pynput_key_name(key):
        names = {
            'alt_l': 'Alt (левый)', 'alt_r': 'Alt (правый)',
            'ctrl_l': 'Ctrl (левый)', 'ctrl_r': 'Ctrl (правый)',
            'shift_l': 'Shift (левый)', 'shift_r': 'Shift (правый)',
            'cmd_l': 'Win (левый)', 'cmd_r': 'Win (правый)',
            'caps_lock': 'Caps Lock', 'num_lock': 'Num Lock',
            'scroll_lock': 'Scroll Lock', 'print_screen': 'Print Screen',
            'page_up': 'Page Up', 'page_down': 'Page Down',
            'backspace': 'Backspace', 'space': 'Space',
            'enter': 'Enter', 'tab': 'Tab', 'esc': 'Esc',
        }
        try:
            name = getattr(key, 'name', None)
            if name:
                return names.get(name, name.replace('_', ' ').title())
            char = getattr(key, 'char', None)
            if char:
                return char.upper()
            vk = getattr(key, 'vk', None)
            if vk is not None:
                return f"VK {vk}"
        except Exception:
            pass
        return str(key)

    def _descriptor_name(self, descriptor):
        key = self._descriptor_to_pynput(descriptor)
        if key is not None:
            return self._pynput_key_name(key)
        return descriptor

    @staticmethod
    def _legacy_qt_key_from_pynput(key):
        """Best-effort legacy integer for old configs/UI compatibility."""
        try:
            from pynput.keyboard import Key
            if isinstance(key, Key):
                reverse = {
                    Key.shift: Qt.Key_Shift, Key.ctrl: Qt.Key_Control,
                    Key.alt: Qt.Key_Alt, Key.cmd: Qt.Key_Meta,
                    Key.caps_lock: Qt.Key_CapsLock, Key.num_lock: Qt.Key_NumLock,
                    Key.scroll_lock: Qt.Key_ScrollLock, Key.space: Qt.Key_Space,
                    Key.enter: Qt.Key_Enter, Key.tab: Qt.Key_Tab,
                    Key.backspace: Qt.Key_Backspace, Key.esc: Qt.Key_Escape,
                }
                return reverse.get(key)
            char = getattr(key, 'char', None)
            if char and len(char) == 1 and char.isascii():
                return ord(char.upper()) if char.isalpha() else ord(char)
        except Exception:
            pass
        return None

    def _qt_key_to_pynput(self, qt_key_code):
        import pynput.keyboard as pynput_kb
        from pynput.keyboard import Key
        if qt_key_code is None:
            return None
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
            Qt.Key_ScrollLock: Key.scroll_lock,
        }
        return mapping.get(qt_key_code)

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
            Qt.Key_Insert: "Insert", Qt.Key_Delete: "Delete", Qt.Key_Home: "Home", Qt.Key_End: "End",
            Qt.Key_PageUp: "Page Up", Qt.Key_PageDown: "Page Down", Qt.Key_Print: "Print Screen",
            Qt.Key_Pause: "Pause", Qt.Key_Escape: "Esc", Qt.Key_Left: "←", Qt.Key_Right: "→",
            Qt.Key_Up: "↑", Qt.Key_Down: "↓", Qt.Key_Shift: "Shift", Qt.Key_Control: "Ctrl",
            Qt.Key_Alt: "Alt", Qt.Key_Space: "Space", Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter",
            Qt.Key_Tab: "Tab", Qt.Key_Backspace: "Backspace", Qt.Key_CapsLock: "Caps Lock",
        }
        return names.get(key_code, f"Key_{key_code}")

    def _play_sound(self):
        make_sound()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()

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