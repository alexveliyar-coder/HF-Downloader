# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
HF Core Server — локальное ядро загрузчика (запускается на ВАШЕМ ПК).

Использует ядро вашего оригинального скрипта:
  - requests + stream=True, чанки по 1 МБ
  - Authorization: Bearer <token>
  - коды 401/403 -> "нужен токен", 404 -> "файл не найден"
  - папки скачиваются по одному файлу (с прогрессом и паузой)
  + докачка через Range: прерванный файл лежит в *.part и продолжается
    с того же байта, а не заново.

Запуск:
    pip install requests
    python hf_core_server.py

Сервер слушает ТОЛЬКО 127.0.0.1:8765 (недоступен из интернета).
Файлы сохраняются в папку "downloads" рядом со скриптом.
"""
import json
import itertools
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

# Allow running this file directly (`python src/hf_core_server.py`) — its
# sibling modules live next to it, so this is a no-op in that case, but it
# also works when invoked from the project root via `python -m src.hf_core_server`.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Локализация
from locale_loader import get_locale, init_locale, SUPPORTED_LANGUAGES
from logger import logger

# Глобальная локаль для сервера (инициализируется при старте)
_server_locale = None

HOST = "127.0.0.1"
PORT = 8765
WEB_PORT = 8777  # порт сайта по умолчанию (см. main.py)
# Фактический порт сайта. main.py выбирает свободный порт (если WEB_PORT
# занят) и сообщает его ядру через set_web_port(), иначе CORS/Origin не
# совпадут с реальным портом и все запросы фронтенда получат 403.
_actual_web_port = WEB_PORT

def set_web_port(port):
    """Обновить разрешённый порт сайта (его выбирает main.py динамически)."""
    global _actual_web_port, ALLOWED_ORIGINS
    _actual_web_port = port
    ALLOWED_ORIGINS = (
        "http://127.0.0.1:%d" % port,
        "http://localhost:%d" % port,
    )

def find_free_port(host, start_port, max_tries=20):
    """Найти свободный порт, держа сокет открытым, чтобы исключить гонку
    (TOCTOU) между проверкой порта и его bind-ом сервером.

    Возвращает (socket, port). Сокет уже привязан и остаётся открытым —
    вызывающий обязан передать его в ThreadingHTTPServer (см. start_in_thread),
    иначе порт может быть перехвачен другим процессом в промежутке.
    """
    last_err = None
    for p in range(start_port, start_port + max_tries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, p))
            return s, p
        except OSError as e:
            last_err = e
            s.close()
            continue
    # Крайний случай: всё занято — возвращаем сокет на start_port (bind может
    # упасть при старте сервера, но это лучше молчаливого выбора занятого порта).
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, start_port))
    return s, start_port
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.join(_PROJECT_ROOT, "downloads")
CHUNK = 4 * 1024 * 1024  # 4 МБ
BOOKMARKS_FILE = os.path.join(_PROJECT_ROOT, "hfdl_bookmarks.json")

# Доступ к ядру разрешён только локальному интерфейсу. Без проверки Origin любой
# сайт в браузере мог бы записать задачи/пути на ваш ПК (недоступно из сети —
# сервер слушает 127.0.0.1, но страницы зовут его из браузера).
ALLOWED_ORIGINS = (
    "http://127.0.0.1:%d" % WEB_PORT,
    "http://localhost:%d" % WEB_PORT,
)

_actual_port = PORT

TASKS = {}            # id -> dict (активные/ожидающие задачи)
# Счётчик для уникальных id задач (исключает коллизию при создании в один
# микросекунду): id = "t<время>-<счётчик>".
_tid_seq = itertools.count(1)
# Завершённые (done/error) задачи. Они НЕ удаляются из памяти сразу, а переносятся
# сюда: фронтенд опрашивает статус по GET /api/tasks/{id} и должен увидеть "done",
# а кнопка «показать в папке» — найти точный путь. Иначе скачанный файл «висит» как
# качающийся и открывается не то место (безопасно чистится "Clear finished").
HISTORY = {}
LOCK = threading.Lock()

# Глобальный режим «по очереди» (обновляется при каждом POST /api/tasks).
# Нужен, чтобы завершившаяся задача знала, запускать одну следующую или все.
_seq_mode = False

# Глобальная ссылка на сервер для graceful shutdown
_server_instance = None
_TASKS_FILE = os.path.join(_PROJECT_ROOT, ".tasks.json")
LANG_FILE = os.path.join(_PROJECT_ROOT, ".lang.txt")
LAST_DIR_FILE = os.path.join(_PROJECT_ROOT, ".last_dir.txt")


def load_tasks_state():
    """Загрузить состояние активных задач из файла при старте."""
    try:
        with open(_TASKS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            # Восстанавливаем задачи в статусе "downloading" и "paused"
            restored = {}
            for t in data:
                if t.get("status") in ("downloading", "paused"):
                    t["run"] = threading.Event()
                    t["cancel"] = False
                    if t["status"] == "paused":
                        t["run"].clear()
                    else:
                        t["run"].set()
                    # Токен не сохранялся на диск — для приватных репозиториев
                    # докачка без него упадёт с 401 (фронтенд покажет «нужен токен»).
                    t.setdefault("token", "")
                    restored[t.get("id", "")] = t
            return restored
    except (OSError, ValueError):
        logger.warn("load_tasks_state failed")
        return {}


def save_tasks_state():
    """Сохранить состояние активных задач в файл."""
    try:
        active = []
        with LOCK:
            for tid, st in TASKS.items():
                if st["status"] in ("downloading", "paused"):
                    # Убираем threading.Event (нельзя сериализовать) и токен
                    # (не храним credential в открытом виде на диске).
                    entry = {k: v for k, v in st.items()
                             if not isinstance(v, threading.Event) and k != "token"}
                    entry["id"] = tid
                    active.append(entry)
        with open(_TASKS_FILE, "w", encoding="utf-8") as fh:
            json.dump(active, fh, ensure_ascii=False, indent=2)
    except OSError:
        logger.warn("save_tasks_state failed")


def _shutdown_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown."""
    global _server_instance
    print("\n\nПолучен сигнал остановки — сохраняю состояние задач...")
    
    # Устанавливаем cancel для всех активных задач
    with LOCK:
        for tid, st in TASKS.items():
            if st["status"] in ("downloading", "paused"):
                st["cancel"] = True
                st["run"].set()  # Разрешаем потоку выйти из цикла паузы
    
    # Сохраняем состояние задач
    save_tasks_state()
    
    # Корректно останавливаем сервер (не вызывает KeyboardInterrupt)
    if _server_instance:
        _server_instance.shutdown()


