# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for 划词助手 — Windows 单文件 exe 打包"""

from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('prototypes/settings-panel.html', 'prototypes'),
        ('.env.example', '.'),
    ] + collect_data_files('certifi'),
    hiddenimports=[
        'tkinterweb',
        'pywebview',
        'pystray',
        'PIL._imaging',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'markdown.extensions',
        'markdown.extensions.codehilite',
        'markdown.extensions.fenced_code',
        'markdown.extensions.tables',
        'markdown.extensions.toc',
        'dotenv',
        'certifi',
        'history',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'tkinter.test.test_tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='划词助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # True = 带控制台窗口（方便调试），False = 无窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
