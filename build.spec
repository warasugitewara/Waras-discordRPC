# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec(onedir)。`build.bat` から実行する。

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/tray_icon.png", "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WarasDiscordRPC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WarasDiscordRPC",
)
