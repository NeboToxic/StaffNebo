import threading
from PyQt5.QtCore import QThread


class StoppableThread(QThread):
    """Cooperative cancellation, including interruptible retry delays."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()

    @property
    def should_stop(self):
        return self._stop_event.is_set()

    def stop(self):
        self._stop_event.set()

    def pause(self, seconds):
        return self._stop_event.wait(max(0.0, float(seconds)))