def _read_saved_lang():
    """Сохранённый выбор языка пользователя (.lang.txt, пишется при смене)."""
    try:
        with open(LANG_FILE, "r", encoding="utf-8") as fh:
            code = fh.read().strip().lower()
        if code in SUPPORTED_LANGUAGES:
            return code
    except OSError:
        pass
    return None


def load_bookmarks():
    try:
        with open(BOOKMARKS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except (OSError, ValueError):
        import sys; sys.stderr.write("  [warn] load_bookmarks failed\n")
    return []


def save_bookmarks(items):
    clean = []
    for x in items:
        s = str(x or "").strip()
        if s and s not in clean:
            clean.append(s)
    try:
        with open(BOOKMARKS_FILE, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, ensure_ascii=False, indent=2)
    except OSError:
        import sys; sys.stderr.write("  [warn] save_bookmarks failed\n")
    return clean


def load_last_dir():
    try:
        with open(LAST_DIR_FILE, "r", encoding="utf-8") as fh:
            p = fh.read().strip()
        if p and os.path.isdir(p):
            return p
    except OSError:
        import sys; sys.stderr.write("  [warn] load_last_dir failed\n")
    return BASE_DIR


def save_last_dir(path):
    try:
        with open(LAST_DIR_FILE, "w", encoding="utf-8") as fh:
            fh.write(path)
    except OSError:
        import sys; sys.stderr.write("  [warn] save_last_dir failed\n")


def resolve_choose_initial_dir(requested):
    """Начальная папка для диалога выбора: то, что прислал фронтенд из поля «Путь».

    Абсолютный путь либо подпапка BASE_DIR; если существует — открываем её,
    иначе ближайшую существующую (родителя) или сам BASE_DIR.
    """
    cur = (requested or "").strip().strip('"').strip("'")
    if not cur:
        return BASE_DIR
    if os.path.isabs(cur):
        cand = os.path.abspath(cur)
    else:
        cand = os.path.abspath(os.path.join(BASE_DIR, cur))
    if os.path.isdir(cand):
        return cand
    parent = os.path.dirname(cand)
    if parent and os.path.isdir(parent):
        return parent
    return BASE_DIR


def _python_cmd():
    """Надёжный интерпретатор Python для subprocess (Windows).

    Проблема: если приложение запущено через `python main.py`, а `python` —
    это Microsoft Store заглушка (C:\\Users\\...\\WindowsApps\\python.exe),
    то sys.executable указывает на неё, и subprocess не может выполнить
    скрипт чтения буфера. Поэтому проверяем sys.executable, затем py -3.
    """
    if os.name != "nt":
        return [sys.executable]
    # 1) sys.executable — если это настоящий Python
    try:
        out = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return [sys.executable]
    except Exception:
        pass
    # 2) py -3 — лаунчер Windows (находит настоящий Python)
    try:
        out = subprocess.run(
            ["py", "-3", "-c", "import sys; print(sys.version_info[:2])"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return ["py", "-3"]
    except Exception:
        pass
    return []


def clipboard_text():
    """Текст из системного буфера обмена.

    Почему не navigator.clipboard: в окне pywebview/WebView2 нет UI запроса
    разрешения ClipboardReadPermission, поэтому navigator.clipboard.readText()
    всегда отклоняется (NotAllowedError) и автовставка не работает.

    Читаем буфер в ОТДЕЛЬНОМ процессе с жёстким таймаутом. Это важно: если
    владельцем буфера стал сам WebView2 (копирование внутри окна приложения),
    GetClipboardData блокируется до отложенного рендера. В отдельном процессе
    по таймауту это гарантирует, что ядро никогда не зависнет.

    Возвращает текст или пустую строку, никогда не бросает исключений.
    """
    if os.name == "nt":
        # Windows: читаем буфер напрямую через ctypes в отдельном процессе
        # (см. _CLIP_WORKER) — надёжно даже при владении буфером WebView2.
        try:
            out = subprocess.run(
                _python_cmd() + ["-c", _CLIP_WORKER],
                capture_output=True, text=True, encoding="utf-8", timeout=2,
            )
            return out.stdout or ""
        except Exception:
            return ""

    # macOS / Linux: штатные утилиты буфера обмена (лучшее усилие). Если их
    # нет — тихо возвращаем пустую строку (функция никогда не падает).
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
            return out.stdout or ""
        # Linux: сначала xclip, затем xsel; при отсутствии — пустая строка.
        for cmd in (["xclip", "-selection", "clipboard", "-o"], ["xsel", "-b", "-o"]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if out.returncode == 0:
                    return out.stdout or ""
            except (OSError, subprocess.SubprocessError):
                continue
    except Exception:
        pass
    return ""


# Отдельный процесс читает буфер напрямую через ctypes (без импорта модуля —
# быстрый старт ~50-100 мс; весь hf_core_server + requests не нужны).
_CLIP_WORKER = r"""import ctypes,sys
from ctypes import wintypes
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
u=ctypes.windll.user32
k=ctypes.windll.kernel32
if not u.OpenClipboard(0):
    sys.exit(0)
u.GetClipboardData.restype=wintypes.HANDLE
u.GetClipboardData.argtypes=[wintypes.UINT]
k.GlobalLock.restype=wintypes.LPVOID
k.GlobalLock.argtypes=[wintypes.HGLOBAL]
k.GlobalSize.restype=ctypes.c_size_t
k.GlobalSize.argtypes=[wintypes.HGLOBAL]
k.GlobalUnlock.argtypes=[wintypes.HGLOBAL]
try:
    h=u.GetClipboardData(13) or u.GetClipboardData(1)
    if not h:
        sys.exit(0)
    p=k.GlobalLock(h)
    if not p:
        sys.exit(0)
    try:
        n=k.GlobalSize(h)
        if u.IsClipboardFormatAvailable(13):
            out=ctypes.wstring_at(p,n//2).rstrip('\x00')
        else:
            out=ctypes.string_at(p,n).rstrip(b'\x00').decode('mbcs','replace')
        sys.stdout.write(out)
    finally:
        k.GlobalUnlock(h)
finally:
    u.CloseClipboard()
"""


class CoreError(Exception):
    def __init__(self, status, msg=""):
        super().__init__(msg or ("HTTP %d" % status))
        self.status = status


def sanitize(name):
    """Имя файла без недопустимых символов и '..'."""
    s = re.sub(r'[\\/:"*?<>|#%&{}$!\'@+=`~^]', "_", str(name or "file")).strip()
    s = s.lstrip(".").rstrip(".") or "file"
    return s[:180]


def safe_subdir(rel, allow_absolute=True):
    """Папка для сохранения.

    - относительный путь (например "models", "a/b") — подпапка внутри BASE_DIR;
    - абсолютный путь (например "C:/Users/V/Music" на Windows) — используется
      как есть, чтобы кнопка «Обзор…» и закладки реально сохраняли туда, куда
      выбрал пользователь.
    Компоненты "." и ".." отбрасываются — выйти за пределы нельзя.
    """
    raw = str(rel or "").strip()
    if not raw:
        return BASE_DIR
    norm = os.path.normpath(raw)
    if allow_absolute and os.path.isabs(norm):
        return os.path.abspath(norm)
    parts = []
    for p in raw.replace("\\", "/").split("/"):
        if not p or p in (".", ".."):
            continue
        parts.append(sanitize(p))
    full = os.path.abspath(os.path.join(BASE_DIR, *parts))
    if full != BASE_DIR and not full.startswith(BASE_DIR + os.sep):
        raise CoreError(400, "bad path")
    return full


def hf_headers(token):
    h = {}
    if token:
        h["Authorization"] = "Bearer %s" % token
    return h


def parse_link(raw):
    """Разбор ссылки: файл (blob/resolve) или репозиторий."""
    url = raw.strip().strip("'\"")
    m = re.match(r"^https?://(?:www\.)?huggingface\.co/.+", url, re.I)
    if not m:
        return None
    branch = "main"
    if "/blob/" in url or "/resolve/" in url:
        direct = url.replace("/blob/", "/resolve/").split("?")[0].rstrip("/")
        name = urllib.parse.unquote(direct.split("/")[-1])
        # Файлы без точки в имени (LICENSE, README, Dockerfile, config и т.п.)
        # — валидны для Hugging Face, поэтому проверяем только непустое имя.
        if not name:
            return None
        # Ветка из сегмента /resolve/<branch>/ или /blob/<branch>/.
        # Префикс (datasets/spaces) добавляет компонент пути, поэтому берём
        # ветку по шаблону, а не по фиксированному индексу (иначе для
        # datasets/spaces ветка определялась бы как "resolve").
        bm = re.search(r"/(?:blob|resolve)/([^/?#]+)", direct)
        if bm:
            branch = bm.group(1)
        return {"kind": "file", "url": direct, "name": name, "branch": branch}
    # Ветка из /tree/<branch> в репозитории
    tm = re.search(r"/tree/([^/?#]+)", url)
    if tm:
        branch = tm.group(1)
    path = urllib.parse.urlparse(url).path.strip("/").split("/")
    rtype = "models"
    if path and path[0] in ("datasets", "spaces") and len(path) >= 3:
        rtype = path[0]
        path = path[1:]
    if len(path) >= 2:
        return {"kind": "repo", "repo": "/".join(path[:2]), "rtype": rtype, "branch": branch}
    return None


def repo_file_url(rtype, repo, fpath, branch="main"):
    prefix = "" if rtype == "models" else rtype + "/"
    enc = "/".join(urllib.parse.quote(p) for p in fpath.split("/"))
    return "https://huggingface.co/%s%s/resolve/%s/%s" % (prefix, repo, branch, enc)


def _next_cursor(resp):
    """Курсор следующей страницы дерева из заголовка Link (rel="next").

    HF-API пагинирует через заголовок вида
        Link: <...?cursor=ZXlKbWFXeGxYMjVoYldVaU9pOj...>; rel="next"
    Возвращает строку-курсор или None, если страниц больше нет.
    """
    link = resp.headers.get("Link") or ""
    m = re.search(r"<([^>]+)>\s*;\s*rel=\"next\"", link, re.I)
    if not m:
        return None
    q = urllib.parse.parse_qs(urllib.parse.urlparse(m.group(1)).query)
    cur = q.get("cursor")
    return cur[0] if cur else None


def fetch_tree(rtype, repo, token, branch="main"):
    """Список файлов репозитория (полностью, с пагинацией по курсору).

    Дерево HF-API возвращает не более 1000 записей за один запрос (limit),
    поэтому для репозиториев крупнее этой цифры листаем страницы: берём
    курсор из заголовка Link ...; rel="next" и повторяем запрос, пока он
    присутствует. Иначе папка скачивалась бы не полностью (обрыв на 1000).
    """
    api = "https://huggingface.co/api/%s/%s/tree/%s" % (rtype, repo, branch)
    params = {"recursive": "true", "expand": "false", "limit": 1000}
    out = []
    while True:
        res = requests.get(api, params=params, headers=hf_headers(token), timeout=30)
        if res.status_code in (401, 403):
            raise CoreError(res.status_code)
        if res.status_code == 404:
            raise CoreError(404)
        res.raise_for_status()
        for f in res.json():
            if f.get("type") == "file" and isinstance(f.get("path"), str):
                size = f.get("size") or (f.get("lfs") or {}).get("size") or 0
                out.append({"path": f["path"], "size": int(size)})
        cursor = _next_cursor(res)
        if not cursor:
            break
        params["cursor"] = cursor
    return out


def stream_to_file(url, dest, token, st):
    """Стриминг в файл с паузой и докачкой через Range (ядро вашего скрипта)."""
    headers = hf_headers(token)
    part = dest + ".part"
    start = os.path.getsize(part) if os.path.exists(part) else 0
    
    # Пробуем начать докачку, если есть .part файл
    resume_attempted = False
    if start > 0:
        headers["Range"] = "bytes=%d-" % start
        resume_attempted = True

    res = requests.get(url, headers=headers, stream=True, timeout=(15, 900))
    try:
        if res.status_code in (401, 403):
            raise CoreError(res.status_code)
        if res.status_code == 404:
            raise CoreError(404)
        
        # Определяем режим работы при попытке докачки:
        # - 206 Partial Content — сервер поддерживает Range, докачиваем с начала .part
        # - 200 OK + Content-Range — редкий случай (некоторые CDN), но есть заголовок range
        # - 200 OK без Content-Range — сервер игнорирует Range, скачиваем заново
        content_range = res.headers.get("Content-Range", "")
        if resume_attempted:
            if res.status_code == 206:
                # Сервер поддерживает Range — докачиваем (.part остаётся).
                mode = "ab"
            else:
                # Сервер проигнорировал Range (вернул 200) либо статус
                # некорректен — качаем заново с начала, сбрасываем .part.
                # ВАЖНО: всегда wb + start=0, иначе полное тело дописалось бы
                # поверх частичного файла и испортило бы его.
                start = 0
                resume_attempted = False

        res.raise_for_status()
        
        content_length = int(res.headers.get("content-length") or 0)
        if resume_attempted and res.status_code == 206:
            # Content-Range: bytes N-M/T — T это полный размер
            cr_match = re.match(r"bytes\s+\d+-\d+\/(\d+)", content_range, re.I)
            if cr_match:
                total_size = int(cr_match.group(1))
            else:
                total_size = start + content_length
        else:
            total_size = content_length
        
        mode = "ab" if (resume_attempted and res.status_code == 206) else "wb"

        downloaded = start
        last_t, last_b, speed = time.time(), start, 0.0
        limit = st.get("speed_limit") or 0
        limit_b = limit * 1024 * 1024  # MB/s -> bytes/s
        window_start = time.monotonic()
        window_bytes = 0
        with open(part, mode) as fh:
            for chunk in res.iter_content(chunk_size=CHUNK):
                # пауза: ждём, пока не разрешат продолжать
                while not st["run"].is_set():
                    if st["cancel"]:
                        raise CoreError(-2, "cancelled")
                    time.sleep(0.2)
                if st["cancel"]:
                    raise CoreError(-2, "cancelled")
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    window_bytes += len(chunk)
                    now = time.time()
                    dt = now - last_t
                    if dt >= 0.4:
                        inst = (downloaded - last_b) / dt
                        # Лёгкое сглаживание (0.2/0.8): показываем ФАКТИЧЕСКУЮ
                        # текущую скорость, а не среднее за всю загрузку.
                        # Раньше было 0.6/0.4 — жёсткое EMA «съедало» реальные
                        # всплески и индикатор показывал почти суммарную скорость.
                        speed = speed * 0.2 + inst * 0.8 if speed > 0 else inst
                        last_t, last_b = now, downloaded
                    # Ограничение скорости: «честное» усреднение. Считаем,
                    # сколько байт разрешено скачать за прошедшее с начала
                    # окна время, и если уже скачали больше — спим ровно
                    # столько, сколько нужно, чтобы вернуться в лимит.
                    # Старая логика со сбросом window_bytes через 1 сек
                    # работала только при chunk_size < limit_b; для крупных
                    # чанков (4 МБ) и лимита 1-5 MB/s фактически не лимитировала.
                    if limit_b > 0:
                        wnow = time.monotonic()
                        wdt = wnow - window_start
                        # Разрешённый объём за wdt секунд:
                        allowed = limit_b * wdt
                        if window_bytes > allowed:
                            over = window_bytes - allowed
                            sleep_s = over / limit_b
                            # Спим нужное время, но с проверкой флагов каждые
                            # 0.2 сек, чтобы юзер мог отменить/поставить на
                            # паузу даже при очень низких лимитах (1 MB/s)
                            # и больших чанках (4 МБ) — иначе на пиковой скорости
                            # источника пришлось бы блокировать поток на 4 сек.
                            slept = 0.0
                            while slept < sleep_s:
                                if st["cancel"]:
                                    raise CoreError(-2, "cancelled")
                                if not st["run"].is_set():
                                    raise CoreError(-2, "paused")
                                step = min(0.2, sleep_s - slept)
                                time.sleep(step)
                                slept += step
                            wnow = time.monotonic()
                            wdt = wnow - window_start
                            allowed = limit_b * wdt
                            if window_bytes > allowed:
                                # Окно продолжаем с этого момента, чтобы
                                # следующие чанки считали отсюда. Не сбрасываем
                                # window_bytes — иначе после паузы лимит сбивается.
                                window_start = wnow - (window_bytes / limit_b)
                    with LOCK:
                        st["downloaded"] = st["base"] + (downloaded - start)
                        st["total"] = st["base_total"] if st["base_total"] else (st["base"] + total_size)
                        st["speed"] = speed
        
        # Если докачка не удалась — удаляем .part и начинаем с чистого листа
        if not resume_attempted and start > 0:
            os.remove(part)
        
        os.replace(part, dest)
        return os.path.getsize(dest)
    finally:
        res.close()


def open_location(path):
    """Открыть файл/папку в системном файловом менеджере.

    Для файла выделяем его в проводнике (Windows: explorer /select,
    macOS: open -R), для папки открываем её. Возвращает True, если
    путь существует и открытие запущено.
    """
    if not path or not os.path.exists(path):
        return False
    path = os.path.abspath(path)
    try:
        if os.name == "nt":
            if os.path.isfile(path):
                subprocess.Popen(["explorer.exe", "/select,", path])
            else:
                os.startfile(path)
        elif sys.platform == "darwin":
            if os.path.isfile(path):
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        return False
    return True


def _start_next_if_seq():
    """Запустить следующую ожидающую задачу, если включён режим «по очереди».

    Вызывается после завершения/ошибки/отмены задачи. В режиме seq запускаем
    строго одну следующую (FIFO: ищем с конца, потому что новые задачи
    добавляются в начало словаря) и только если прямо сейчас ничего не качается
    — иначе при включении seq поверх уже идущих задач конкурентность росла бы.
    Если seq выключен — ничего не делаем: фронтенд сам запускает все ожидающие.
    """
    global _seq_mode
    if not _seq_mode:
        return
    with LOCK:
        # Строго одна активная задача: если уже что-то качается — не запускаем.
        if any(s["status"] == "downloading" for s in TASKS.values()):
            return
        # Ищем ожидающую задачу с конца (самую старую из добавленных)
        for tid in reversed(list(TASKS.keys())):
            st = TASKS[tid]
            if st["status"] == "waiting":
                st["status"] = "downloading"
                threading.Thread(target=run_task, args=(tid,), daemon=True).start()
                return


def run_task(tid):
    st = TASKS[tid]
    branch = st.get("branch", "main")
    max_retries = st.get("max_retries", 3)
    
    def _sleep_with_cancel(seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if st["cancel"]:
                raise CoreError(-2, "cancelled")
            time.sleep(0.2)
    
    def _do_file_download():
        dest = os.path.join(st["dir"], sanitize(st["name"]))
        # Если файл уже на диске и HEAD подтверждает совпадение размера —
        # считаем его скачанным, не трогаем. Экономим трафик и не затираем
        # уже имеющиеся данные.
        if os.path.exists(dest):
            try:
                head = requests.head(
                    st["url"],
                    headers=hf_headers(st.get("token", "")),
                    allow_redirects=True,
                    timeout=(10, 30),
                )
                head.raise_for_status()
                expected = int(head.headers.get("content-length") or 0)
                head.close()
                if expected > 0 and os.path.getsize(dest) == expected:
                    st["downloaded"] = st.get("total") or expected
                    st["files_done"] = 1
                    st["files_total"] = 1
                    st["had_skip"] = True
                    logger.warn("File already on disk with matching size, skipping: %s" % os.path.basename(dest))
                    return expected
            except Exception as _e:
                # HEAD упал (нет сети / 405 / таймаут) — лучше качать заново,
                # чем зависнуть на пропуске. Не считаем это ошибкой юзера.
                logger.warn("HEAD probe failed for %s, will re-download: %s" % (os.path.basename(dest), _e))
        return stream_to_file(st["url"], dest, st.get("token", ""), st)

    def _do_fetch_tree():
        return fetch_tree(st["rtype"], st["repo"], st.get("token", ""), branch)

    def _do_repo_download():
        if not st["files"]:
            st["files"] = _do_fetch_tree()
            st["files_total"] = len(st["files"])
            st["total"] = sum(f["size"] for f in st["files"])
            st["base_total"] = st["total"]
        for i in range(st["file_index"], len(st["files"])):
            f = st["files"][i]
            st["file_index"] = i
            st["current"] = f["path"]
            dest = os.path.join(st["dir"], *[sanitize(p) for p in f["path"].split("/")])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # Пропуск уже скачанного: если файл на диске и его размер совпадает
            # с тем, что говорит API репо — оставляем как есть, не качаем.
            if os.path.exists(dest) and f.get("size", 0) > 0 and os.path.getsize(dest) == f["size"]:
                got = f["size"]
                st["had_skip"] = True
                logger.warn("Already on disk, skipping: %s" % f["path"])
            else:
                got = stream_to_file(repo_file_url(st["rtype"], st["repo"], f["path"], branch),
                                     dest, st.get("token", ""), st)
            st["base"] += got
            st["files_done"] = i + 1
            st["file_index"] = i + 1
            st["downloaded"] = st["base"]
    
    try:
        os.makedirs(st["dir"], exist_ok=True)
        st["status"] = "downloading"
        
        if st["kind"] == "file":
            while True:
                try:
                    _do_file_download()
                    break
                except requests.exceptions.RequestException:
                    st["retries"] = st.get("retries", 0) + 1
                    if st["retries"] > max_retries:
                        raise
                    delay = st.get("retry_delay", 2)
                    st["current"] = "retry %d/%d in %ds" % (st["retries"], max_retries, delay)
                    _sleep_with_cancel(delay)
                    st["retry_delay"] = min(delay * 2, 30)
                    st["current"] = ""
            st["status"] = "done"
            st["speed"] = 0
        else:
            while True:
                try:
                    _do_repo_download()
                    break
                except requests.exceptions.RequestException:
                    st["retries"] = st.get("retries", 0) + 1
                    if st["retries"] > max_retries:
                        raise
                    delay = st.get("retry_delay", 2)
                    st["current"] = "retry %d/%d in %ds" % (st["retries"], max_retries, delay)
                    _sleep_with_cancel(delay)
                    st["retry_delay"] = min(delay * 2, 30)
                    st["current"] = ""
            st["status"] = "done"
            st["speed"] = 0
    except CoreError as e:
        st["status"] = "error"
        st["error"] = "http_%d" % e.status
        st["speed"] = 0
        if e.status in (401, 403):
            logger.warn("Access denied (%d) for %s — token required" % (e.status, st.get("repo") or st.get("name") or "unknown"))
        elif e.status == 404:
            logger.warn("File not found (404): %s" % (st.get("name") or "unknown"))
        elif e.status == -2:
            pass
        else:
            logger.error("HTTP error %d for %s" % (e.status, st.get("repo") or st.get("name") or "unknown"))
    except requests.exceptions.RequestException:
        st["status"] = "error"
        st["error"] = "network"
        st["speed"] = 0
        logger.error("Network error for %s" % (st.get("repo") or st.get("name") or "unknown"))
    except Exception:
        st["status"] = "error"
        st["error"] = "unknown"
        st["speed"] = 0
        logger.error("Unexpected error for %s" % (st.get("repo") or st.get("name") or "unknown"))
    finally:
        part = os.path.join(st["dir"], sanitize(st.get("name", "")) + ".part")
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        if st["kind"] == "repo" and st.get("current"):
            cur = st["current"]
            if isinstance(cur, str) and cur:
                rpart = os.path.join(st["dir"], *[sanitize(p) for p in cur.split("/")]) + ".part"
                if os.path.exists(rpart):
                    try:
                        os.remove(rpart)
                    except OSError:
                        pass
        _start_next_if_seq()
        with LOCK:
            if st["status"] in ("done", "error"):
                TASKS.pop(tid, None)
                st.pop("token", None)
                # На финише подравниваем прогресс: фронт считает проценты как
                # downloaded / total, и если total пришёл из заявленных размеров
                # файлов репо (а реально скачалось чуть меньше из-за редиректов /
                # Content-Encoding), полоска не дотянется до 100% при статусе
                # "done". Приравниваем к total при done, оставляем как есть при error.
                if st["status"] == "done":
                    if st.get("total"):
                        st["downloaded"] = st["total"]
                    else:
                        st["downloaded"] = st.get("downloaded", 0)
                    st["speed"] = 0
                # Переносим в историю, а не выбрасываем: фронтенд должен успеть
                # увидеть статус "done"/"error" при опросе и корректно открыть место.
                if len(HISTORY) > 500:
                    try:
                        HISTORY.pop(next(iter(HISTORY)))
                    except StopIteration:
                        pass
                HISTORY[tid] = st


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _cors(self):
        # CORS-заголовок отдаём ТОЛЬКО проверенным источникам (вместо "*").
        # Незнакомому Origin браузер не покажет ответ даже при простом GET.
        o = self.headers.get("Origin")
        if o and (o in ALLOWED_ORIGINS or (o == "null" and self._origin_ok())):
            self.send_header("Access-Control-Allow-Origin", o)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _origin_ok(self):
        """Разрешаем только локальному интерфейсу обращаться к ядру."""
        o = self.headers.get("Origin")
        if not o:  # curl / серверные вызовы
            return True
        if o in ALLOWED_ORIGINS:
            return True
        # pywebview/WebView2 может присылать Origin: null. Пропускаем ТОЛЬКО
        # нашу собственную страницу (проверка по Referer), чтобы file://-страница
        # из браузера (у неё Origin тоже null) не получила доступ к ядру.
        if o == "null":
            ref = self.headers.get("Referer") or ""
            return (ref.startswith("http://127.0.0.1:%d/" % _actual_web_port) or
                    ref.startswith("http://localhost:%d/" % _actual_web_port))
        return False

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # буфер обмена и задачи не должны кэшироваться браузером
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if not self._origin_ok():
            self._json({"error": "origin forbidden"}, 403)
            return
        if u.path == "/health":
            self._json({"ok": True, "core": "python", "base_dir": BASE_DIR})
            return
        if u.path == "/api/bookmarks":
            self._json({"bookmarks": load_bookmarks()})
            return
        if u.path == "/api/last_dir":
            self._json({"path": load_last_dir()})
            return
        if u.path == "/api/resolve_dir":
            # Юзер ввёл что-то в поле "Путь" — возвращаем реальный путь
            # на диске, куда пойдут файлы. Используется для подсказки
            # в UI, чтобы не было сюрпризов "скачалось не туда".
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, json.JSONDecodeError, OSError):
                self._json({"error": "bad body"}, 400)
                return
            p = body.get("path")
            if not isinstance(p, str):
                self._json({"error": "bad path"}, 400)
                return
            try:
                resolved = safe_subdir(p)
            except CoreError:
                self._json({"error": "bad path"}, 400)
                return
            self._json({
                "input": p,
                "resolved": resolved,
                "is_absolute": os.path.isabs(p.strip()),
                "exists": os.path.isdir(resolved),
            })
            return
        if u.path == "/api/dirs":
            try:
                base = safe_subdir(urllib.parse.unquote(u.query) or "")
            except CoreError:
                self._json({"error": "bad path"}, 400)
                return
            names = []
            if os.path.isdir(base):
                for name in sorted(os.listdir(base)):
                    if os.path.isdir(os.path.join(base, name)):
                        names.append(name)
            self._json({"dirs": names, "base_dir": BASE_DIR})
            return
        if u.path == "/api/clipboard":
            self._json({"ok": True, "text": clipboard_text()})
            return
        if u.path == "/api/logs":
            self._json({"logs": logger.all()})
            return
        if u.path == "/api/logs/clear":
            logger.clear()
            self._json({"ok": True})
            return
        # Установка предпочтительного языка (вызывается frontend при смене языка)
        if u.path == "/api/lang":
            global _server_locale
            lang = urllib.parse.unquote(u.query or "")
            # u.query — это строка "lang=ru"; выделяем значение параметра.
            if "=" in lang:
                lang = lang.split("=", 1)[1]
            if lang in SUPPORTED_LANGUAGES:
                _server_locale = get_locale(lang)
                self._json({"lang": lang})
                return
            self._json({"error": "unsupported language"}, 400)
            return
        if u.path == "/api/tasks":
            # Список всех задач — фронтенд подгружает его при старте, чтобы
            # показать восстановленные (незавершённые) задачи из .tasks.json.
            with LOCK:
                out = []
                for tid, st in TASKS.items():
                    out.append({
                        "id": tid,
                        "kind": st["kind"],
                        "name": st.get("name", ""),
                        "repo": st.get("repo", ""),
                        "dir": st.get("dir", ""),
                        "link": st.get("url", ""),
                        "status": st["status"],
                        "downloaded": st.get("downloaded", 0),
                        "total": st.get("total", 0),
                        "speed": st.get("speed", 0),
                        "files_done": st.get("files_done", 0),
                        "files_total": st.get("files_total", 0),
                        "current": st.get("current", ""),
                        "error": st.get("error"),
                        "branch": st.get("branch", "main"),
                        "speed_limit": st.get("speed_limit", 0),
                        "had_skip": bool(st.get("had_skip", False)),
                    })
            self._json({"tasks": out})
            return
        m = re.match(r"^/api/tasks/([\w-]+)$", u.path)
        if m:
            with LOCK:
                st = TASKS.get(m.group(1)) or HISTORY.get(m.group(1))
                if not st:
                    self._json({"error": "not found"}, 404)
                    return
                self._json({
                    "status": st["status"],
                    "downloaded": st["downloaded"],
                    "total": st["total"],
                    "speed": st["speed"],
                    "files_done": st["files_done"],
                    "files_total": st["files_total"],
                    "current": st["current"],
                    "error": st["error"],
                    "retries": st.get("retries", 0),
                    "max_retries": st.get("max_retries", 3),
                    "speed_limit": st.get("speed_limit", 0),
                })
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if not self._origin_ok():
            self._json({"error": "origin forbidden"}, 403)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            body = {}

        if u.path == "/api/lang":
            # Сохранение предпочтения языка. main.py при старте читает .lang.txt
            # и передаёт язык в URL (?lang=...) — выбор переживает перезапуски
            # даже при недоступном localStorage в WebView2.
            global _server_locale
            lang = str(body.get("lang") or "").lower().strip()
            if lang not in SUPPORTED_LANGUAGES:
                self._json({"error": "unsupported language"}, 400)
                return
            try:
                with open(LANG_FILE, "w", encoding="utf-8") as lf:
                    lf.write(lang)
            except OSError:
                self._json({"error": "write failed"}, 500)
                return
            _server_locale = get_locale(lang)
            self._json({"lang": lang})
            return

        if u.path == "/api/tasks":
            global _seq_mode
            link = str(body.get("link") or "")
            parsed = parse_link(link)
            if not parsed:
                self._json({"error": "bad link"}, 400)
                return
            try:
                dest = safe_subdir(body.get("dir"))
            except CoreError:
                self._json({"error": "bad dir"}, 400)
                return
            tid = "t%d-%d" % (int(time.time() * 1000000), next(_tid_seq))
            branch = str(body.get("branch") or parsed.get("branch", "main")).strip() or "main"
            st = {
                "kind": parsed["kind"],
                "url": parsed.get("url", ""),
                "name": parsed.get("name", ""),
                "repo": parsed.get("repo", ""),
                "rtype": parsed.get("rtype", "models"),
                "branch": branch,
                "dir": dest,
                "token": str(body.get("token") or ""),
                "status": "downloading",
                "downloaded": 0, "total": 0, "speed": 0,
                "base": 0, "base_total": 0,
                "files": [], "file_index": 0,
                "files_done": 0, "files_total": 0,
                "current": "",
                "error": None,
                "cancel": False,
                "run": threading.Event(),
                "retries": 0,
                "max_retries": 3,
                "retry_delay": 2,
                "speed_limit": 0,
            }
            sl = body.get("speed_limit")
            if isinstance(sl, int) and sl > 0:
                st["speed_limit"] = sl
            st["run"].set()

            # Режим «по очереди»: обновляем глобальный флаг и, если уже что-то
            # качается, ставим новую задачу в очередь (waiting). Завершившаяся
            # задача сама запустит следующую через _start_next_if_seq().
            _seq_mode = bool(body.get("seq"))
            if _seq_mode:
                with LOCK:
                    busy = any(s["status"] == "downloading" for s in TASKS.values())
                if busy:
                    st["status"] = "waiting"

            with LOCK:
                TASKS[tid] = st
            if st["status"] == "downloading":
                threading.Thread(target=run_task, args=(tid,), daemon=True).start()
            self._json({"id": tid, "kind": parsed["kind"], "status": st["status"], "dir": dest})
            return

        if u.path == "/api/bookmarks":
            items = body.get("bookmarks")
            if not isinstance(items, list):
                self._json({"error": "bad body"}, 400)
                return
            try:
                clean = save_bookmarks(items)
            except OSError:
                self._json({"error": "write failed"}, 500)
                return
            self._json({"bookmarks": clean})
            return

        if u.path == "/api/last_dir":
            path = str(body.get("path") or "").strip()
            if not path or not os.path.isdir(path):
                self._json({"error": "bad path"}, 400)
                return
            save_last_dir(path)
            self._json({"path": path})
            return

        if u.path == "/api/open":
            # Кнопка «показать в папке»: открыть скачанный файл/папку в проводнике.
            tid = str(body.get("id") or "")
            with LOCK:
                st = TASKS.get(tid) or HISTORY.get(tid)
            if st:
                if st["kind"] == "file" and st.get("name"):
                    # файл ещё качается — открываем саму папку загрузки
                    f = os.path.join(st["dir"], sanitize(st["name"]))
                    path = f if os.path.isfile(f) else st["dir"]
                else:
                    path = st["dir"]
            else:
                # fallback: фронтенд прислал dir/name/kind напрямую.
                # ВАЖНО: после завершения задачи её нет в TASKS, попадаем сюда.
                # Фронтенд хранит ОТНОСИТЕЛЬНЫЙ подпапок (напр. "models"),
                # поэтому резолвим его относительно BASE_DIR, а не рабочей
                # директории процесса (иначе откроется не то место).
                d = str(body.get("dir") or "").strip()
                nm = str(body.get("name") or "")
                if not d:
                    self._json({"error": "not found"}, 404)
                    return
                try:
                    d = safe_subdir(d)
                except CoreError:
                    self._json({"error": "bad path"}, 400)
                    return
                if str(body.get("kind") or "") == "file" and nm:
                    f = os.path.join(d, sanitize(nm))
                    path = f if os.path.isfile(f) else d
                else:
                    path = d
            if not open_location(path):
                self._json({"error": "not found"}, 404)
                return
            self._json({"ok": True})
            return

        if u.path == "/api/choose_dir":
            # Диалог выбора папки — используем Windows Shell (не tkinter!),
            # потому что tkinter нестабилен в фоновом потоке внутри pywebview.
            import subprocess

            L = _server_locale or init_locale()

            result = {"path": None, "absolute": None, "canceled": False, "error": None}

            # Открываем диалог в папке, указанной в поле «Путь» (если она есть),
            # а не в BASE_DIR по умолчанию.
            requested = str(body.get("dir") or "").strip()
            initial = resolve_choose_initial_dir(requested)

            if os.name == 'nt':
                # Windows: используем PowerShell диалог — работает стабильно в любом потоке
                try:
                    ps_code = r'''
Add-Type -AssemblyName Microsoft.VisualBasic
$folder = [Microsoft.VisualBasic.FileIO.DirectorySelectDialog]::new()
$folder.Title = '{title}'
$folder.InitialDirectory = '{dir}'
if ($folder.ShowDialog()) {{
    Write-Output $folder.FolderName
}}
                    '''.replace("{title}", L.t("dir_title").replace("'", "''")).replace("{dir}", initial.replace("'", "''"))
                    out = subprocess.check_output(
                        ['powershell', '-NoProfile', '-Command', ps_code],
                        stderr=subprocess.STDOUT, timeout=120  # 2 минуты — пользователь выбирает
                    ).decode('utf-8').strip()
                    if out:
                        ap = os.path.abspath(out)
                        # На разных дисках Windows relpath бросает ValueError — отдаём абсолютный
                        try:
                            rel = os.path.relpath(ap, BASE_DIR).replace("\\", "/")
                        except ValueError:
                            rel = ap
                        result["path"] = "." if rel == "." else rel
                        result["absolute"] = ap
                except subprocess.TimeoutExpired:
                    result["canceled"] = True  # диалог закрыт/завис
                except Exception as e2:
                    result["error"] = "PowerShell dialog failed: " + str(e2)[:100]
            else:
                # macOS/Linux: через shell — osascript (macOS) или xdg-open (Linux)
                try:
                    if sys.platform == 'darwin':
                        # macOS: osascript диалог
                        cmd = [
                            'osascript', '-e',
                            'tell application "Finder" to choose folder with prompt "' + L.t("dir_title") + '"'
                        ]
                        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=15)
                        path = out.decode('utf-8').strip()
                        ap = os.path.abspath(path)
                        try:
                            rel = os.path.relpath(ap, BASE_DIR).replace("\\", "/")
                        except ValueError:
                            rel = ap
                        result["path"] = "." if rel == "." else rel
                        result["absolute"] = ap
                    else:
                        # Linux: xdg-open не поддерживает диалоги — показываем подсказку
                        result["error"] = "Please enter path manually on Linux"
                except Exception as e:
                    result["error"] = str(e)[:100]

            if not result.get("path") and not result.get("absolute"):
                # Пользователь нажал Cancel или ничего не выбрано
                result["canceled"] = True

            self._json(result)
            return

        m = re.match(r"^/api/tasks/([\w-]+)/(pause|resume|cancel)$", u.path)
        if m:
            with LOCK:
                st = TASKS.get(m.group(1))
            if not st:
                self._json({"error": "not found"}, 404)
                return
            act = m.group(2)
            if act == "pause":
                st["run"].clear()
                st["speed"] = 0
            elif act == "resume":
                st["run"].set()
            else:
                st["cancel"] = True
                st["run"].set()
            self._json({"ok": True})
            return

        self._json({"error": "not found"}, 404)


def start_in_thread():
    """Запуск ядра в фоновом потоке (использует main.py / pywebview)."""
    global _server_instance, _server_locale, _actual_port
    
    # Инициализируем локализацию: сначала сохранённый выбор пользователя
    # (.lang.txt, пишется при смене языка в UI), затем автоопределение ОС.
    saved_lang = _read_saved_lang()
    _server_locale = init_locale(saved_lang) if saved_lang else init_locale()
    
    os.makedirs(BASE_DIR, exist_ok=True)
    
    # Восстанавливаем сохранённые задачи при старте и запускаем для них
    # рабочие потоки, чтобы недокачанные загрузки продолжились.
    saved = load_tasks_state()
    if saved:
        print("  " + _server_locale.t("restore_tasks", len(saved)))
        with LOCK:
            TASKS.update(saved)
        for tid in saved:
            threading.Thread(target=run_task, args=(tid,), daemon=True).start()
    
    sock, _actual_port = find_free_port(HOST, PORT)
    # Передаём уже привязанный сокет, чтобы не терять зарезервированный порт
    # (иначе между find_free_port и bind-ом сервера порт мог бы перехватить другой процесс).
    srv = ThreadingHTTPServer((HOST, 0), Handler, bind_and_activate=False)
    srv.socket = sock
    srv.server_address = sock.getsockname()
    srv.server_name = socket.getfqdn(srv.server_address[0])
    srv.server_port = srv.server_address[1]
    srv.server_activate()
    _server_instance = srv
    
    # Signal handlers registered in main.py for unified shutdown.
    # Here we only expose the API — do NOT register signals again.
    
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def main():
    global _server_instance
    
    start_in_thread()
    
    L = _server_locale or init_locale()
    print("=" * 56)
    print(" " + L.t("core_start"))
    print("   " + L.t("core_addr") + " http://%s:%d" % (HOST, _actual_port))
    print("   " + L.t("core_dir") + " %s" % BASE_DIR)
    print("   " + L.t("core_stop"))
    print("=" * 56)
    
    # Регистрируем обработчик сигнала для standalone запуска
    try:
        signal.signal(signal.SIGINT, _shutdown_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _shutdown_handler)
    except (OSError, ValueError):
        pass
    
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        # Дублируем shutdown на случай если signal handler не сработал
        print("\n\n" + L.t("signal_shutdown"))
        
        with LOCK:
            for tid, st in TASKS.items():
                if st["status"] in ("downloading", "paused"):
                    st["cancel"] = True
                    st["run"].set()
        
        save_tasks_state()
        
        if _server_instance:
            _server_instance.shutdown()
        print(L.t("stopped"))


if __name__ == "__main__":
    main()
