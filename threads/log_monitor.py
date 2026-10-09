import os
from PyQt5.QtCore import pyqtSignal
from threads.base import StoppableThread


class LogMonitorThread(StoppableThread):
    update_signal = pyqtSignal(str)
    log_line_signal = pyqtSignal(str)

    def __init__(self, logs_path):
        super().__init__()
        self.logs_path = logs_path
        self.last_position = 0
        self.first_run = True
        self._identity = None
        self._pending = b''
        self._checkpoint = b''
        self._missing = False

    def run(self):
        self.update_signal.emit(f'[SYSTEM] Мониторинг логов запущен для: {self.logs_path}')
        while not self.should_stop:
            self._check_logs()
            self.pause(0.1 if not self._missing else 1)

    def _check_logs(self):
        try:
            with open(self.logs_path, 'rb') as file:
                stat = os.fstat(file.fileno())
                identity = (stat.st_dev, stat.st_ino)
                size = stat.st_size
                if self.first_run:
                    self.last_position = size
                    self.first_run = False
                else:
                    replaced = self._missing or identity != self._identity or size < self.last_position
                    if not replaced and self._checkpoint:
                        file.seek(self.last_position - len(self._checkpoint))
                        replaced = file.read(len(self._checkpoint)) != self._checkpoint
                    if replaced:
                        self.last_position = 0
                        self._pending = b''
                        self.update_signal.emit('[SYSTEM] Файл логов пересоздан, чтение с начала.')
                    file.seek(self.last_position)
                    data = self._pending + file.read()
                    self.last_position = file.tell()
                    lines = data.split(b'\n')
                    self._pending = lines.pop()
                    for raw in lines:
                        line = raw.decode('utf-8', errors='replace').strip()
                        if line:
                            self.log_line_signal.emit(line)
                self._identity = identity
                self._missing = False
                file.seek(max(0, self.last_position - 64))
                self._checkpoint = file.read(self.last_position - file.tell())
        except FileNotFoundError:
            if not self._missing:
                self.update_signal.emit(f'[ERROR] Файл логов {self.logs_path} не найден!')
            self._missing = True
        except Exception as exc:
            self.update_signal.emit(f'[ERROR] Ошибка чтения логов: {exc}')
