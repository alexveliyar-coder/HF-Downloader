# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.

import http.server
import os
import signal
import socket
import sys
import threading
import urllib.parse
import webbrowser
from functools import partial
from pathlib import Path

# Add bundled src/ to sys.path so we can import the project modules
# without requiring the user to install anything (no `pip install -e .`).
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Localization — auto-detect OS language
from locale_loader import get_locale, init_locale

# Update checker (только консольное уведомление, без скачивания).
# Прямой импорт: updater.py лежит в src/ и добавлен в sys.path выше.
import updater
_HAS_UPDATER = True

BASE = Path(__file__).parent
SITE = BASE / "site"
WEB_PORT = 8777

# Глобальные ссылки на серверы для graceful shutdown
_site_server = None
_core_server_ref = None

try:
    import hf_core_server  # ядро скачивания
# Ядро требует requests; если зависимости не установлены (например, нет
# интернета при первом запуске), даём понятное сообщение вместо краша.
except ImportError as _imp_err:
    import sys
    sys.stderr.write(
        "\n[HF Downloader] Не найдены зависимости (requests).\n"
        "Установите их командой:  python -m pip install -r requirements.txt\n"
        "Текст ошибки: %s\n" % _imp_err
    )
    raise SystemExit(1)


def _graceful_shutdown():
    """Корректная остановка всех компонентов."""
    global _site_server, _core_server_ref
    L = init_locale()  # получаем локализацию (уже инициализирована в main())
    
    print("\n\n" + L.t("shutdown_title"))
    
    # Устанавливаем cancel для всех активных задач в core-сервере
    with hf_core_server.LOCK:
        for tid, st in hf_core_server.TASKS.items():
            if isinstance(st.get("run"), threading.Event) and st["status"] in ("downloading", "paused"):
                st["cancel"] = True
                st["run"].set()
    
    # Сохраняем состояние задач
    try:
        hf_core_server.save_tasks_state()
        print("  " + L.t("shutdown_saved"))
    except Exception:
        import sys; sys.stderr.write("  [warn] shutdown: save_tasks_state failed\n")
    
    # Корректно останавливаем core-сервер (не вызывает KeyboardInterrupt)
    if _core_server_ref:
        try:
            _core_server_ref.shutdown()
            print("  " + L.t("shutdown_core"))
        except Exception:
            import sys; sys.stderr.write("  [warn] shutdown: core server failed\n")
    
    # Останавливаем сайт-сервер корректно
    if _site_server:
        try:
            _site_server.shutdown()
            print("  " + L.t("shutdown_site"))
        except Exception:
            import sys; sys.stderr.write("  [warn] shutdown: site server failed\n")
    
    print(L.t("shutdown_done"))


def _saved_lang():
    """User-selected language (the core writes it to .lang.txt).

    If the file doesn't exist or the language isn't supported — None (use auto-detect).
    """
    try:
        with open(hf_core_server.LANG_FILE, "r", encoding="utf-8") as fh:
            code = fh.read().strip().lower()
        if code in hf_core_server.SUPPORTED_LANGUAGES:
            return code
    except OSError:
        pass
    return None


def _find_free_port(host, start_port, max_tries=20):
    """Найти свободный порт, держа привязанный сокет открытым (исключает
    гонку TOCTOU). Возвращает (socket, port); сокет передаётся в сервер."""
    import socket
    for p in range(start_port, start_port + max_tries):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, p))
            return s, p
        except OSError:
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
            continue
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, start_port))
    return s, start_port


class _SiteHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._serve_index()
        else:
            super().do_GET()

    def _serve_index(self):
        try:
            with open(SITE / "index.html", "r", encoding="utf-8") as f:
                content = f.read()
            port = getattr(hf_core_server, '_actual_port', hf_core_server.PORT)
            content = content.replace("%CORE_PORT%", str(port))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(content.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        except Exception:
            self.send_error(500)


def serve_site():
    global _site_server
    sock, port = _find_free_port("127.0.0.1", WEB_PORT)
    # Hold the reserved socket so nothing else grabs the port before the server starts.
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SiteHandler, bind_and_activate=False)
    srv.socket = sock
    srv.server_address = sock.getsockname()
    srv.server_name = socket.getfqdn(str(srv.server_address[0]))
    srv.server_port = srv.server_address[1]
    srv.server_activate()
    _site_server = srv

    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def _dir_result(absolute, base):
    """JSON response with the selected folder path.

    Inside `base` — relative path (with / separators), otherwise absolute
    (e.g., another Windows drive). The core understands both variants.
    """
    import json
    ap = os.path.abspath(absolute)
    try:
        rel = os.path.relpath(ap, base).replace("\\", "/")
    except ValueError:
        rel = ap
    return json.dumps({"path": "." if rel == "." else rel, "absolute": ap})


def _resolve_initial_dir(current_dir):
    """Initial folder for the dialog: whatever was specified in the 'Path' field.

    We check if it's an absolute path or a subfolder of BASE_DIR; if such a folder
    exists — we open it, otherwise we look for the nearest existing parent
    (or BASE_DIR itself).
    """
    base = hf_core_server.BASE_DIR
    cur = (current_dir or "").strip().strip('"').strip("'")
    if not cur:
        return base
    if os.path.isabs(cur):
        cand = os.path.abspath(cur)
    else:
        cand = os.path.abspath(os.path.join(base, cur))
    if os.path.isdir(cand):
        return cand
    parent = os.path.dirname(cand)
    if parent and os.path.isdir(parent):
        return parent
    return base


