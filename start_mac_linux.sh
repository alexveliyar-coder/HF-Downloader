#!/bin/sh
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
echo "Устанавливаю зависимости..."
"$PY" -m pip install -r requirements.txt || { echo "Не удалось установить зависимости. Проверьте интернет и наличие pip."; exit 1; }
echo "Запускаю HF Downloader..."
"$PY" main.py
