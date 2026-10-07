from core.settings import load_settings, update_settings

# ===== Темы =====

THEMES = {
    "Dark Orange": {
        "primary": "#FF7F50",
        "primary_hover": "#FF9D7A",
        "primary_pressed": "#E67A5D",
        "background": "#2B2C34",
        "secondary": "#45475A",
        "secondary_hover": "#585B70",
        "text": "#CDD6F4",
        "text_secondary": "#A6ADC8",
        "accent": "#94E2D5",
        "error": "#F38BA8",
        "warning": "#F9E2AF",
        "success": "#A6E3A1",
        "chat": "#CDD6F4",
        "chat_shadow": "0 0 2px rgba(255,255,255,0.3)",
    },
    "Dark Blue": {
        "primary": "#89B4FA",
        "primary_hover": "#A6C8FF",
        "primary_pressed": "#74A7F7",
        "background": "#1E1E2E",
        "secondary": "#313244",
        "secondary_hover": "#45475A",
        "text": "#CDD6F4",
        "text_secondary": "#A6ADC8",
        "accent": "#74C7EC",
        "error": "#F38BA8",
        "warning": "#F9E2AF",
        "success": "#A6E3A1",
        "chat": "#CDD6F4",
        "chat_shadow": "0 0 2px rgba(255,255,255,0.3)",
    },
    "Light White": {
        "primary": "#2563EB",
        "primary_hover": "#3B82F6",
        "primary_pressed": "#1D4ED8",
        "background": "#FFFFFF",
        "secondary": "#F8FAFC",
        "secondary_hover": "#F1F5F9",
        "text": "#1E293B",
        "text_secondary": "#475569",
        "accent": "#0369A1",
        "error": "#DC2626",
        "warning": "#EA580C",
        "success": "#16A34A",
        "chat": "#1E293B",
        "chat_shadow": "none",
    },
    "Purple": {
        "primary": "#CBA6F7",
        "primary_hover": "#D9BBF9",
        "primary_pressed": "#BB90F4",
        "background": "#1A1B26",
        "secondary": "#343B58",
        "secondary_hover": "#444B73",
        "text": "#C0CAF5",
        "text_secondary": "#A9B1D6",
        "accent": "#7AA2F7",
        "error": "#F7768E",
        "warning": "#E0AF68",
        "success": "#9ECE6A",
        "chat": "#C0CAF5",
        "chat_shadow": "0 0 2px rgba(255,255,255,0.3)",
    },
}

AVAILABLE_THEMES = list(THEMES.keys())
THEME_DISPLAY_NAMES = {name: name for name in THEMES.keys()}


