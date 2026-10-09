# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import PyQt5
from PyInstaller.utils.hooks.qt import pyqt5_library_info

# PyQt5 5.15.2 may report '?' instead of Unicode characters in QLibraryInfo.
# Derive wheel paths from the Python package before the PyInstaller Qt hooks run.
qt_root = Path(PyQt5.__file__).resolve().parent / 'Qt5'
old_prefix = pyqt5_library_info.location['PrefixPath']
if qt_root.is_dir():
    for key, value in tuple(pyqt5_library_info.location.items()):
        if value.startswith(old_prefix):
            pyqt5_library_info.location[key] = str(qt_root) + value[len(old_prefix):]
    pyqt5_library_info.qt_inside_package = True
    pyqt5_library_info.qt_lib_dir = qt_root / 'bin'


hiddenimports = ['pynput.keyboard._win32', 'pynput.mouse._win32', 'socks']

a = Analysis(
    ['main.py'], pathex=['.'], binaries=[], datas=[('path', 'path')],
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='NeboProject',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False, icon='path/icon.ico')
