# -*- mode: python ; coding: utf-8 -*-
"""
ImageNinja - PyInstaller spec (minimal, autodetect deps)
Build: python -m PyInstaller --noconfirm --clean ImageNinja.spec
"""
from pathlib import Path

BASE = Path('.').resolve()
block_cipher = None


a = Analysis(
    ['desktop.py'],
    pathex=[str(BASE)],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('core', 'core'),
    ],
    hiddenimports=[
        'core', 'core.upscaler', 'core.utils',
        'flask', 'flask_cors', 'PIL',
        'webview', 'webview.platforms.winforms',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy.tests', 'scipy',
        'pandas', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'test', 'tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ImageNinja',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(BASE / 'static' / 'favicon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ImageNinja',
)
