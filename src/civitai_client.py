# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
CivitAI client — получение прямых ссылок для скачивания моделей.

CivitAI разделился на два домена:
  - civitai.com  (Blue) — основной сайт, SFW-контент
  - civitai.red (Red)  — отдельный домен для NSFW-контента

API v1: https://civitai.com/api/v1/models/{modelId}
        https://civitai.com/api/v1/model-versions/{versionId}

Токен обязателен — без него API не отдаёт прямую ссылку.
"""

import re
import urllib.parse

import requests

from logger import logger

# ---------------------------------------------------------------------------
# Регулярки для парсинга ссылок CivitAI
# ---------------------------------------------------------------------------

CIVITAI_MODEL_RE = re.compile(
    r"^https?://(?:www\.)?civitai\.(?:com|red)/models/(\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)

CIVITAI_DIRECT_RE = re.compile(
    r"^https?://(?:www\.)?civitai\.(?:com|red)/api/download/models/(\d+)(?:[/?#]|$)",
    re.IGNORECASE,
)

# URN-формат: urn:air:zimageturbo:diffusionmodel:civitai:620406@3161628+3042004
# Извлекает model_id, version_id, file_id
CIVITAI_URN_RE = re.compile(
    r"^urn:.*:civitai:(\d+)(?:@(\d+))?(?:\+(\d+))?$",
    re.IGNORECASE,
)


class CivitAIError(Exception):
    """Ошибка CivitAI API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def detect_civitai_source(url: str) -> str | None:
    """Определить источник CivitAI по домену.

    Возвращает "civitai_blue", "civitai_red" или None.
    """
    u = url.strip().lower()
    if "civitai.red" in u:
        return "civitai_red"
    if "civitai.com" in u:
        return "civitai_blue"
    return None


def parse_civitai_link(url: str) -> dict | None:
    """Извлечь ID модели/версии/файла из URL или URN CivitAI.

    Поддерживает:
      - https://civitai.com/models/{id}?modelVersionId={vid}
      - https://civitai.com/api/download/models/{id}
      - urn:...:civitai:{modelId}@{versionId}+{fileId}

    Возвращает dict с полями model_id, version_id, file_id, source, name
    или None если URL/URN не распознан.
    """
    url = url.strip()

    # Пробуем URN-формат
    if url.lower().startswith("urn:"):
        m = CIVITAI_URN_RE.match(url)
        if m:
            model_id = m.group(1)
            version_id = m.group(2)
            file_id = m.group(3) or m.group(2)
            return {
                "model_id": model_id,
                "version_id": version_id,
                "file_id": file_id,
                "source": "civitai_blue",  # URN по умолчанию Blue
                "name": f"civitai_model_{model_id}" + (f"_v{version_id}" if version_id else ""),
            }
        return None

    source = detect_civitai_source(url)
    if source is None:
        return None

    # Прямая ссылка /api/download/models/{id}
    m = CIVITAI_DIRECT_RE.match(url)
    if m:
        return {
            "model_id": None,
            "version_id": m.group(1),
            "file_id": m.group(1),
            "source": source,
            "name": f"civitai_model_{m.group(1)}",
        }

    # /models/{id}?modelVersionId={vid}[&fileId=..][&type=..&format=..&size=..&fp=..]
    m = CIVITAI_MODEL_RE.match(url)
    if m:
        model_id = m.group(1)
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        version_id = qs.get("modelVersionId", [None])[0] or qs.get("version", [None])[0]
        file_id = qs.get("fileId", [None])[0]
        return {
            "model_id": model_id,
            "version_id": version_id,
            "file_id": file_id or version_id,
            # Не теряем уточнения варианта из кнопки Copy Link
            # (type/format/size/fp): по ним resolve выберет точный файл.
            "variant": {k: (qs.get(k) or [None])[0]
                        for k in ("type", "format", "size", "fp")},
            "source": source,
            "name": f"civitai_model_{model_id}",
        }

    return None


def _api_base(source: str) -> str:
    """Базовый URL API для данного источника."""
    if source == "civitai_red":
        return "https://civitai.red/api/v1"
    return "https://civitai.com/api/v1"


def _clean_token(token):
    """Убрать пробелы/переносы/кавычки и невидимые символы из токена."""
    t = str(token or "")
    t = t.strip().strip("'\"")
    t = re.sub(r"\s+", "", t)
    t = t.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "")
    t = t.replace("\u200d", "").replace("\u00ad", "")
    return t


