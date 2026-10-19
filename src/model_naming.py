# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
model_naming.py — читаемые имена файлов и раскладка моделей по папкам.

Зачем: на HF и CivitAI файлы моделей часто называются безлико
(`diffusion_pytorch_model.safetensors`, `model.safetensors`, `v1-5-pruned.ckpt`),
и по имени на диске невозможно понять, что это за модель и для чего она.
Здесь мы строим префикс ИЗ МЕТАДАННЫХ источника (имя модели/версии, база,
тип, точность) и определяем подпапку по типу модели — в конвенции ComfyUI
(`models/loras`, `models/vae`, `models/text_encoders`, …).

Модуль намеренно БЕЗ сети и без побочных эффектов: всё, что нужно, приходит
в dict метаданных. Поэтому логику имён можно проверить тестами
(`tests/test_smoke.py`), не поднимая сервер и не ходя в интернет.
"""

import os
import re

# ---------------------------------------------------------------------------
# Подпапки по типам модели (конвенция ComfyUI, она же используется в A1111
# как models/<тип>). "other" — всё, что уверенно опознать не удалось: лучше
# предсказуемая свалка, чем модель в случайной папке.
# ---------------------------------------------------------------------------
TYPE_DIRS = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "lycoris": "loras",          # LyCORIS/LoCon/AestheticGradient грузятся как LoRA
    "vae": "vae",
    "encoder": "text_encoders",
    "controlnet": "controlnet",
    "embedding": "embeddings",
    "upscale": "upscale_models",
    "hypernetwork": "hypernetworks",
    "poses": "poses",
    "diffusers": "diffusers",
    "diffusion": "diffusion_models",   # ComfyUI models/diffusion_models (flux/wan/trellis…)
    "clip_vision": "clip_vision",      # ComfyUI models/clip_vision
    "other": "other",
}

FALLBACK_TYPE = "other"

# ---------------------------------------------------------------------------
# Типы CivitAI API ("model": {"type": ...}) -> наши каноничные токены.
# Ключ — значение после удаления всего кроме букв/цифр, в нижнем регистре.
# ---------------------------------------------------------------------------
CIVITAI_TYPES = {
    "checkpoint": "checkpoint",
    "lora": "lora",
    "locon": "lycoris",
    "dora": "lora",
    "aestheticgradient": "lycoris",
    "textualinversion": "embedding",
    "hypernetwork": "hypernetwork",
    "controlnet": "controlnet",
    "poses": "poses",
    "vae": "vae",
    "upscaler": "upscale",
    "upscalers": "upscale",
    "motionmodule": "other",
    "wildcards": "other",
    "workflows": "other",
    "other": "other",
}

# Расширения весов модели: по ним решаем, можно ли считать неопознанный файл
# чекпойнтом (для .json/.txt/README это было бы неверно).
WEIGHT_EXTS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx")

# Нормализация baseModel в короткий токен префикса. Порядок правил важен:
# частные случаи (flux1d, sd35) обязаны идти раньше общих (flux, sd).
_BASE_RULES = (
    ("flux1d", r"^(?:flux1d|fluxd|fluxdev|flux1dev|dev)"),
    ("flux1s", r"^(?:flux1s|fluxs|fluxschnell|schnell)"),
    ("flux", r"^flux"),
    ("sd35", r"^(?:sd35|sd3_?5)"),
    ("sd3", r"^sd3"),
    ("sdxl", r"^(?:sdxl|sd_xl|sd10|xl)"),
    ("sd21", r"^(?:sd21|sd2_?1)"),
    ("sd15", r"^(?:sd15|sd1_?5|sd1)"),
    ("pony", r"^pony"),
    ("illustrious", r"^illustrious"),
    ("noob", r"^(?:noob|noobaivpred)"),
    ("hunyuan", r"^hunyuan"),
    ("wan", r"^(?:wan|wanvideo)"),
    ("qwen", r"^qwen"),
    ("sd", r"^sd"),
)

# «Пустые» значения baseModel: в префикс их тащить незачем.
_BASE_EMPTY = ("", "other", "unknown", "none", "n/a", "na", "standard")

# Правила определения типа по имени файла/репозитория. Порядок важен:
# "text_encoder" обязан проверяться до общего "model", а lora — до всего
# остального (в имени лоры часто есть и база, и слово "sdxl").
_NAME_RULES = (
    ("lora", r"lora|lycoris|loha|locon|\bdora\b|_lokr"),
    ("vae", r"\bvae\b|_vae|vae_|kl-f8|kl_f8|autoencoder"),
    ("controlnet", r"controlnet|control_net"),
    ("encoder", r"text_encoder|textencoder|clip_l|clip_g|\bclip\b|t5xxl|t5_xxl|t5encoder|umt5"),
    ("embedding", r"embedding|textual_inversion|textualinversion"),
    ("upscale", r"upscale|esrgan|swinir|_4x|4x_"),
    ("hypernetwork", r"hypernetwork"),
    # Чекпойнт по имени: явные токены SD-семейства либо слово "checkpoint".
    ("checkpoint", r"checkpoint|\bsd_?xl\b|sd_?1[._]?5|sdxl|sd15|sd21|sd_"),
)

# Символы, недопустимые в имени файла (Windows) и просто мусорные в префиксе.
_BAD_CHARS = re.compile(r"[\\/:*?\"<>|#%&{}$!'@+=`~^\[\]()]+")

_TOKEN_MAX = 40     # один токен префикса не длиннее 40 символов
_NAME_MAX = 180     # общий лимит имени файла (совпадает с sanitize())


def normalize_token(value, max_len=_TOKEN_MAX):
    """Привести часть префикса к безопасному виду без пробелов.

    Пробелы ВЫРЕЗАЕМ, а не заменяем на "_": префикс вида "Detail Tweaker XL"
    превратился бы в "Detail_Tweaker_XL", и имя файла становится нечитаемым.
    "DetailTweakerXL" читается лучше и короче.

    max_len ограничивает ОДИН токен (например имя модели), а не весь префикс
    целиком — в apply_prefix лимит другой (там режет общий лимит имени файла).
    """
    s = _BAD_CHARS.sub("-", str(value or "").strip())
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-._")
    return s[:max_len]


def normalize_base(base):
    """baseModel ("SD 1.5", "Flux.1 D", "Pony") -> токен ("sd15", "flux1d", "pony")."""
    compact = re.sub(r"[^0-9a-z]+", "", str(base or "").lower())
    if compact in _BASE_EMPTY:
        return ""
    for canon, pattern in _BASE_RULES:
        if re.match(pattern, compact):
            return canon
    # Незнакомая база — оставляем как есть (обрезка уже внутри _TOKEN_MAX).
    return compact[:24]


def is_weight_file(name):
    """Похоже ли имя на файл весов модели (а не на конфиг/README)."""
    return str(name or "").lower().endswith(WEIGHT_EXTS)


def classify_by_name(*names):
    """Определить тип модели по именам (файла, репозитория, ссылки).

    Возвращает каноничный токен типа или "" — если ничего уверенного нет.
    """
    hay = " ".join(str(n or "").lower() for n in names if n)
    if not hay:
        return ""
    for token, pattern in _NAME_RULES:
        if re.search(pattern, hay):
            return token
    return ""


# ---------------------------------------------------------------------------
# Папки репозитория (конвенция ComfyUI): первая компонента пути файла в репо
# прямо называет назначение весов. Самый точный признак для отдельного файла:
# "clip_vision/dino.safetensors" — и есть клип-вижн, что бы ни было в тегах.
# ---------------------------------------------------------------------------
_REPO_DIR_RULES = (
    # Порядок важен: "clip_vision" проверяется раньше общего "clip".
    ("clip_vision", r"^clip_vision$"),
    ("diffusion", r"^(?:diffusion_models?|unet)$"),  # unet/ — legacy-имя той же папки
    ("encoder", r"^(?:text_encoders?|text_encoder|clip|te)$"),
    ("lora", r"^loras?$"),
    ("vae", r"^vae$"),
    ("controlnet", r"^controlnet$"),
    ("embedding", r"^embeddings?$"),
    ("upscale", r"^upscale_models?$"),
    ("hypernetwork", r"^hypernetworks?$"),
)


def classify_repo_dir(file_path):
    """Тип по первой папке пути файла в репозитории.

    "vae/x.safetensors" -> "vae", "diffusion_models/x.gguf" -> "diffusion".
    Файл в корне репозитория (без подпапки) или незнакомая папка — "".
    """
    parts = str(file_path or "").replace("\\", "/").strip("/").split("/")
    if len(parts) < 2 or not parts[0]:
        return ""
    first = parts[0].lower()
    for token, pattern in _REPO_DIR_RULES:
        if re.match(pattern, first):
            return token
    return ""


def type_subdir(model_type):
    """Подпапка для типа модели ("" — тип неизвестен, папку не меняем)."""
    return TYPE_DIRS.get(str(model_type or ""), "")


# ---------------------------------------------------------------------------
# Алиасы имён папок для роутинга по закладкам пользователя.
# Ключ — каноничный токен типа, значение — множество нормализованных
# подстрок (basename.lower без всего кроме букв/цифр). Совпадение ищется
# ПОДСТРОКОЙ в последнем сегменте пути: "ComfyUI/models-loras-sdxl"
# подходит для lora, "D:/Models/loras" — тем более.
# "other" намеренно отсутствует: свалку по закладкам не раскидываем.
# ---------------------------------------------------------------------------
BOOKMARK_ALIASES = {
    "checkpoint": {"checkpoint", "checkpoints", "ckpt", "ckpts"},
    "lora": {"lora", "loras", "locon", "locons", "dora",
             "lycoris", "lycorises"},
    "lycoris": {"lora", "loras", "locon", "locons", "dora",
                "lycoris", "lycorises"},
    "vae": {"vae", "vaes"},
    "encoder": {"encoder", "encoders", "textencoder", "textencoders",
                "cliptext", "textmodel"},
    "controlnet": {"controlnet", "controlnets"},
    "embedding": {"embedding", "embeddings", "textualinversion",
                  "textualinversions", "embed", "embeds"},
    "upscale": {"upscale", "upscaler", "upscalers", "upscalemodels",
                "esrgan", "swinir"},
    "hypernetwork": {"hypernetwork", "hypernetworks", "hypernet"},
    "poses": {"pose", "poses", "openpose"},
    "diffusers": {"diffuser", "diffusers", "pipelines"},
    "diffusion": {"diffusionmodels", "diffusion", "unet"},
    "clip_vision": {"clipvision", "clipvisionmodels"},
}

# Минимальная длина алиаса для подстрочного совпадения. Однобуквенные
# токены ("t5", "ti", "clip") сознательно НЕ внесены в алиасы: они дают
# ложные срабатывания ("relative" содержит "ti"). Самый короткий алиас —
# "vae" (3 символа), поэтому подстрокой ищутся все алиасы без исключения.
_BOOKMARK_SUB_MIN = 3


def _bookmark_key(path):
    """Нормализованное имя папки закладки для сравнения с алиасами."""
    raw = str(path or "").replace("\\", "/").rstrip("/").split("/")[-1]
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def match_pinned_dir(dir_base, bookmarks):
    """Совпадает ли выбранный путь с одной из закладок (pinned-режим).

    Юзер явно тыкнул на закладку — её нормализованный путь равен пути
    закладки (без учёта регистра и слешей, относительные — через тот же
    резолв, что и safe_subdir). Возвращает исходную строку закладки или
    "" — путь не из закладок, работает тихий авто-поиск.
    """
    base = str(dir_base or "").strip()
    if not base:
        return ""
    norm_base = os.path.normcase(os.path.normpath(base))
    for bm in bookmarks or []:
        s = str(bm or "").strip()
        if not s:
            continue
        if os.path.normcase(os.path.normpath(s)) == norm_base:
            return s
    return ""


def match_bookmark_dir(model_type, bookmarks):
    """Найти папку типа модели среди закладок пользователя.

    Тихий режим без настроек: первое совпадение в порядке закладок
    побеждает (детерминировано). Совпадение — подстрока алиаса в имени
    папки (последний сегмент пути), чтобы находились и составные имена
    вроде "models-loras-sdxl". Однобуквенные токены ("t5", "ti", "clip")
    в алиасы не внесены — они давали бы ложные срабатывания ("relative"
    содержит "ti"). Возвращает исходную строку закладки (без нормализации)
    или "" — роутить некуда, ядро использует fallback dir_base + type_subdir.
    """
    mtype = str(model_type or "").lower()
    if not mtype or mtype == FALLBACK_TYPE:
        return ""
    aliases = BOOKMARK_ALIASES.get(mtype)
    if not aliases:
        return ""
    for bm in bookmarks or []:
        s = str(bm or "").strip()
        if not s:
            continue
        key = _bookmark_key(s)
        if not key:
            continue
        for alias in aliases:
            if key == alias:
                return s
            if len(alias) >= _BOOKMARK_SUB_MIN and alias in key:
                return s
    return ""


def classify_civitai(model_type, file_name=""):
    """Тип модели по данным CivitAI API (model.type) с fallback на имя файла."""
    key = re.sub(r"[^a-z0-9]", "", str(model_type or "").lower())
    found = CIVITAI_TYPES.get(key, "")
    if found:
        return found
    return classify_by_name(file_name)


def classify_hf(meta, file_path="", repo=""):
    """Тип модели по метаданным HF-API (теги, pipeline_tag, класс diffusers).

    meta — dict c ключами tags, pipeline_tag, library_name, diffusers_class,
    weight_file (см. fetch_hf_model_meta в hf_core_server.py). Любое поле
    может отсутствовать: при недоступности API метаданных просто нет.

    Приоритет: папка пути файла в репо (структура ComfyUI — самый точный
    признак для отдельного файла) → явные теги → класс diffusers → путь/имя
    файла → чекпойнт по совокупности признаков «это диффузионная модель и
    это файл весов».
    """
    meta = meta or {}

    # 0) Структура репозитория: первая папка пути файла ("clip_vision/",
    # "diffusion_models/", "vae/", …) прямо объявляет назначение весов.
    # Сильнее тегов: коллекции бывают тегнуты "lora", а конкретный файл
    # лежит в "vae/".
    repo_dir = classify_repo_dir(file_path)
    if repo_dir:
        return repo_dir

    tags = [str(t).lower() for t in (meta.get("tags") or [])]
    cls = str(meta.get("diffusers_class") or "").lower()
    pipe = str(meta.get("pipeline_tag") or "").lower()
    lib = str(meta.get("library_name") or "").lower()

    # 1) Явные теги HF — самый надёжный источник.
    if "lora" in tags or "lycoris" in tags:
        return "lora"
    if "textual-inversion" in tags or "textual_inversion" in tags:
        return "embedding"
    if "controlnet" in tags:
        return "controlnet"
    if "vae" in tags:
        return "vae"
    if "upscaler" in tags or pipe == "image-super-resolution":
        return "upscale"
    if "hypernetwork" in tags:
        return "hypernetwork"

    # 2) Класс diffusers из config (_class_name) — что за компонент в репо.
    if cls:
        if "lora" in cls:
            return "lora"
        if "autoencoder" in cls or cls.endswith("vae"):
            return "vae"
        if "controlnet" in cls:
            return "controlnet"
        if "clip" in cls or "textmodel" in cls or "textencoder" in cls or "t5" in cls:
            return "encoder"
        if "transformer2d" in cls or "unet" in cls:
            return "diffusers"

    # 3) Путь файла и имя репозитория.
    found = classify_by_name(file_path, repo)
    if found:
        return found

    # 4) Диффузионные признаки + файл весов -> чекпойнт. Без признаков
    # (например, GGUF LLM) тип не угадываем: уйдёт в "other".
    diffusion = (
        "diffusers" in tags
        or "stable-diffusion" in tags
        or "text-to-image" in tags
        or "image-to-image" in tags
        or pipe in ("text-to-image", "image-to-image", "unconditional-image-generation")
        or lib == "diffusers"
        or bool(cls)
    )
    if diffusion and meta.get("weight_file"):
        return "checkpoint"
    return ""


def _dedupe_join(parts):
    """Склеить токены через "-", выбросив повторы и вложенные дубликаты.

    Вложенность нужна для HF: репозиторий `owner/juggernaut-xl-v10-lora-sdxl`
    уже содержит слово "lora", и дописывать в конец ещё один "-lora" — шум.
    """
    out = []
    for p in parts:
        if not p:
            continue
        low = p.lower()
        if any(low == x.lower() or low in x.lower() for x in out):
            continue
        out.append(p)
    return "-".join(out)


def build_prefix(source="", kind="file", repo="", branch="main",
                 meta=None, model_type="", user_prefix=""):
    """Собрать префикс имени файла из метаданных.

    Формат:
        CivitAI : {Model}-v{Version}-{base}-{type}-{fp}
        HF      : {owner}-{Repo}-[{branch}-]{type}

    Возвращает строку без финального разделителя ("" — префикс не нужен).
    """
    meta = meta or {}
    parts = []
    # Пользовательский префикс всегда первый: если он задан руками, юзер
    # ожидает увидеть его в начале имени.
    parts.append(normalize_token(user_prefix))

    if str(source or "").lower().startswith("civitai"):
        name = normalize_token(meta.get("model_name") or "")
        version = normalize_token(meta.get("version_name") or "")
        if not name:
            # Имени модели нет (пустой ответ API) — берём имя версии.
            name, version = version, ""
        parts.append(name)
        if version and version.lower() != name.lower():
            parts.append(version if version.lower().startswith("v") else "v" + version)
        parts.append(normalize_base(meta.get("base_model")))
        parts.append(model_type)
        parts.append(normalize_token(meta.get("fp")))
    else:
        owner, _, rname = str(repo or "").partition("/")
        parts.append(normalize_token(owner))
        parts.append(normalize_token(rname))
        if branch and str(branch) != "main":
            parts.append(normalize_token(branch))
        parts.append(model_type)

    return _dedupe_join(parts)


def apply_prefix(name, prefix, max_len=_NAME_MAX):
    """Вставить префикс в имя файла, не потеряв расширение.

    sanitize() в ядре режет имя по 180 символам целиком, поэтому длинный
    префикс обрезал бы ".safetensors" вместе с хвостом имени — файл потерял бы
    понятный тип. Здесь расширение сохраняется всегда, а режется префикс
    (если имя уже само почти в лимите — режется само имя).
    """
    raw = str(name or "")
    base, ext = os.path.splitext(raw)
    if not base:
        base, ext = raw or "file", ""
    if len(ext) >= max_len - 8:
        # Экзотика вроде ".onnx_data" — расширение само съедает лимит.
        base, ext = raw, ""
    room = max_len - len(ext)
    pre = normalize_token(prefix, max_len)
    if pre:
        budget = room - 1 - len(base)   # -1 на разделитель "_"
        if budget >= 3:
            return f"{pre[:budget]}_{base}{ext}"
    return f"{base[:room]}{ext}"
