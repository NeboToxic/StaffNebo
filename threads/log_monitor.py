import os
from PyQt5.QtCore import QThread, pyqtSignal


class LogMonitorThread(QThread):

    update_signal = pyqtSignal(str)
    log_line_signal = pyqtSignal(str)

    def __init__(self, logs_path: str):
        super().__init__()
        self.logs_path = logs_path
        self.running = True
        self.last_position = 0
        self.first_run = True

    def run(self):
        self.update_signal.emit(f"[SYSTEM] Мониторинг логов запущен для: {self.logs_path}")

        while self.running:
            try:
                self._check_logs()
                self.msleep(100)
            except Exception as e:
                self.update_signal.emit(f"[ERROR] В функции check_logs: {e}")
                self.msleep(1000)

    def stop(self):
        self.running = False
        if self.isRunning():
            self.wait(2000)

    def _check_logs(self):
        try:
            with open(self.logs_path, 'r', encoding='utf-8', errors='ignore') as file:
                file.seek(0, os.SEEK_END)
                current_size = file.tell()

                if self.first_run:
                    self.last_position = current_size
                    self.first_run = False
                    return

                if current_size < self.last_position:
                    self.update_signal.emit("[SYSTEM] Файл логов был пересоздан, начинаем чтение с начала.")
                    self.last_position = 0

                if current_size <= self.last_position:
                    return

                file.seek(self.last_position)
                new_lines = file.readlines()
                self.last_position = file.tell()

                for line in new_lines:
                    line = line.strip()
                    if line:
                        self.log_line_signal.emit(line)

        except FileNotFoundError:
            self.update_signal.emit(f"[ERROR] Файл логов {self.logs_path} не найден!")
            self.msleep(5000)
        except Exception as e:
            self.update_signal.emit(f"[ERROR] Ошибка при чтении логов: {e}")
            self.msleep(1000)