def get_civitai_file_info(
    model_id: str | None = None,
    version_id: str | None = None,
    file_id: str | None = None,
    token: str = "",
    source: str = "civitai_blue",
    variant: dict | None = None,
) -> dict:
    """Получить информацию о файле CivitAI через API.

    Приоритет: version_id → model_id (последняя версия с файлом Model).

    Возвращает dict с полями name, downloadUrl, sizeKB, format и др.
    Кидает CivitAIError при ошибках.
    """
    base = _api_base(source)
    # Токен мог прийти с переносами строк/кавычками/невидимыми символами после
    # копипаста — requests кинет InvalidHeader (подкласс RequestException) на
    # такой Bearer-заголовок, и задача мгновенно упадёт с «Network error».
    token = _clean_token(token)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def _with_token(u: str) -> str:
        """Добавить токен как query-параметр (CivitAI принимает и Bearer, и ?token=,
        но Bearer не переживает редирект на CDN — поэтому дублируем в URL)."""
        if not token or not u:
            return u
        sep = "&" if "?" in u else "?"
        return f"{u}{sep}token={urllib.parse.quote(token)}"

    version_data = None

    # Пробуем получить конкретную версию
    if version_id:
        url = _with_token(f"{base}/model-versions/{version_id}")
        logger.info(f"CivitAI: fetching version info from {base}/model-versions/{version_id}")
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            version_data = resp.json()
        elif resp.status_code == 401:
            raise CivitAIError(
                "civitai_token_invalid",
                "CivitAI rejected the token (401). Check your API key.",
            )
        elif resp.status_code == 403:
            raise CivitAIError(
                "civitai_forbidden",
                "CivitAI access denied (403). The model may be gated.",
            )
        elif resp.status_code == 404:
            raise CivitAIError(
                "civitai_not_found",
                f"CivitAI model version not found (404): {version_id}",
            )
        else:
            raise CivitAIError(
                "civitai_api_error",
                f"CivitAI API error: HTTP {resp.status_code}",
            )

    # Если версия не найдена — пробуем через model_id
    if version_data is None and model_id:
        url = _with_token(f"{base}/models/{model_id}")
        logger.info(f"CivitAI: fetching model info from {base}/models/{model_id}")
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            model_data = resp.json()
            versions = model_data.get("modelVersions", [])
            for v in versions:
                for f in v.get("files", []):
                    if f.get("type") == "Model":
                        version_data = v
                        break
                if version_data:
                    break
            if version_data is None and versions:
                for v in versions:
                    if v.get("files"):
                        version_data = v
                        break
        elif resp.status_code == 401:
            raise CivitAIError("civitai_token_invalid",
                               "CivitAI rejected the token (401).")
        elif resp.status_code == 403:
            raise CivitAIError("civitai_forbidden",
                               "CivitAI access denied (403).")
        elif resp.status_code == 404:
            raise CivitAIError("civitai_not_found",
                               f"CivitAI model not found (404): {model_id}")
        else:
            raise CivitAIError("civitai_api_error",
                               f"CivitAI API error: HTTP {resp.status_code}")

    if version_data is None:
        raise CivitAIError("civitai_not_found",
                           "Could not find model version on CivitAI.")

    # Извлекаем файл
    files = version_data.get("files", [])
    target_file = None

    if target_file is None:
        # file_id из ссылки равен version_id (обычная /models/ ссылка без
        # ?fileId=): это НЕ id файла — игнорируем и выбираем по variant/meta.
        # Иначе брался бы первый Model-файл наугад, а fileId в download-URL
        # указывал на несуществующий файл.
        file_id_is_version = str(file_id or "") == str(
            version_data.get("id") or "")
        if file_id and not file_id_is_version:
            for f in files:
                if str(f.get("id")) == str(file_id):
                    target_file = f
                    break
        if target_file is None and variant:
            want = {k: str(v).lower() for k, v in (variant or {}).items() if v}
            if want:
                scored = []
                for f in files:
                    if f.get("type") != "Model":
                        continue
                    meta = f.get("metadata") or {}
                    score = 0
                    for k in ("format", "fp", "size"):
                        w = want.get(k)
                        if w and str(meta.get(k) or "").lower() == w:
                            score += 1
                    # type (Checkpoint/LoRA/...) лежит в самом файле
                    wt = want.get("type")
                    if wt and str(f.get("modelType") or "").lower() == wt:
                        score += 1
                    scored.append((score, f))
                if scored:
                    scored.sort(key=lambda s: s[0], reverse=True)
                    if scored[0][0] > 0:
                        target_file = scored[0][1]
    if target_file is None:
        for f in files:
            if f.get("type") == "Model":
                target_file = f
                break
        if target_file is None and files:
            target_file = files[0]

    if target_file is None:
        raise CivitAIError("civitai_no_files",
                           "No downloadable files found in this model version.")

    download_url = target_file.get("downloadUrl", "")
    if not download_url:
        download_url = version_data.get("downloadUrl", "")

    # model.type («Checkpoint», «LORA», «VAE», «TextualInversion», …) и
    # baseModel («SD 1.5», «SDXL 1.0», «Flux.1 D») нужны, чтобы построить
    # читаемый префикс имени файла и разложить файл по папкам. API отдаёт их
    # в том же ответе, который мы уже получили, — дополнительных запросов нет.
    model_info = version_data.get("model") or {}

    return {
        "name": target_file.get("name", f"civitai_{version_data.get('id', 'unknown')}.safetensors"),
        "downloadUrl": download_url,
        "sizeKB": target_file.get("sizeKB", 0),
        "format": target_file.get("metadata", {}).get("format", ""),
        "fp": target_file.get("metadata", {}).get("fp", ""),
        "size": target_file.get("metadata", {}).get("size", ""),
        # Настоящее имя МОДЕЛИ (DreamShaper), а не версии ("8"). Раньше здесь
        # лежало имя версии — оно и остаётся, но теперь в version_name.
        "model_name": model_info.get("name", "") or version_data.get("name", ""),
        "model_type": model_info.get("type", ""),
        "base_model": version_data.get("baseModel", ""),
        "trained_words": version_data.get("trainedWords") or [],
        "version_name": version_data.get("name", ""),
        # Реальный ID выбранного файла — нужен чтобы fileId в download-URL
        # указывал на него, а не на version_id (см. get_civitai_download_url).
        "_fileId": target_file.get("id"),
    }


