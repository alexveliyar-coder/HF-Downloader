@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Если есть py-лаунчер (он не является Store-заглушкой), используем его;
:: иначе — обычный python. Это обходит проблему, когда `python` — это
:: заглушка Microsoft Store, открывающая магазин вместо запуска скрипта.
set "PY=python"
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"

%PY% -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите его с https://www.python.org/downloads/
    echo и поставьте галочку "Add Python to PATH".
    pause
    exit /b
)

echo Проверяю зависимости...
%PY% -c "import requests, webview" >nul 2>nul
if errorlevel 1 (
    echo Устанавливаю зависимости...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Не удалось установить зависимости. Проверьте интернет и наличие pip.
        echo Затем запустите скрипт снова.
        pause
        exit /b 1
    )
)
echo Запускаю HF Downloader...
%PY% main.py
pause
