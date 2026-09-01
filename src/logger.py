# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
logger.py — Логирование для HF Downloader.

Хранит логи в памяти (ring buffer) и в файле.
Маскирует чувствительные данные: токены, пути, имена репозиториев.
"""
import os
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / ".hfdl_log.txt"
MAX_LINES = 500


def _mask(msg):
    """Маскирует чувствительные данные в сообщении лога."""
    if not isinstance(msg, str):
        return msg

    # Токены hf_...
    msg = re.sub(r'hf_[a-zA-Z0-9]{10,}', 'hf_***MASKED***', msg)

    # Authorization Bearer
    msg = re.sub(r'(Authorization:\s*Bearer\s+)\S+', r'\1***', msg, flags=re.I)

    # URL huggingface.co/owner/repo — маскируем owner/repo (до путей файлов!)
    def _mask_hf_url(m):
        prefix = m.group(1)
        rest = m.group(2) or ''
        return prefix + '***/***' + rest

    msg = re.sub(
        r'(https?://(?:www\.)?huggingface\.co/)[^/]+/[^/\s"\']+([^\s"\']*)',
        _mask_hf_url,
        msg,
        flags=re.I,
    )

    # Пути к файлам — оставляем только последние 4 символа имени файла
    def _mask_path(m):
        p = m.group(0)
        name = os.path.basename(p)
        if len(name) > 4:
            return '***' + name[-4:]
        return '***'

    msg = re.sub(r'[A-Za-z]:\\[^"\s<>|*?]+', _mask_path, msg)
    msg = re.sub(r'(?<!:/)/[^"\s<>|*?]+\.[a-zA-Z0-9]{1,10}(?!\.[a-zA-Z])', _mask_path, msg)

    return msg


class Logger:
    def __init__(self, max_lines=MAX_LINES, log_file=LOG_FILE):
        self._lock = threading.Lock()
        self._lines = deque(maxlen=max_lines)
        self._log_file = log_file

    def warn(self, msg):
        self._add("WARN", msg)

    def error(self, msg):
        self._add("ERROR", msg)

    def _add(self, level, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        masked = _mask(msg)
        entry = {"time": ts, "level": level, "msg": masked}
        with self._lock:
            self._lines.append(entry)
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write("[%s] %s %s\n" % (ts, level, masked))
            except OSError:
                pass

    def all(self):
        with self._lock:
            return list(self._lines)

    def clear(self):
        with self._lock:
            self._lines.clear()
            try:
                with open(self._log_file, "w", encoding="utf-8") as f:
                    f.write("")
            except OSError:
                pass


logger = Logger()