def get_civitai_download_url(
    model_id: str | None = None,
    version_id: str | None = None,
    file_id: str | None = None,
    token: str = "",
    source: str = "civitai_blue",
    variant: dict | None = None,
) -> tuple[str, str, int, dict]:
    """Получить прямую ссылку для скачивания с CivitAI.

    Возвращает (filename, url, size_bytes, info), где info — полный ответ
    get_civitai_file_info (имя модели, тип, база, fp): из него ядро строит
    читаемый префикс имени файла и определяет папку. Запрос к API один и тот
    же, поэтому отдаём info наружу, а не ходим в API второй раз.
    Кидает CivitAIError при ошибках.
    """
    token = _clean_token(token)
    info = get_civitai_file_info(model_id, version_id, file_id, token, source,
                                 variant=variant)

    download_url = info.get("downloadUrl", "")

    # CivitAI иногда отдаёт downloadUrl в формате URN (urn:air:<stack>:...),
    # а не http-ссылку — requests падает с InvalidSchema. В этом случае
    # строим стандартный download-endpoint сами.
    if download_url and not download_url.startswith(("http://", "https://")):
        download_url = ""

    if not download_url:
        base = _api_base(source)
        vid = version_id or file_id
        if vid:
            download_url = f"{base}/download/models/{vid}"
            if token:
                download_url += f"?token={urllib.parse.quote(token)}"

    if not download_url:
        raise CivitAIError(
            "civitai_no_url",
            "CivitAI did not return a download URL. The model may require a valid token.",
        )

    # ВАЖНО: downloadUrl из API приходит БЕЗ токена. Если качать по нему с
    # Bearer-заголовком — редирект на CDN теряет авторизацию и CivitAI отдаёт
    # 401. Токен обязан быть в самом URL как query-параметр.
    if token and "token=" not in urllib.parse.urlparse(download_url).query:
        sep = "&" if "?" in download_url else "?"
        download_url = f"{download_url}{sep}token={urllib.parse.quote(token)}"

    # fileId обязан указывать на РЕАЛЬНЫЙ файл, а не на version_id:
    # /download/models/{versionId} без fileId отдаёт primary-файл версии,
    # а resolve выше мог выбрать другой (Model-первый). Если в URL нет
    # fileId или он равен version_id, а выбранный файл другой — чиним.
    try:
        real_file_id = str(info.get("_fileId") or "")
        if real_file_id:
            parts = urllib.parse.urlparse(download_url)
            q = urllib.parse.parse_qs(parts.query)
            cur_fid = (q.get("fileId") or [""])[0]
            if cur_fid != real_file_id:
                q["fileId"] = [real_file_id]
                download_url = urllib.parse.urlunparse(
                    parts._replace(query=urllib.parse.urlencode(q, doseq=True))
                )
    except Exception:
        pass

    filename = info.get("name", "civitai_model.safetensors")
    size_bytes = int(info.get("sizeKB", 0)) * 1024

    return filename, download_url, size_bytes, info
