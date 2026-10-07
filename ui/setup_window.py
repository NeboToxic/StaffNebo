import os
import sys
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QStackedWidget,
    QProgressBar, QSlider, QFileDialog, QSizePolicy
)
from PyQt5.QtCore import Qt, QRectF, QTimer, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon, QImage, QPainterPath

from ui.base_window import BaseWindow
from ui.title_bar import TitleBar
from ui.theme_manager import THEMES, checkbox_style, field_label_style, slider_style
from core.settings import load_settings, save_settings, update_settings
from core.helpers import gui_print
from threads.validation import ValidationThread
from core.paths import resource_path, data_path


class SetupWindow(BaseWindow):

    def __init__(self):
        super().__init__()

        try:
            icon_path = resource_path(os.path.join('path', 'icon.ico'))
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"Не удалось установить иконку для SetupWindow: {e}")

        self.themes = THEMES

        self.setMinimumSize(780, 680)
        self.resize(900, 840)
        self.current_theme = self._load_theme()
        self.setStyleSheet(self._get_theme_stylesheet())

        self.verified_bot_id = None
        self.verified_chat_id = None
        self.validation_data = {}
        self.old_bot_id = ''
        self.old_chat_id = ''

        self.stacked_widget = QStackedWidget()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.stacked_widget)

        self.setup_screen = self._create_setup_screen()
        self.loading_screen = self._create_loading_screen()

        self.stacked_widget.addWidget(self.setup_screen)
        self.stacked_widget.addWidget(self.loading_screen)

        self._load_existing_config()
        self._update_theme_specific_styles()
        self._load_verification_info()

        QTimer.singleShot(100, lambda: self._on_platform_changed(self.platform_combo.currentText()))

    def _load_theme(self):
        theme = load_settings().theme
        if theme in self.themes:
            return theme
        return "Небо"

    def _get_theme_stylesheet(self):
        theme = self.themes.get(self.current_theme, self.themes["Небо"])
        return f"""
        QWidget {{ background: transparent; color: {theme['text']}; font-family: 'Segoe UI', Arial; }}
        QLineEdit, QComboBox {{ background-color: {theme['secondary']}; color: {theme['text']}; border: 1px solid {theme['secondary_hover']}; border-radius: 5px; padding: 8px; font-size: 12px; min-width: 200px; }}
        QLineEdit:focus, QComboBox:focus {{ border: 2px solid {theme['primary']}; }}
        QLabel {{ color: {theme['text']}; padding: 5px; min-width: 100px; font-size: 14px; font-weight: bold; background: transparent; }}
        QPushButton {{ background-color: {theme['primary']}; color: white; border: none; border-radius: 5px; padding: 10px 20px; font-size: 14px; font-weight: bold; }}
        QPushButton:hover {{ background-color: {theme['primary_hover']}; }}
        QPushButton:pressed {{ background-color: {theme['primary_pressed']}; }}
        QCheckBox {{ color: {theme['text']}; spacing: 8px; font-size: 14px; font-weight: normal; background: transparent; }}
        QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid {theme['secondary_hover']}; border-radius: 3px; background: {theme['secondary']}; }}
        QCheckBox::indicator:checked {{ background: {theme['primary']}; border-color: {theme['primary']}; }}
        QProgressBar {{ border: 1px solid {theme['secondary_hover']}; border-radius: 5px; background: {theme['secondary']}; text-align: center; height: 15px; }}
        QProgressBar::chunk {{ background: {theme['primary']}; border-radius: 3px; }}
        QSlider::groove:horizontal {{ border: 1px solid {theme['secondary_hover']}; height: 8px; background: {theme['secondary']}; border-radius: 4px; }}
        QSlider::handle:horizontal {{ background: {theme['primary']}; border: 1px solid {theme['primary_hover']}; width: 18px; margin: -4px 0; border-radius: 9px; }}
        QSlider::handle:horizontal:hover {{ background: {theme['primary_hover']}; }}
        """

    def _update_theme_specific_styles(self):
        if hasattr(self, 'title_bar'):
            self.title_bar.apply_theme(self.current_theme)
        if hasattr(self, 'loading_title'):
            self.loading_title.apply_theme(self.current_theme)
        self._update_delay_slider_style()
        self.update()

    def _slider_stylesheet(self) -> str:
        return slider_style(self.current_theme)

    def _combo_arrow_url(self) -> str:
        theme = self.themes[self.current_theme]
        path = data_path('combo_arrow.png')
        image = QImage(16, 16, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(theme['text']))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(QPointF(3, 5), QPointF(8, 10))
        painter.drawLine(QPointF(8, 10), QPointF(13, 5))
        painter.end()
        image.save(path)
        return path.replace('\\', '/')

    def _update_delay_slider_style(self):
        if hasattr(self, 'delay_slider') and self.delay_slider is not None:
            self.delay_slider.setStyleSheet(self._slider_stylesheet())
        if hasattr(self, 'delay_value_label') and self.delay_value_label is not None:
            self.delay_value_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.themes[self.current_theme]['primary']}; background: transparent;")
        if hasattr(self, 'sound_checkbox') and self.sound_checkbox is not None:
            self.sound_checkbox.setStyleSheet(checkbox_style(self.current_theme))

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFixedSize(132, 32)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        label.setStyleSheet(field_label_style(self.current_theme))
        return label

    def _field_row(self, label_text: str, field) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(self._field_label(label_text))
        field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        field.setFixedHeight(32)
        row.addWidget(field, 1)
        return row

    def _get_content_frame_stylesheet(self):
        theme = self.themes.get(self.current_theme, self.themes["Небо"])
        return f"""
        QWidget#configCard {{
            background-color: {theme['secondary']};
            border: 2px solid {theme['secondary_hover']};
            border-radius: 15px;
        }}
        QWidget#fieldHost {{
            background: transparent;
            border: none;
        }}
        QLabel#configHeader {{
            color: {theme['text']};
            background: transparent;
            border: 2px solid {theme['secondary_hover']};
            border-radius: 12px;
            font-size: 18px;
            font-weight: bold;
            padding: 14px 20px;
        }}
        QLabel {{
            color: {theme['text']};
            background: transparent;
            border: none;
            font-size: 14px;
            font-weight: bold;
            padding: 0px;
            margin: 0px;
        }}
        QLineEdit {{
            background-color: {theme['background']};
            color: {theme['text']};
            border: 1px solid {theme['secondary_hover']};
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 13px;
            min-height: 32px;
            max-height: 32px;
        }}
        QLineEdit:focus {{
            border: 2px solid {theme['primary']};
        }}
        QComboBox {{
            background-color: {theme['background']};
            color: {theme['text']};
            border: 1px solid {theme['secondary_hover']};
            border-radius: 6px;
            padding: 4px 8px 4px 10px;
            font-size: 13px;
            min-height: 32px;
            max-height: 32px;
        }}
        QComboBox:focus, QComboBox:on {{
            border: 2px solid {theme['primary']};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 22px;
            border: none;
            background: transparent;
        }}
        QComboBox::down-arrow {{
            image: url({self._combo_arrow_url()});
            width: 12px;
            height: 12px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {theme['background']};
            color: {theme['text']};
            border: 1px solid {theme['primary']};
            selection-background-color: {theme['primary']};
            outline: none;
        }}
        QPushButton {{
            background-color: {theme['primary']};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 10px;
            font-size: 14px;
            font-weight: bold;
            min-height: 25px;
        }}
        QPushButton:hover {{ background-color: {theme['primary_hover']}; }}
        QPushButton:pressed {{ background-color: {theme['primary_pressed']}; }}
        QCheckBox {{
            color: {theme['text']};
            spacing: 8px;
            background: transparent;
            border: none;
            font-size: 14px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {theme['secondary_hover']};
            border-radius: 4px;
            background: {theme['background']};
        }}
        QCheckBox::indicator:checked {{
            background: {theme['primary']};
            border-color: {theme['primary']};
        }}
        """

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        theme = self.themes[self.current_theme]
        frame = QRectF(self.rect().adjusted(1, 1, -1, -1))
        clip = QPainterPath()
        clip.addRoundedRect(frame, 8, 8)
        painter.setClipPath(clip)
        painter.fillRect(frame, QColor(theme['background']))
        painter.fillRect(QRectF(frame.x(), frame.y(), frame.width(), 35), QColor(theme['secondary']))
        painter.setClipping(False)
        painter.setPen(QPen(QColor(theme['secondary_hover']), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame, 8, 8)

    def _load_verification_info(self):
        try:
            settings = load_settings()
            self.verified_bot_id = settings.verified_bot_id or None
            self.verified_chat_id = settings.verified_chat_id or None
        except Exception as e:
            print(f"Ошибка загрузки verified_settings: {e}")

    def save_verification_info(self, bot_id_val, chat_id_val):
        try:
            update_settings(verified_bot_id=bot_id_val, verified_chat_id=chat_id_val)
            self.verified_bot_id = bot_id_val
            self.verified_chat_id = chat_id_val
        except Exception as e:
            print(f"Ошибка сохранения verified_settings: {e}")

    def _load_existing_config(self):
        try:
            settings = load_settings()
            if settings.nick:
                self.nick_input.setText(settings.nick)
            if settings.logs:
                logs_path = settings.logs
                username = os.getlogin()
                minigames_path = f"C:\\Users\\{username}\\.cristalix\\updates\\Minigames\\logs\\latest.log"
                staff_path = f"C:\\Users\\{username}\\.cristalix\\updates\\Minigames-staging-java21\\logs\\latest.log"
                if logs_path == minigames_path:
                    self.logs_combo.setCurrentText("Minigames")
                elif logs_path == staff_path:
                    self.logs_combo.setCurrentText("Staff Minigames")
                else:
                    self.logs_combo.setCurrentText("Свой путь")
                    self.custom_logs_input.setText(logs_path)
            self.sound_checkbox.setChecked(bool(settings.use_sound))
            try:
                self.delay_slider.setValue(int(float(settings.screenshot_delay) * 10))
            except (ValueError, TypeError):
                self.delay_slider.setValue(7)
            if settings.bot_id:
                self.bot_id_input.setText(settings.bot_id)
            if settings.chat_id:
                self.tg_id_input.setText(settings.chat_id)
            if settings.vk_user_id:
                self.vk_id_input.setText(settings.vk_user_id)
            if settings.vk_token:
                self.vk_token_input.setText(settings.vk_token)
            if settings.platform == 'vk':
                self.platform_combo.setCurrentText("ВКонтакте")
            else:
                self.platform_combo.setCurrentText("Telegram")
        except Exception as e:
            print(f"Ошибка загрузки конфига: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        if self.platform_combo.currentText() == "Telegram":
            self.telegram_widget.setVisible(True)
            self.vk_widget.setVisible(False)
            self._load_telegram_settings()
        else:
            self.telegram_widget.setVisible(False)
            self.vk_widget.setVisible(True)
            self._load_vk_id()
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

    def _create_setup_screen(self):
        screen = QWidget()
        main_layout = QVBoxLayout(screen)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.title_bar = TitleBar("NeboProject - Настройка программы", self)
        self.title_bar.apply_theme(self.current_theme)
        self.minimize_btn = self.title_bar.minimize_btn
        self.maximize_btn = self.title_bar.maximize_btn
        self.close_btn = self.title_bar.close_btn
        main_layout.addWidget(self.title_bar)
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(20, 20, 20, 20)
        center_layout.addStretch()
        content_frame = QWidget()
        content_frame.setObjectName("configCard")
        content_frame.setMinimumWidth(520)
        content_frame.setMaximumWidth(680)
        content_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        content_frame.setStyleSheet(self._get_content_frame_stylesheet())
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(14)

        header_label = QLabel("Настройка конфигурации")
        header_label.setObjectName("configHeader")
        header_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(header_label)

        self.nick_input = QLineEdit()
        self.nick_input.setPlaceholderText("Ваш никнейм в игре")
        content_layout.addLayout(self._field_row("Никнейм:", self.nick_input))

        self.logs_combo = QComboBox()
        self.logs_combo.addItems(["Minigames", "Staff Minigames", "Свой путь"])
        self.logs_combo.currentTextChanged.connect(self._on_logs_type_changed)
        content_layout.addLayout(self._field_row("Клиент:", self.logs_combo))

        self.custom_logs_widget = QWidget()
        self.custom_logs_widget.setObjectName("fieldHost")
        self.custom_logs_widget.setVisible(False)
        custom_logs_layout = QHBoxLayout(self.custom_logs_widget)
        custom_logs_layout.setContentsMargins(0, 0, 0, 0)
        custom_logs_layout.setSpacing(12)
        custom_logs_layout.addWidget(self._field_label("Путь:"))
        self.custom_logs_input = QLineEdit()
        self.custom_logs_input.setPlaceholderText("Полный путь до файла latest.log")
        self.custom_logs_input.setFixedHeight(32)
        self.custom_logs_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        custom_logs_layout.addWidget(self.custom_logs_input, 1)
        self.browse_logs_btn = QPushButton("...")
        self.browse_logs_btn.setFixedSize(32, 32)
        self.browse_logs_btn.setToolTip("Выбрать файл")
        self.browse_logs_btn.clicked.connect(self._browse_logs)
        custom_logs_layout.addWidget(self.browse_logs_btn)
        content_layout.addWidget(self.custom_logs_widget)

        self.platform_combo = QComboBox()
        self.platform_combo.addItems(["Telegram", "ВКонтакте"])
        self.platform_combo.currentTextChanged.connect(self._on_platform_changed)
        content_layout.addLayout(self._field_row("Платформа:", self.platform_combo))

        self.telegram_widget = QWidget()
        self.telegram_widget.setObjectName("fieldHost")
        telegram_layout = QVBoxLayout(self.telegram_widget)
        telegram_layout.setContentsMargins(0, 0, 0, 0)
        telegram_layout.setSpacing(14)
        self.bot_id_input = QLineEdit()
        self.bot_id_input.setPlaceholderText("ID бота в формате число:строка")
        telegram_layout.addLayout(self._field_row("Token Bot:", self.bot_id_input))
        self.tg_id_input = QLineEdit()
        self.tg_id_input.setPlaceholderText("ID чата Telegram (число)")
        telegram_layout.addLayout(self._field_row("TG ID:", self.tg_id_input))
        content_layout.addWidget(self.telegram_widget)

        self.vk_widget = QWidget()
        self.vk_widget.setObjectName("fieldHost")
        vk_layout = QVBoxLayout(self.vk_widget)
        vk_layout.setContentsMargins(0, 0, 0, 0)
        vk_layout.setSpacing(14)
        self.vk_id_input = QLineEdit()
        self.vk_id_input.setPlaceholderText("ID пользователя / беседы")
        vk_layout.addLayout(self._field_row("VK ID:", self.vk_id_input))
        self.vk_token_input = QLineEdit()
        self.vk_token_input.setPlaceholderText("Токен VK API")
        self.vk_token_input.setEchoMode(QLineEdit.Password)
        vk_layout.addLayout(self._field_row("VK Token:", self.vk_token_input))
        self.vk_widget.setVisible(False)
        content_layout.addWidget(self.vk_widget)

        content_layout.addStretch()
        delay_layout = QHBoxLayout()
        delay_layout.setContentsMargins(0, 0, 0, 0)
        delay_layout.setSpacing(10)
        delay_layout.addWidget(self._field_label("Kd скрина:"))
        self.delay_slider = QSlider(Qt.Horizontal)
        self.delay_slider.setMinimum(1)
        self.delay_slider.setMaximum(10)
        self.delay_slider.setTickInterval(1)
        self.delay_slider.setTickPosition(QSlider.TicksBelow)
        self.delay_slider.setValue(7)
        self.delay_slider.setFixedHeight(24)
        self.delay_slider.setStyleSheet(self._slider_stylesheet())
        self.delay_value_label = QLabel("0.7 сек")
        self.delay_value_label.setMinimumWidth(60)
        self.delay_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.delay_value_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.themes[self.current_theme]['primary']}; background: transparent;")
        self.delay_slider.valueChanged.connect(self._on_delay_changed)
        delay_layout.addWidget(self.delay_slider)
        delay_layout.addWidget(self.delay_value_label)
        content_layout.addLayout(delay_layout)
        sound_layout = QHBoxLayout()
        sound_layout.addStretch()
        self.sound_checkbox = QCheckBox("Использовать звуковые уведомления")
        self.sound_checkbox.setChecked(True)
        self.sound_checkbox.setStyleSheet(checkbox_style(self.current_theme))
        sound_layout.addWidget(self.sound_checkbox)
        sound_layout.addStretch()
        content_layout.addLayout(sound_layout)

        self.confirm_btn = QPushButton("Подтвердить")
        self.confirm_btn.setFixedHeight(40)
        self.confirm_btn.setMinimumWidth(200)
        self.confirm_btn.clicked.connect(self.validate_and_save)
        content_layout.addWidget(self.confirm_btn, alignment=Qt.AlignCenter)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #F38BA8; font-weight: bold; padding: 10px; background: transparent;")
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.error_label)

        center_layout.addWidget(content_frame)
        center_layout.addStretch()
        main_layout.addWidget(center_widget)
        return screen

    def _create_loading_screen(self):
        screen = QWidget()
        layout = QVBoxLayout(screen)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.loading_title = TitleBar("NeboProject - Загрузка", self)
        self.loading_title.apply_theme(self.current_theme)
        layout.addWidget(self.loading_title)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        loading_label = QLabel("Загрузка...")
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setStyleSheet("font-size: 16px; color: #CDD6F4; background: transparent;")
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 0)
        content_layout.addWidget(loading_label)
        content_layout.addWidget(self.loading_progress)
        content_layout.addStretch()
        layout.addWidget(content)
        return screen

    def _on_logs_type_changed(self, logs_type):
        if logs_type == "Свой путь":
            self.custom_logs_widget.setVisible(True)
        else:
            self.custom_logs_widget.setVisible(False)

    def _browse_logs(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите файл latest.log", "", "Log files (*.log);;All files (*.*)")
        if file_path:
            self.custom_logs_input.setText(file_path)

    def _on_platform_changed(self, platform_name):
        if platform_name == "Telegram":
            self.telegram_widget.setVisible(True)
            self.vk_widget.setVisible(False)
            self._load_telegram_settings()
        else:
            self.telegram_widget.setVisible(False)
            self.vk_widget.setVisible(True)
            self._load_vk_id()
        self.telegram_widget.updateGeometry()
        self.vk_widget.updateGeometry()
        self.vk_id_input.updateGeometry()
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

    def _load_telegram_settings(self):
        try:
            settings = load_settings()
            if settings.bot_id and settings.bot_id not in ['', 'None']:
                self.bot_id_input.setText(settings.bot_id)
            if settings.chat_id and settings.chat_id not in ['', 'None']:
                self.tg_id_input.setText(settings.chat_id)
        except Exception as e:
            print(f"Ошибка загрузки настроек Telegram: {e}")

    def _load_vk_id(self):
        try:
            settings = load_settings()
            vk_id = settings.vk_user_id
            if vk_id and vk_id not in ['', 'None']:
                self.vk_id_input.setText(vk_id)
            if settings.vk_token and settings.vk_token not in ['', 'None']:
                self.vk_token_input.setText(settings.vk_token)
        except Exception as e:
            print(f"Ошибка загрузки VK ID: {e}")

    def _on_delay_changed(self, value):
        try:
            if hasattr(self, 'delay_value_label') and self.delay_value_label is not None:
                delay = value / 10.0
                self.delay_value_label.setText(f"{delay:.1f} сек")
        except Exception as e:
            print(f"Ошибка в on_delay_changed: {e}")

    def show_error(self, message):
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def validate_and_save(self):
        self.error_label.setVisible(False)
        nick = self.nick_input.text().strip()
        logs_type = self.logs_combo.currentText()
        platform_choice = self.platform_combo.currentText()
        use_sound = self.sound_checkbox.isChecked()
        screenshot_delay_val = self.delay_slider.value() / 10.0
        errors = []
        if not nick:
            errors.append("Никнейм не может быть пустым")
        if logs_type == "Свой путь":
            logs_path = self.custom_logs_input.text().strip()
            if not logs_path:
                errors.append("Не указан путь к файлу логов")
            elif not os.path.exists(logs_path):
                errors.append(f"Указанный путь не существует:\n{logs_path}")
        else:
            username = os.getlogin()
            if logs_type == "Minigames":
                logs_path = f"C:\\Users\\{username}\\.cristalix\\updates\\Minigames\\logs\\latest.log"
            else:
                logs_path = f"C:\\Users\\{username}\\.cristalix\\updates\\Minigames-staging-java21\\logs\\latest.log"
            if not os.path.exists(logs_path):
                errors.append(f"Путь к логам не существует:\n{logs_path}")
        if platform_choice == "Telegram":
            bot_id_val = self.bot_id_input.text().strip()
            tg_id_val = self.tg_id_input.text().strip()
            if not bot_id_val or ':' not in bot_id_val:
                errors.append("Token Bot должен быть в формате 'число:строка'")
            if not tg_id_val or not tg_id_val.isdigit():
                errors.append("TG ID должен быть числом")
        else:
            vk_id_val = self.vk_id_input.text().strip()
            vk_token_val = self.vk_token_input.text().strip()
            if not vk_id_val:
                errors.append("Для ВКонтакте необходимо указать ID получателя")
            if not vk_token_val:
                errors.append("Для ВКонтакте необходимо указать VK Token")
            elif not vk_id_val.isdigit():
                errors.append("VK ID должен быть числом")
        if errors:
            self.show_error("\n".join(errors))
            return

        existing = load_settings()
        self.old_bot_id = existing.bot_id or ''
        self.old_chat_id = existing.chat_id or ''

        try:
            if platform_choice == "Telegram":
                bot_saved = bot_id_val
                chat_saved = tg_id_val
                vk_saved = existing.vk_user_id
                vk_token_saved = existing.vk_token
            else:
                bot_saved = existing.bot_id
                chat_saved = existing.chat_id
                vk_saved = vk_id_val
                vk_token_saved = vk_token_val

            existing.nick = nick
            existing.logs = logs_path
            existing.platform = 'vk' if platform_choice == 'ВКонтакте' else 'telegram'
            existing.use_sound = use_sound
            existing.screenshot_delay = screenshot_delay_val
            existing.bot_id = bot_saved
            existing.chat_id = chat_saved
            existing.vk_user_id = vk_saved
            existing.vk_token = vk_token_saved
            save_settings(existing)

            self.validation_data = {
                'nick': nick,
                'platform': platform_choice,
                'bot_id': bot_saved,
                'chat_id': chat_saved,
                'vk_user_id': vk_saved,
                'vk_token': vk_token_saved,
            }
            self.stacked_widget.setCurrentWidget(self.loading_screen)
            self._start_validation()
        except Exception as e:
            self.show_error(f"Ошибка сохранения: {str(e)}")

    def _start_validation(self):
        self.validation_thread = ValidationThread(
            self.validation_data, self.old_bot_id, self.old_chat_id,
            self.verified_bot_id, self.verified_chat_id, self
        )
        self.validation_thread.finished.connect(self._on_validation_finished)
        self.validation_thread.start()

    def _on_validation_finished(self, success, message):
        if success:
            QTimer.singleShot(1000, self._open_main_window)
        else:
            self.stacked_widget.setCurrentWidget(self.setup_screen)
            self.show_error(message)

    def check_bot_and_chat(self, bot_id_val, chat_id_val, need_verification_message=True):
        try:
            if not bot_id_val or bot_id_val == "0:default" or ':' not in bot_id_val:
                return {"success": True, "message": "Проверка не требуется (VK режим)"}
            if not chat_id_val or not chat_id_val.isdigit():
                return {"success": False, "message": "TG ID должен содержать только цифры"}
            import telebot
            test_bot = telebot.TeleBot(bot_id_val)
            test_chat_id = int(chat_id_val)
            if need_verification_message:
                test_bot.send_message(test_chat_id, "✅ NeboProject успешно подключен! Настройки корректны.", parse_mode='html')
            return {"success": True, "message": "Проверка пройдена успешно"}
        except Exception as e:
            error_msg = str(e).lower()
            if "chat not found" in error_msg or "invalid chat id" in error_msg:
                return {"success": False, "message": "Ошибка: TG ID не найден или неверный"}
            elif "bot token" in error_msg or "invalid token" in error_msg:
                return {"success": False, "message": "Ошибка: Неверный Token Bot"}
            return {"success": False, "message": f"Ошибка Telegram API: {e}"}

    def save_bot_verification(self, bot_id_val, chat_id_val):
        self.save_verification_info(bot_id_val, chat_id_val)

    def _open_main_window(self):
        from ui.main_window import MainWindow
        from core.globals import reload_globals_from_config
        import core.globals as g

        reload_globals_from_config()

        if getattr(self, '_main_screen', None) is None:
            self._main_screen = MainWindow(parent=self)
            self.stacked_widget.addWidget(self._main_screen)

        g.main_window = self._main_screen
        self.setMinimumSize(800, 560)
        self.stacked_widget.setCurrentWidget(self._main_screen)

        self._main_screen.setup_initial_display()
        if not self._main_screen.log_monitor.isRunning():
            self._main_screen.log_monitor.start()
        self._main_screen.update_stats()

    def closeEvent(self, event):
        if getattr(self, '_main_screen', None) is not None:
            self._main_screen.shutdown()
        if hasattr(self, 'validation_thread') and self.validation_thread is not None:
            try:
                self.validation_thread.stop()
            except Exception:
                pass
        super().closeEvent(event)