class Api:
    """JS API для pywebview — вызывается из site/index.html.

    В JS доступен как window.pywebview.api (методы объекта).
    """

    def _folder_dialog_native(self, base):
        """Нативный диалог pywebview — открывается ПОВЕРХ окна приложения.

        Методы js_api выполняются в рабочем потоке pywebview, и создание
        tkinter.Tk() оттуда не работает (tkinter требует главный поток GUI) —
        поэтому здесь используется штатный webview.create_file_dialog,
        который сам открывает диалог поверх окна.
        """
        import json
        try:
            import webview
            if not webview.windows:
                return None
            win = webview.windows[0]
            result = win.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=str(base),
                allow_multiple=False,
            )
            if result:
                path = result if isinstance(result, str) else result[0]
                return path
            return json.dumps({"canceled": True})
        except Exception:
            return None

    def choose_dir(self, current_dir=None):
        """Открыть системный диалог выбора папки (проводник Windows).

        current_dir — текущее значение поля «Путь»; диалог открывается именно
        в этой папке (если она существует), а не в BASE_DIR по умолчанию.
        Возвращает JSON-строку: {"path": ..., "absolute": ..., "canceled": bool}.
        """
        import json

        L = hf_core_server._server_locale or init_locale()
        root = hf_core_server.BASE_DIR
        initial = _resolve_initial_dir(current_dir)

        # 1) Нативный диалог pywebview (главный путь): открывается поверх окна,
        #    не зависит от потоков tkinter и работает в WebView2 без проблем.
        native = self._folder_dialog_native(initial)
        if native is not None:
            if isinstance(native, str) and native.startswith("{"):
                return native  # {"canceled": True}
            return _dir_result(native, root)

        # 2) Fallback: tkinter (для запуска без pywebview — обычный браузер)
        try:
            import tkinter as tk
            from tkinter import filedialog
            root_tk = None
            try:
                root_tk = tk.Tk()
                root_tk.withdraw()
                chosen = filedialog.askdirectory(parent=root_tk, initialdir=initial, title=L.t("dir_title"))
            except Exception:
                chosen = ""
            finally:
                if root_tk is not None:
                    try:
                        root_tk.destroy()
                    except Exception:
                        pass
            if chosen:
                return _dir_result(chosen, root)
        except Exception:
            pass

        # 3) Fallback: PowerShell (Windows) если tkinter недоступен
        if os.name == "nt":
            try:
                import subprocess
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
                    ["powershell", "-NoProfile", "-Command", ps_code],
                    stderr=subprocess.STDOUT, timeout=120
                ).decode("utf-8").strip()
                if out:
                    return _dir_result(out, root)
            except Exception:
                pass

        return json.dumps({"canceled": True})


def main():
    global _core_server_ref
    
    # Initialize localization: first use saved user preference
    # (.lang.txt, written when changing language in UI), then auto-detect OS.
    saved_lang = _saved_lang()
    L = init_locale(saved_lang) if saved_lang else init_locale()
    
    # Регистрируем обработчик сигнала ОДИН РАЗ в главном потоке
    try:
        signal.signal(signal.SIGINT, lambda signum, frame: (_graceful_shutdown(), None)[1])
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda signum, frame: (_graceful_shutdown(), None)[1])
    except (OSError, ValueError):
        pass
    
    _core_server_ref = hf_core_server.start_in_thread()
    site_srv = serve_site()
    actual_web_port = site_srv.server_address[1]
    # Сайт может слушать не 8777 (если порт занят) — сообщаем ядру фактический
    # порт, иначе CORS/Origin не совпадут и все запросы фронтенда получат 403.
    hf_core_server.set_web_port(actual_web_port)
    
    # Передаём язык в frontend через URL-параметр.
    # cache-buster (`&v=VERSION`) — чтобы при обновлении версии pywebview/браузер
    # не показывал старую страницу из кэша.
    url = "http://127.0.0.1:%d/?lang=%s&v=%s" % (actual_web_port, L.lang, updater.VERSION)
    
    print("=" * 58)
    print(" " + L.t("console_start") + " v" + (updater.VERSION if _HAS_UPDATER else "?"))
    print("   " + L.t("console_site") + " " + url)
    print("   " + L.t("console_core") + " http://127.0.0.1:%d" % hf_core_server._actual_port)
    print("   " + L.t("console_files") + "    " + hf_core_server.BASE_DIR)
    print("   " + L.t("console_exit"))
    print("=" * 58)

    # Проверка обновлений (best-effort, не блокирует запуск).
    if _HAS_UPDATER:
        try:
            info = updater.check_update()
            if info:
                print(updater.format_update_message(info))
        except Exception:
            pass
    
    try:
        import webview  # pywebview

        webview.create_window(
            L.t("app_name"),
            url,
            width=1280,
            height=860,
            min_size=(980, 640),
            background_color="#14110C",
            js_api=Api(),
        )
        webview.start()
    except ImportError:
        print(" " + L.t("no_pywebview"))
        print(" (" + L.t("install_pywebview") + ")")
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            _graceful_shutdown()
    except KeyboardInterrupt:
        # pywebview может прокинуть KeyboardInterrupt
        _graceful_shutdown()


if __name__ == "__main__":
    main()
