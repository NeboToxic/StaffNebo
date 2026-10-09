"""Resolve Qt plugins with Unicode paths on Windows, before QApplication."""
from pathlib import Path
import sys
import PyQt5
from PyQt5.QtCore import QCoreApplication


def configure_qt_plugins():
    candidates = [Path(PyQt5.__file__).parent / 'Qt5' / 'plugins']
    if getattr(sys, 'frozen', False):
        candidates.insert(0, Path(sys._MEIPASS) / 'PyQt5' / 'Qt5' / 'plugins')
    for plugins in candidates:
        if (plugins / 'platforms').is_dir():
            QCoreApplication.addLibraryPath(str(plugins))
            break
