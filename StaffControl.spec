# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('telebot')

a = Analysis(
    ['main.py'], pathex=['.'], binaries=[], datas=[('path', 'path')],
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='StaffControl',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=True, console=False, icon='path/icon.ico')