def get_theme_stylesheet(theme_name: str) -> str:
    """
    Генерирует полный CSS-стиль для темы.
    Возвращает строку с CSS.
    """
    theme = THEMES.get(theme_name, THEMES["Dark Orange"])

    return f"""
    QWidget {{
        background-color: {theme['background']};
        color: {theme['text']};
        font-family: 'Segoe UI', Arial;
    }}
    QLineEdit, QComboBox {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        border: 1px solid {theme['secondary_hover']};
        border-radius: 5px;
        padding: 8px;
        font-size: 12px;
        min-width: 200px;
    }}
    QLineEdit:focus, QComboBox:focus {{
        border: 2px solid {theme['primary']};
    }}
    QComboBox::drop-down {{
        border: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        selection-background-color: {theme['primary']};
        border: 1px solid {theme['secondary_hover']};
    }}
    QLabel {{
        color: {theme['text']};
        padding: 5px;
        min-width: 100px;
        font-size: 14px;
        font-weight: bold;
        background: transparent;
    }}
    QPushButton {{
        background-color: {theme['primary']};
        color: white;
        border: none;
        border-radius: 5px;
        padding: 10px 20px;
        font-size: 14px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {theme['primary_hover']};
    }}
    QPushButton:pressed {{
        background-color: {theme['primary_pressed']};
    }}
    QPushButton:disabled {{
        background-color: {theme['secondary']};
        color: {theme['text_secondary']};
    }}
    QCheckBox {{
        color: {theme['text']};
        spacing: 8px;
        font-size: 14px;
        font-weight: normal;
        background: transparent;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {theme['secondary_hover']};
        border-radius: 3px;
        background: {theme['secondary']};
    }}
    QCheckBox::indicator:checked {{
        background: {theme['primary']};
        border-color: {theme['primary']};
    }}
    QCheckBox::indicator:hover {{
        border: 2px solid {theme['primary_hover']};
    }}
    QProgressBar {{
        border: 1px solid {theme['secondary_hover']};
        border-radius: 5px;
        background: {theme['secondary']};
        text-align: center;
        height: 15px;
    }}
    QProgressBar::chunk {{
        background: {theme['primary']};
        border-radius: 3px;
    }}
    QSlider::groove:horizontal {{
        border: none;
        height: 6px;
        background: {theme['secondary']};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {theme['primary']};
        border: none;
        width: 18px;
        height: 18px;
        margin: -6px 0;
        border-radius: 9px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {theme['primary_hover']};
    }}
    QSlider::handle:horizontal:pressed {{
        background: {theme['primary_pressed']};
    }}
    QSlider::sub-page:horizontal {{
        background: {theme['primary']};
        border-radius: 3px;
    }}
    QTextEdit {{
        background-color: {theme['secondary']};
        color: {theme['text']};
        border: 1px solid {theme['secondary_hover']};
        border-radius: 5px;
        padding: 10px;
        font-family: 'Cascadia Code', 'Courier New', monospace;
        font-size: 12px;
        selection-background-color: {theme['primary']};
    }}
    QScrollBar:vertical {{
        border: none;
        background: {theme['secondary']};
        width: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {theme['secondary_hover']};
        border-radius: 6px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {theme['primary']};
    }}
    QScrollBar::handle:vertical:pressed {{
        background: {theme['primary_pressed']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        border: none;
        background: {theme['secondary']};
        height: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {theme['secondary_hover']};
        border-radius: 6px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {theme['primary']};
    }}
    QScrollBar::handle:horizontal:pressed {{
        background: {theme['primary_pressed']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QMenu {{
        background-color: {theme['background']};
        color: {theme['text']};
        border: 1px solid {theme['secondary_hover']};
    }}
    QMenu::item:selected {{
        background-color: {theme['primary']};
    }}
    """


def load_saved_theme() -> str:
    saved = load_settings().theme
    if saved in THEMES:
        return saved
    return "Dark Orange"


def save_theme(theme_name: str):
    update_settings(theme=theme_name)


def theme(theme_name: str) -> dict:
    return THEMES.get(theme_name, THEMES["Dark Orange"])


def window_button_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"QPushButton {{ background-color: transparent; color: {t['text']}; border: none; "
        f"font-size: 16px; font-weight: normal; padding: 0px; margin: 0px; }} "
        f"QPushButton:hover {{ background-color: {t['secondary_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {t['secondary']}; }}"
    )


def close_button_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"QPushButton {{ background-color: transparent; color: {t['text']}; border: none; "
        f"font-size: 16px; font-weight: normal; padding: 0px; margin: 0px; }} "
        f"QPushButton:hover {{ background-color: #FF4757; color: white; }} "
        f"QPushButton:pressed {{ background-color: #FF3742; }}"
    )


def title_label_style(theme_name: str, size: int = 12) -> str:
    t = theme(theme_name)
    return (
        f"font-size: {size}px; font-weight: bold; color: {t['text']}; "
        f"background: transparent; padding: 0px; margin: 0px;"
    )


def toolbar_button_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"QPushButton {{ background-color: {t['background']}; color: {t['text']}; "
        f"border: 1px solid {t['secondary_hover']}; "
        f"border-radius: 4px; padding: 4px 8px; font-size: 11px; margin: 0px; }} "
        f"QPushButton:hover {{ background-color: {t['secondary']}; border-color: {t['primary']}; }} "
        f"QPushButton:pressed {{ background-color: {t['secondary_hover']}; }}"
    )


def accent_button_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"QPushButton {{ background-color: {t['primary']}; color: white; border: none; "
        f"border-radius: 2px; padding: 4px 8px; font-size: 11px; margin: 0px; }} "
        f"QPushButton:hover {{ background-color: {t['primary_hover']}; }} "
        f"QPushButton:pressed {{ background-color: {t['primary_pressed']}; }}"
    )


