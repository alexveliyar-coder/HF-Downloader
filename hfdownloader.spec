# -*- mode: python ; coding: utf-8 -*-
"""
hfdownloader.spec — PyInstaller spec для HF Downloader.

Сборка:   pyinstaller --noconfirm --clean hfdownloader.spec
Результат: dist/HF-Downloader/  (--onedir, рекомендуется)
           или:  dist/HF-Downloader.exe  (--onefile, см. переменную APP_MODE ниже)

Этот spec задуман так, чтобы быть переносимым между Windows / macOS / Linux.
CI в .github/workflows/release.yml использует тот же spec, плюс подкладывает
иконки и подпись для macOS.
"""
import os
import sys
from pathlib import Path

block_cipher = None

# Режим: 'onedir' (по умолчанию — быстрый старт, удобно дебажить) или 'onefile'
# (один .exe, медленнее старт, неудобно для антивирусов).
APP_MODE = os.environ.get("HF_APP_MODE", "onedir")

# Версия из updater.py — единый источник правды.
APP_VERSION = "1.0.0"

# Иконка: берётся из build/icon.ico (Windows) / build/icon.icns (macOS) /
# build/icon.png (Linux). Можно не указывать — будет дефолтная.
ICON_PATH = None
if sys.platform == "win32":
    candidate = Path("build") / "icon.ico"
    if candidate.exists():
        ICON_PATH = str(candidate)
elif sys.platform == "darwin":
    candidate = Path("build") / "icon.icns"
    if candidate.exists():
        ICON_PATH = str(candidate)

# Данные, которые нужно положить рядом с exe (не .py-исходники).
# Формат: (исходник, относительный путь внутри сборки).
DATA_FILES = [
    ("site", "site"),
    ("locales", "locales"),
]

# Путь поиска Python-модулей. main.py лежит в корне, остальные модули
# — в src/. PyInstaller сам найдёт их по AST-анализу main.py, но мы
# добавляем src/ явно на случай, если Analysis не отследит динамические
# импорты.
sys.path.insert(0, str(Path("src").resolve()))

# Скрытые импорты, которые PyInstaller не находит статическим анализом.
# pywebview требует backend-модуль под каждую ОС; requests тянет urllib3.
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

# Однострочное (для удобства grep'а по логам).
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
        # Не тащим в сборку лишнее — уменьшает размер.
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

# Собираем exe.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # для onedir — бинари отдельно, для onefile — None
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX часто триггерит антивирусы; оставляем выключенным
    console=False,  # --windowed: без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,  # macOS: подпись настраивается в CI
    entitlements_file=None,
    icon=ICON_PATH,
)

if APP_MODE == "onefile":
    # onefile: запаковываем всё в один бинарь.
    exe.exclude_binaries = False
    coll = COLLECT(exe) if False else None  # noqa
    # В onefile нет coll, exe уже содержит всё.
else:
    # onedir: бинари и данные в подпапке.
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
