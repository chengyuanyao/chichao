# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Windows one-click itch.io build.
# Run from repo root via scripts/build_windows_release.ps1 (or pyinstaller).

import os

try:
    _spec_dir = SPECPATH
except NameError:
    _spec_dir = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.abspath(os.path.join(_spec_dir, ".."))

hiddenimports = [
    "paths",
    "catalog",
    "easter_eggs",
    "battle_report",
    "diagnostics",
    "rift_map",
    "tactical_orders",
    "formation",
    "event_stream",
]

datas = [
    (os.path.join(ROOT, "public"), "public"),
]

a = Analysis(
    [os.path.join(ROOT, "server.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["give_cash", "tkinter", "unittest", "test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChichaoSteelFront",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ChichaoSteelFront",
)