def checkbox_style(theme_name: str) -> str:
    t = theme(theme_name)
    return f"""
    QCheckBox {{
        color: {t['text']};
        font-size: 14px;
        font-weight: normal;
        background: transparent;
        spacing: 8px;
        border: none;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {t['secondary_hover']};
        border-radius: 4px;
        background: {t['secondary']};
    }}
    QCheckBox::indicator:checked {{
        background: {t['primary']};
        border-color: {t['primary']};
    }}
    QCheckBox::indicator:hover {{
        border: 2px solid {t['primary_hover']};
    }}
    """


def slider_style(theme_name: str) -> str:
    t = theme(theme_name)
    return f"""
    QSlider {{ background: transparent; border: none; min-height: 22px; }}
    QSlider::groove:horizontal {{
        border: none;
        height: 4px;
        background: {t['secondary_hover']};
        border-radius: 2px;
        margin: 0 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {t['primary']};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {t['primary']};
        border: none;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{ background: {t['primary_hover']}; }}
    """


def field_label_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"color: {t['text']}; background: transparent; "
        f"border: 1px solid {t['secondary_hover']}; border-radius: 8px; "
        f"font-size: 14px; font-weight: bold; padding: 0px 10px; margin: 0px;"
    )


def stat_label_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"font-size: 14px; background-color: {t['secondary']}; padding: 10px; "
        f"border-radius: 5px; border: 1px solid {t['secondary_hover']}; color: {t['text']};"
    )


def session_label_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"font-size: 14px; font-weight: bold; color: {t['accent']}; "
        f"background-color: {t['secondary']}; padding: 8px 12px; border-radius: 8px; "
        f"border: 1px solid {t['secondary_hover']}; min-width: 120px;"
    )


def bind_label_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"font-size: 14px; color: {t['primary']}; padding: 8px; "
        f"background-color: {t['secondary']}; border-radius: 5px; "
        f"border: 1px solid {t['secondary_hover']};"
    )


def log_output_style(theme_name: str) -> str:
    t = theme(theme_name)
    return (
        f"QTextEdit {{ background-color: {t['secondary']}; color: {t['text']}; "
        f"border: 1px solid {t['secondary_hover']}; border-radius: 5px; padding: 10px; "
        f"font-family: 'Cascadia Code', 'Courier New', monospace; font-size: 12px; "
        f"selection-background-color: {t['primary']}; }} "
        f"QScrollBar:vertical {{ border: none; background: {t['secondary']}; width: 12px; margin: 0px; }} "
        f"QScrollBar::handle:vertical {{ background: {t['secondary_hover']}; border-radius: 6px; min-height: 30px; }} "
        f"QScrollBar::handle:vertical:hover {{ background: {t['primary']}; }} "
        f"QScrollBar::handle:vertical:pressed {{ background: {t['primary_pressed']}; }}"
    )


def main_window_stylesheet(theme_name: str) -> str:
    t = theme(theme_name)
    return f"""
    QWidget {{ background: transparent; color: {t['text']}; font-family: 'Segoe UI', Arial; }}
    QTextEdit {{ background-color: {t['secondary']}; color: {t['text']}; border: 1px solid {t['secondary_hover']}; border-radius: 5px; padding: 10px; font-family: 'Cascadia Code', 'Courier New', monospace; font-size: 12px; selection-background-color: {t['primary']}; }}
    QLabel {{ color: {t['text']}; padding: 5px; }}
    QPushButton {{ background-color: {t['primary']}; color: white; border: none; border-radius: 5px; padding: 10px 20px; font-size: 14px; font-weight: bold; }}
    QPushButton:hover {{ background-color: {t['primary_hover']}; }}
    QPushButton:pressed {{ background-color: {t['primary_pressed']}; }}
    QPushButton:disabled {{ background-color: {t['secondary']}; color: {t['text_secondary']}; }}
    QMenu {{ background-color: {t['background']}; color: {t['text']}; border: 1px solid {t['secondary_hover']}; }}
    QMenu::item:selected {{ background-color: {t['primary']}; }}
    """


def get_log_colors(theme_name: str = None) -> dict:
    """
    Возвращает словарь цветов для подсветки логов.
    Если тема не указана, загружает сохранённую.
    """
    if theme_name is None:
        theme_name = load_saved_theme()
    theme = THEMES.get(theme_name, THEMES["Dark Orange"])
    return {
        'error': theme['error'],
        'warning': theme['warning'],
        'system': theme['accent'],
        'chat': theme['chat'],
        'text': theme['text'],
        'chat_shadow': theme['chat_shadow'],
    }