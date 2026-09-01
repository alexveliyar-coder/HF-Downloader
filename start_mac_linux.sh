#!/bin/sh
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
echo "Installing dependencies..."
"$PY" -m pip install -r requirements.txt || { echo "Failed to install dependencies. Check your internet connection and pip."; exit 1; }
echo "Starting HF Downloader..."
"$PY" main.py
