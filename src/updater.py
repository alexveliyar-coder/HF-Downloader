# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
updater.py — Проверка обновлений HF Downloader.

Не скачивает и не устанавливает обновления сама (это слишком рискованно для
одиночного проекта). Только опрашивает GitHub Releases API, сравнивает версии
и возвращает структурированный результат. Вывод (ссылка + новая версия) ложится
в консоль — юзер сам решает, обновляться или нет.

Источник правды о версии:
  - основной: GitHub Releases API репозитория, заданного UPDATE_REPO
  - fallback: файл VERSION на том же GitHub (если релизов ещё нет)
  - для разработчиков: переменная окружения HF_DOWNLOADER_NO_UPDATE=1 отключает
    проверку (чтобы CI/тесты не спамили запросами).

Сетевые ошибки глотаются: если нет интернета или GitHub недоступен — мы молча
возвращаем None, чтобы не мешать нормальной работе программы.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional


# Эту строку обновляешь вручную при каждом релизе. Должна совпадать с тегом
# GitHub-релиза вида v1.2.3 (без префикса 'v' в самой строке).
VERSION = "1.0.0"

# Куда смотреть. Юзер может переопределить через env HUGGINGFACE_TOKEN же нет,
# через HF_DOWNLOADER_UPDATE_REPO — например, для форка.
_DEFAULT_REPO = "alexveliyar-coder/HF-Downloader"
UPDATE_REPO = os.environ.get("HF_DOWNLOADER_UPDATE_REPO", _DEFAULT_REPO).strip() or _DEFAULT_REPO

# Таймаут на запрос — 5 секунд, чтобы не подвешивать запуск.
_TIMEOUT = 5

# Маркер "сборки из исходников" (для бейджа в /version).
BUILD_CHANNEL = "source"  # PyInstaller-сборка переопределит это в "release"


def _http_json(url: str) -> Optional[dict]:
    """GET url, вернуть распарсенный JSON. На любой сетевой ошибке — None."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "HF-Downloader/%s (+https://github.com/%s)" % (VERSION, UPDATE_REPO),
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError, ValueError):
        return None


def _parse_version(s: str):
    """'1.2.3' -> (1, 2, 3). Нечисловые суффиксы игнорируются."""
    s = (s or "").strip().lstrip("v")
    parts = []
    for chunk in s.split("."):
        chunk = chunk.strip()
        # Берём только ведущие цифры, чтобы '1.2.3-beta' стало (1, 2, 3).
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            try:
                parts.append(int(digits))
            except ValueError:
                pass
    return tuple(parts) if parts else (0,)


def is_newer(latest: str, current: str = VERSION) -> bool:
    """True, если latest > current по semver-style сравнению."""
    return _parse_version(latest) > _parse_version(current)


def check_update():
    """Проверить GitHub Releases. Возвращает dict или None.

    Возвращает: {"latest": "1.2.3", "url": "...", "notes": "...", "prerelease": False}
    """
    if os.environ.get("HF_DOWNLOADER_NO_UPDATE") == "1":
        return None
    if "/" not in UPDATE_REPO or UPDATE_REPO == _DEFAULT_REPO:
        # Не сконфигурировано — молча выходим, не ругаемся на dev-машине.
        return None
    url = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
    data = _http_json(url)
    if not data or "tag_name" not in data:
        return None
    tag = str(data.get("tag_name") or "").lstrip("v")
    if not tag or not is_newer(tag):
        return None
    return {
        "latest": tag,
        "url": data.get("html_url") or ("https://github.com/" + UPDATE_REPO + "/releases"),
        "notes": data.get("body") or "",
        "prerelease": bool(data.get("prerelease")),
    }


def format_update_message(info) -> str:
    """Готовая строка для печати в консоль."""
    if not info:
        return ""
    lines = [
        "",
        "-" * 58,
        "  HF Downloader: доступна новая версия %s (у вас %s)" % (info["latest"], VERSION),
        "  " + info["url"],
    ]
    if info.get("prerelease"):
        lines.append("  (это prerelease — может быть нестабильной)")
    lines.append("-" * 58)
    return "\n".join(lines)


if __name__ == "__main__":
    # Можно дёрнуть напрямую:  python updater.py
    info = check_update()
    if info:
        print(format_update_message(info))
    else:
        print("У вас последняя версия (%s)." % VERSION)
