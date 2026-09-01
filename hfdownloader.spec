# -*- mode: python ; coding: utf-8 -*-
"""
hfdownloader.spec — PyInstaller spec for HF Downloader.

Build:    pyinstaller --noconfirm --clean hfdownloader.spec
Result:   dist/HF-Downloader/  (--onedir, recommended)
          or:  dist/HF-Downloader.exe  (--onefile, see APP_MODE below)

This spec is designed to be portable between Windows / macOS / Linux.
The CI in .github/workflows/release.yml uses this same spec, plus it ships
icons and macOS signing.
"""
import os
import sys
from pathlib import Path

block_cipher = None

# Mode: 'onedir' (default — fast startup, easy to debug) or 'onefile'
# (single .exe, slower startup, more annoying to antiviruses).
APP_MODE = os.environ.get("HF_APP_MODE", "onedir")

# Version from updater.py — the single source of truth.
APP_VERSION = "1.0.0"

# Icon: taken from build/icon.ico (Windows) / build/icon.icns (macOS) /
# build/icon.png (Linux). Can be omitted — a default one will be used.
ICON_PATH = None
if sys.platform == "win32":
    candidate = Path("build") / "icon.ico"
    if candidate.exists():
        ICON_PATH = str(candidate)
elif sys.platform == "darwin":
    candidate = Path("build") / "icon.icns"
    if candidate.exists():
        ICON_PATH = str(candidate)

# Data placed next to the exe (not .py sources).
# Format: (source, relative path inside the build).
DATA_FILES = [
    ("site", "site"),
    ("locales", "locales"),
]

# Python module search path. main.py lives in the root, other modules are in
# src/. PyInstaller will find them via AST analysis of main.py, but we
# add src/ explicitly in case Analysis misses dynamic imports.
sys.path.insert(0, str(Path("src").resolve()))

# Hidden imports that PyInstaller can't find via static analysis.
# pywebview needs a backend module per OS; requests pulls in urllib3.
HIDDEN_IMPORTS = [
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "webview.platforms.cocoa",
    "webview.platforms.gtk",
    "webview.platforms.qt",
    "urllib3",
    "requests",
]

# One-liner (handy for grepping logs).
EXE_NAME = "HF-Downloader" + (".exe" if sys.platform == "win32" else "")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Don't drag extra stuff into the build — keeps it smaller.
        "tkinter",
        "test",
        "unittest",
        "pytest",
        "IPython",
        "numpy",
        "pandas",
        "matplotlib",
        "PIL",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Build the exe.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # for onedir — binaries separate; for onefile — None
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX often triggers antiviruses; leave it off
    console=False,  # --windowed: no black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,  # macOS: signing is configured in CI
    entitlements_file=None,
    icon=ICON_PATH,
)

if APP_MODE == "onefile":
    # onefile: pack everything into a single binary.
    exe.exclude_binaries = False
    coll = COLLECT(exe) if False else None  # noqa
    # In onefile mode there's no coll — the exe already contains everything.
else:
    # onedir: binaries and data in a subfolder.
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=EXE_NAME.replace(".exe", ""),
    )
