from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from ui.theme_manager import close_button_style, title_label_style, window_button_style


class TitleBar(QWidget):
    """Shared frameless title bar: title, optional extras, min / max / close."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(35)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(5)

        self.title_label = QLabel(title)
        layout.addWidget(self.title_label)
        layout.addStretch()

        self._extras = QHBoxLayout()
        self._extras.setSpacing(5)
        layout.addLayout(self._extras)

        self.minimize_btn = self._window_button("_", "Свернуть")
        self.maximize_btn = self._window_button("□", "Развернуть")
        self.close_btn = self._window_button("×", "Закрыть")
        self.minimize_btn.clicked.connect(self._minimize)
        self.maximize_btn.clicked.connect(self._maximize)
        self.close_btn.clicked.connect(self._close)

        layout.addWidget(self.minimize_btn)
        layout.addWidget(self.maximize_btn)
        layout.addWidget(self.close_btn)

    def add_widget(self, widget):
        self._extras.addWidget(widget)

    def set_title(self, title: str):
        self.title_label.setText(title)

    def apply_theme(self, theme_name: str, title_size: int = 12):
        self.title_label.setStyleSheet(title_label_style(theme_name, title_size))
        chrome = window_button_style(theme_name)
        self.minimize_btn.setStyleSheet(chrome)
        self.maximize_btn.setStyleSheet(chrome)
        self.close_btn.setStyleSheet(close_button_style(theme_name))

    @staticmethod
    def _window_button(text: str, tip: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(30, 20)
        button.setToolTip(tip)
        return button

    def _minimize(self):
        window = self.window()
        if window is not None:
            window.showMinimized()

    def _maximize(self):
        window = self.window()
        if window is not None and hasattr(window, 'toggle_maximize'):
            window.toggle_maximize(self.maximize_btn)

    def _close(self):
        window = self.window()
        if window is not None:
            window.close()
