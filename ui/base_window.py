import sys
from PyQt5.QtWidgets import QWidget, QSizePolicy, QApplication
from PyQt5.QtCore import Qt, QPoint, QRect, QEvent
from PyQt5.QtGui import QMouseEvent, QCursor


HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

_HIT_MAP = {
    'left': HTLEFT,
    'right': HTRIGHT,
    'top': HTTOP,
    'bottom': HTBOTTOM,
    'left_top': HTTOPLEFT,
    'right_top': HTTOPRIGHT,
    'left_bottom': HTBOTTOMLEFT,
    'right_bottom': HTBOTTOMRIGHT,
}

_CURSOR_MAP = {
    'left_top': Qt.SizeFDiagCursor,
    'right_bottom': Qt.SizeFDiagCursor,
    'right_top': Qt.SizeBDiagCursor,
    'left_bottom': Qt.SizeBDiagCursor,
    'left': Qt.SizeHorCursor,
    'right': Qt.SizeHorCursor,
    'top': Qt.SizeVerCursor,
    'bottom': Qt.SizeVerCursor,
}


class BaseWindow(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(720, 560)

        self.dragging = False
        self.drag_position = QPoint()

        self.margin = 8
        self.resize_direction = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self._edge_override_active = False

        self.is_maximized = False

    def _can_resize(self):
        return not self.isMaximized() and not self.is_maximized and not self.isFullScreen()

    def _clear_edge_cursor(self):
        if self._edge_override_active:
            QApplication.restoreOverrideCursor()
            self._edge_override_active = False

    def _set_edge_cursor(self, direction):
        cursor = _CURSOR_MAP.get(direction)
        if cursor is None:
            self._clear_edge_cursor()
            return
        if self._edge_override_active:
            QApplication.changeOverrideCursor(QCursor(cursor))
        else:
            QApplication.setOverrideCursor(QCursor(cursor))
            self._edge_override_active = True

    def _update_hover_cursor(self, local_pos):
        if not self._can_resize() or self.resize_direction or self.dragging:
            return
        direction = self._get_resize_direction(local_pos)
        if direction:
            self._set_edge_cursor(direction)
        else:
            self._clear_edge_cursor()

    def event(self, event):
        if event.type() == QEvent.HoverMove and not self.resize_direction and not self.dragging:
            self._update_hover_cursor(event.pos())
        elif event.type() in (QEvent.HoverLeave, QEvent.Leave):
            if not self.resize_direction:
                self._clear_edge_cursor()
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        if self._can_resize():
            self.resize_direction = self._get_resize_direction(event.pos())
            if self.resize_direction:
                self.resize_start_pos = event.globalPos()
                self.resize_start_geometry = QRect(self.geometry())
                self._set_edge_cursor(self.resize_direction)
                self.grabMouse()
                event.accept()
                return

        if event.pos().y() <= 35 and self._get_resize_direction(event.pos()) is None:
            self._clear_edge_cursor()
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.resize_direction and self.resize_start_pos is not None:
            self._apply_resize(event.globalPos())
            event.accept()
            return

        if event.buttons() == Qt.LeftButton and self.dragging:
            if self.isMaximized() or self.is_maximized:
                event.accept()
                return
            self.move(event.globalPos() - self.drag_position)
            event.accept()
            return

        self._update_hover_cursor(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self.resize_direction:
                self.releaseMouse()
            self.dragging = False
            self.resize_direction = None
            self.resize_start_pos = None
            self.resize_start_geometry = None
            self._clear_edge_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.pos().y() <= 35:
            btn = getattr(self, 'maximize_btn', None)
            self.toggle_maximize(btn)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        if not self.resize_direction:
            self._clear_edge_cursor()
        super().leaveEvent(event)

    def _apply_resize(self, global_pos):
        if self.resize_start_geometry is None or self.resize_start_pos is None:
            return

        delta = global_pos - self.resize_start_pos
        geo = QRect(self.resize_start_geometry)
        min_w = max(self.minimumWidth(), 400)
        min_h = max(self.minimumHeight(), 300)

        if 'left' in self.resize_direction:
            new_left = geo.left() + delta.x()
            if geo.right() - new_left + 1 >= min_w:
                geo.setLeft(new_left)
        if 'right' in self.resize_direction:
            new_right = geo.right() + delta.x()
            if new_right - geo.left() + 1 >= min_w:
                geo.setRight(new_right)
        if 'top' in self.resize_direction:
            new_top = geo.top() + delta.y()
            if geo.bottom() - new_top + 1 >= min_h:
                geo.setTop(new_top)
        if 'bottom' in self.resize_direction:
            new_bottom = geo.bottom() + delta.y()
            if new_bottom - geo.top() + 1 >= min_h:
                geo.setBottom(new_bottom)

        self.setGeometry(geo)

    def _get_resize_direction(self, pos):
        if not self._can_resize():
            return None
        m = self.margin
        w, h = self.width(), self.height()
        if w <= m * 2 or h <= m * 2:
            return None

        x, y = pos.x(), pos.y()
        left = 0 <= x <= m
        right = (w - m) <= x < w
        top = 0 <= y <= m
        bottom = (h - m) <= y < h

        if left and top:
            return 'left_top'
        if left and bottom:
            return 'left_bottom'
        if right and top:
            return 'right_top'
        if right and bottom:
            return 'right_bottom'
        if left:
            return 'left'
        if right:
            return 'right'
        if top:
            return 'top'
        if bottom:
            return 'bottom'
        return None

    def nativeEvent(self, eventType, message):
        if sys.platform != 'win32' or not self._can_resize():
            return super().nativeEvent(eventType, message)

        et = bytes(eventType) if not isinstance(eventType, (bytes, bytearray)) else bytes(eventType)
        if et not in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            return super().nativeEvent(eventType, message)

        try:
            import ctypes
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return super().nativeEvent(eventType, message)

        if msg.message != 0x0084:  # WM_NCHITTEST
            return super().nativeEvent(eventType, message)

        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        local = self.mapFromGlobal(QPoint(x, y))
        direction = self._get_resize_direction(local)
        hit = _HIT_MAP.get(direction)
        if hit is not None:
            # Windows сам ставит курсор ресайза по HT*; setCursor на окне не трогаем.
            return True, hit
        return True, HTCLIENT

    def toggle_maximize(self, maximize_btn=None):
        self._clear_edge_cursor()
        if self.is_maximized or self.isMaximized():
            self.showNormal()
            self.is_maximized = False
            if maximize_btn:
                maximize_btn.setText("□")
        else:
            self.showMaximized()
            self.is_maximized = True
            if maximize_btn:
                maximize_btn.setText("❐")

    def closeEvent(self, event):
        self._clear_edge_cursor()
        super().closeEvent(event)
