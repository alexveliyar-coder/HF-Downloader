@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: If the py launcher exists (and isn't a Microsoft Store stub), use it;
:: otherwise use plain python. This bypasses the issue where `python` is
:: a Microsoft Store stub that opens the store instead of running a script.
set "PY=python"
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"

%PY% -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install it from https://www.python.org/downloads/
    echo and check "Add Python to PATH".
    pause
    exit /b
)

echo Checking dependencies...
%PY% -c "import requests, webview" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies. Check your internet connection and pip.
        echo Then run the script again.
        pause
        exit /b 1
    )
)
echo Starting HF Downloader...
%PY% main.py
pause
