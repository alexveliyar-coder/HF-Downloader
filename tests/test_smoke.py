# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
test_smoke.py — минимальные smoke-тесты.

Запуск:  python -m tests.test_smoke
Или из CI: см. .github/workflows/ci.yml

Здесь намеренно нет pytest/unittest — проект маленький, и заводить
полный test-runner ради двух проверок не хочется. Если тестов станет
больше — переедем в pytest, добавим requirements-dev.txt.
"""
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent


def check_locale_files():
    """Все locales/*.json валидные, у всех одинаковый набор ключей."""
    print("1. Проверка locales/*.json …")
    files = sorted(ROOT.glob("locales/*.json"))
    assert files, "locales/ пустая"
    keys_sets = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            raise AssertionError(f"{p.name}: invalid JSON — {e}") from None
        assert isinstance(data, dict), f"{p.name}: not a dict at top level"
        keys_sets.append((p.name, set(data.keys())))
    # Сравниваем с английским (эталон).
    en = next(s for name, s in keys_sets if name == "en.json")
    missing = []
    extra = []
    for name, s in keys_sets:
        if name == "en.json":
            continue
        if not (s >= en):
            missing.append((name, en - s))
        if not (s <= en):
            extra.append((name, s - en))
    if missing:
        print("  WARN: locales without all en keys:")
        for name, miss in missing:
            print(f"    {name} missing: {', '.join(sorted(miss))}")
    if extra:
        print("  WARN: locales with extra keys (vs en):")
        for name, ex in extra:
            print(f"    {name} extra: {', '.join(sorted(ex))}")
    print(f"  OK ({len(files)} files)")


def check_updater_version():
    """VERSION в updater.py — это строка вида X.Y.Z."""
    print("2. Проверка updater.VERSION …")
    updater_src = (ROOT / "src" / "updater.py").read_text(encoding="utf-8")
    # Ищем строку VERSION = "..."
    import re
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', updater_src, re.M)
    assert m, "VERSION not found in updater.py"
    version = m.group(1)
    parts = version.split(".")
    assert len(parts) == 3, f"VERSION should be X.Y.Z, got {version!r}"
    for p in parts:
        assert p.isdigit(), f"VERSION part should be numeric: {p!r}"
    print(f"  OK: VERSION = {version}")


def check_html_size():
    """site/index.html не раздулся до неприличия (лимит — 500 КБ)."""
    print("3. Проверка размера site/index.html …")
    p = ROOT / "site" / "index.html"
    size = p.stat().st_size
    assert size < 500 * 1024, f"site/index.html больше 500 КБ ({size} байт) — пора разбивать на файлы"
    print(f"  OK: {size // 1024} КБ")


def check_no_secrets_in_history():
    """Ни один файл, который мы коммитим, не содержит очевидных секретов."""
    print("4. Поиск потенциальных секретов в коммитируемых файлах …")
    forbidden_patterns = [
        # Hugging Face: токены вида hf_ + 10+ алфавитно-цифровых символов.
        # Placeholder hf_xxxxxxxxxxxxxxxxxxxx (20 одинаковых 'x' или '0') — не секрет.
        (r"(?<!_)hf_(?!x{8,}|0{8,})[A-Za-z0-9]{10,}", "Hugging Face token"),
        (r"sk-[A-Za-z0-9]{20,}", "OpenAI-style key"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    ]
    import re
    bad = []
    for path in ROOT.rglob("*"):
        if any(part.startswith(".") and part != ".env.example" for part in path.parts):
            continue
        if path.is_dir() or path.suffix in (".png", ".jpg", ".ico", ".icns", ".pdf", ".zip", ".exe"):
            continue
        if "downloads" in path.parts or "build" in path.parts or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern, label in forbidden_patterns:
            if re.search(pattern, text):
                bad.append((path, label))
    if bad:
        msg = "Найдены паттерны секретов:\n"
        for p, label in bad:
            msg += f"  {p} — {label}\n"
        raise AssertionError(msg)
    print("  OK (ничего подозрительного)")


def check_model_naming():
    """model_naming: префикс из метаданных, тип модели, подпапка, расширение."""
    print("5. Проверка model_naming (префикс и авто-раскладка) …")
    sys.path.insert(0, str(ROOT / "src"))
    import hf_core_server as core
    import model_naming as mn

    # Свитч префикса: выкл = имя файла не трогаем (final_name = исходное),
    # вкл = авто-префикс из метаданных + ручной первым токеном.
    st_off = {"kind": "file", "dir": "C:/tmp/dl", "source": "hf",
              "name": "pytorch_lora_weights.safetensors",
              "auto_dir": False, "use_prefix": False, "prefix": "MyPack",
              "meta": {"tags": ["lora"], "weight_file": True,
                       "hf_loaded": True, "repo_name": "o/r"}, "token": ""}
    core.prepare_naming(st_off, tid="iprefix-off")
    assert st_off["final_name"] == "pytorch_lora_weights.safetensors", st_off
    assert st_off["type"] == "lora", st_off
    st_on = {"kind": "file", "dir": "C:/tmp/dl", "source": "hf",
             "name": "pytorch_lora_weights.safetensors",
             "auto_dir": False, "use_prefix": True, "prefix": "",
             "meta": {"tags": ["lora"], "weight_file": True,
                      "hf_loaded": True, "repo_name": "John6666/r"}, "token": ""}
    core.prepare_naming(st_on, tid="iprefix-on")
    assert st_on["final_name"].startswith("John6666-r-lora_"), st_on
    # Старые задачи без поля use_prefix — дефолт True (поведение не меняется)
    st_old = {"kind": "file", "dir": "C:/tmp/dl", "source": "hf",
              "name": "model.safetensors", "auto_dir": False, "prefix": "",
              "meta": {"weight_file": True, "hf_loaded": True,
                       "repo_name": "o/r"}, "token": ""}
    core.prepare_naming(st_old, tid="iprefix-old")
    assert st_old["final_name"].startswith("o-r_"), st_old

    # baseModel -> короткий токен префикса
    assert mn.normalize_base("SD 1.5") == "sd15"
    assert mn.normalize_base("SDXL 1.0") == "sdxl"
    assert mn.normalize_base("Flux.1 D") == "flux1d"
    assert mn.normalize_base("SD 3.5") == "sd35"
    assert mn.normalize_base("Pony") == "pony"
    assert mn.normalize_base("Other") == ""
    assert mn.normalize_base("") == ""

    # Тип модели с CivitAI (model.type)
    assert mn.classify_civitai("Checkpoint") == "checkpoint"
    assert mn.classify_civitai("LORA") == "lora"
    assert mn.classify_civitai("LoCon") == "lycoris"
    assert mn.classify_civitai("DoRA") == "lora"
    assert mn.classify_civitai("TextualInversion") == "embedding"
    assert mn.classify_civitai("VAE") == "vae"
    assert mn.classify_civitai("Upscaler") == "upscale"
    # Тип не пришёл — решаем по имени файла
    assert mn.classify_civitai("", "my_model_lora.safetensors") == "lora"

    # Тип модели с HF: явные теги важнее имени
    hf_lora = {"tags": ["lora", "diffusers"], "weight_file": True}
    assert mn.classify_hf(hf_lora, "pytorch_lora_weights.safetensors", "o/r") == "lora"
    hf_vae = {"tags": ["diffusers"], "diffusers_class": "AutoencoderKL", "weight_file": True}
    assert mn.classify_hf(hf_vae, "diffusion_pytorch_model.safetensors", "o/vae") == "vae"
    hf_ctrl = {"tags": ["controlnet"], "weight_file": True}
    assert mn.classify_hf(hf_ctrl, "diffusion_pytorch_model.safetensors", "o/r") == "controlnet"
    hf_enc = {"tags": ["diffusers"], "diffusers_class": "CLIPTextModelWithProjection",
              "weight_file": True}
    assert mn.classify_hf(hf_enc, "model.safetensors", "o/r") == "encoder"
    # Полный чекпойнт: тегов типа нет, но модель диффузионная и это веса
    hf_full = {"tags": ["diffusers", "text-to-image"], "library_name": "diffusers",
               "pipeline_tag": "text-to-image", "weight_file": True}
    assert mn.classify_hf(hf_full, "sd_xl_base_1.0.safetensors",
                          "stabilityai/stable-diffusion-xl-base-1.0") == "checkpoint"
    # Не диффузионная модель (LLM) — тип НЕ угадываем, уйдёт в other
    assert mn.classify_hf({}, "model.gguf", "meta-llama/Llama-3-8B") == ""
    # Метаданных нет вовсе — остаёмся на имени файла
    assert mn.classify_hf({}, "text_encoder/model.safetensors", "o/r") == "encoder"

    # Папка пути файла в репо — приоритетный признак (структура ComfyUI):
    # у Comfy-Org/TRELLIS.2 нет тегов, но папка называет тип сама. Реальные
    # ссылки, на которых классификатор раньше отдавал "other".
    assert mn.classify_hf({}, "clip_vision/dino_v3_vit_l.safetensors",
                          "Comfy-Org/TRELLIS.2") == "clip_vision"
    assert mn.classify_hf({}, "diffusion_models/trellis_2_bf16.safetensors",
                          "Comfy-Org/TRELLIS.2") == "diffusion"
    # unet/ — legacy-имя той же папки diffusion_models
    assert mn.classify_hf({}, "unet/diffusion_pytorch_model.safetensors",
                          "o/r") == "diffusion"
    # Папка сильнее тега: коллекция тегнута "lora", файл лежит в "vae/".
    assert mn.classify_hf({"tags": ["lora"]}, "vae/model.safetensors",
                          "o/collection") == "vae"
    # Файл в корне репо — папочного признака нет, работает как раньше.
    assert mn.classify_hf({}, "model.safetensors", "o/r") == ""

    # Подпапки (конвенция ComfyUI)
    assert mn.type_subdir("lora") == "loras"
    assert mn.type_subdir("lycoris") == "loras"
    assert mn.type_subdir("vae") == "vae"
    assert mn.type_subdir("encoder") == "text_encoders"
    assert mn.type_subdir("checkpoint") == "checkpoints"
    assert mn.type_subdir("diffusion") == "diffusion_models"
    assert mn.type_subdir("clip_vision") == "clip_vision"
    assert mn.type_subdir("nosuchtype") == ""

    # Префикс CivitAI: {Model}-v{Version}-{base}-{type}-{fp}
    civ = {"model_name": "DreamShaper", "version_name": "8",
           "base_model": "SD 1.5", "fp": "fp16"}
    assert mn.build_prefix(source="civitai_blue", meta=civ,
                           model_type="checkpoint") == "DreamShaper-v8-sd15-checkpoint-fp16"
    # Пробелы/скобки в имени модели не ломают имя файла
    civ2 = {"model_name": "Detail Tweaker (XL)", "version_name": "v1.0",
            "base_model": "SDXL 1.0", "fp": ""}
    assert mn.build_prefix(source="civitai_red", meta=civ2,
                           model_type="lora") == "DetailTweaker-XL-v1.0-sdxl-lora"
    # Имени модели нет — берём имя версии, пустые поля не тащим
    assert mn.build_prefix(source="civitai_blue", meta={"version_name": "v2"},
                           model_type="vae") == "v2-vae"
    # Совсем нет метаданных -> пустой префикс (имя файла не портится)
    assert mn.build_prefix(source="civitai_blue", meta={}, model_type="") == ""

    # Префикс HF: {owner}-{Repo}-[{branch}-]{type}, без дублей типа в имени
    assert mn.build_prefix(source="hf", repo="John6666/juggernaut-xl-v10-lora-sdxl",
                           model_type="lora") == "John6666-juggernaut-xl-v10-lora-sdxl"
    assert mn.build_prefix(source="hf", repo="stabilityai/sdxl-vae",
                           model_type="vae") == "stabilityai-sdxl-vae"
    assert mn.build_prefix(source="hf", repo="o/r", branch="v2.0",
                           model_type="vae") == "o-r-v2.0-vae"
    # Пользовательский префикс идёт первым
    assert mn.build_prefix(source="hf", repo="o/r", model_type="lora",
                           user_prefix="my pack") == "mypack-o-r-lora"

    # Вставка префикса: расширение сохраняется всегда
    assert mn.apply_prefix("dreamshaper_8.safetensors",
                           "DreamShaper-v8-sd15-checkpoint-fp16") == \
        "DreamShaper-v8-sd15-checkpoint-fp16_dreamshaper_8.safetensors"
    assert mn.apply_prefix("model.safetensors", "") == "model.safetensors"
    got = mn.apply_prefix("a" * 200 + ".safetensors", "p" * 200)
    assert got.endswith(".safetensors"), got[-32:]
    assert len(got) <= 180, len(got)
    # Экзотическое расширение и файл без расширения
    assert mn.apply_prefix("model.onnx_data", "x" * 50).endswith(".onnx_data")
    assert mn.apply_prefix("LICENSE", "o-r") == "o-r_LICENSE"

    # Файлы весов vs конфиги (от этого зависит fallback на чекпойнт)
    assert mn.is_weight_file("model.safetensors")
    assert mn.is_weight_file("model.gguf")
    assert not mn.is_weight_file("config.json")
    assert not mn.is_weight_file("README.md")

    # Роутинг по закладкам пользователя (тихий режим): точное совпадение,
    # алиас, дубли (первый выигрывает), нет совпадения, свалка other.
    bms = ["D:/Models/checkpoints", "D:/Models/loras", "E:/ComfyUI/models/vae"]
    assert mn.match_bookmark_dir("lora", bms) == "D:/Models/loras"
    assert mn.match_bookmark_dir("vae", bms) == "E:/ComfyUI/models/vae"
    assert mn.match_bookmark_dir("checkpoint", bms) == "D:/Models/checkpoints"
    # Алиас имени папки: text_encoder -> тип encoder
    assert mn.match_bookmark_dir("encoder", ["E:/ComfyUI/models/text_encoder"]) == \
        "E:/ComfyUI/models/text_encoder"
    # Дубли: первое совпадение в порядке закладок побеждает
    assert mn.match_bookmark_dir("lora", ["D:/SD15/loras", "D:/SDXL/loras"]) == \
        "D:/SD15/loras"
    # Нет совпадения -> "" (ядро использует dir_base + type_subdir)
    assert mn.match_bookmark_dir("controlnet", bms) == ""
    assert mn.match_bookmark_dir("", bms) == ""
    # Свалку other по закладкам не раскидываем
    assert mn.match_bookmark_dir("other", ["D:/Models/other"]) == ""
    # Относительный путь и мусорные записи не ломают поиск
    assert mn.match_bookmark_dir("vae", ["", "  ", "models/vae"]) == "models/vae"
    # Составное имя папки находится подстрокой
    assert mn.match_bookmark_dir("lora", ["E:/ComfyUI/models-loras-sdxl"]) == \
        "E:/ComfyUI/models-loras-sdxl"
    # Короткие имена не дают ложных срабатываний: "privateer" не содержит
    # ни одного алиаса целиком, а составные имена находятся подстрокой.
    assert mn.match_bookmark_dir("vae", ["D:/privateer"]) == ""
    assert mn.match_bookmark_dir("vae", ["D:/my-vae-files"]) == "D:/my-vae-files"

    # Pinned-режим: поле «Путь» совпало с закладкой — её выбор важнее
    # тихого авто-поиска (иначе «тыкнул, а ушло не туда»).
    pbms = ["D:/SD15/loras", "D:/SDXL/loras"]
    assert mn.match_pinned_dir("D:/SDXL/loras", pbms) == "D:/SDXL/loras"
    # Регистр и слеши не важны
    assert mn.match_pinned_dir("d:/sdxl\\loras", pbms) == "D:/SDXL/loras"
    # Путь не из закладок -> "" (работает тихий авто-поиск)
    assert mn.match_pinned_dir("D:/Models", pbms) == ""
    assert mn.match_pinned_dir("", pbms) == ""
    assert mn.match_pinned_dir("D:/Models", []) == ""
    print("  OK")


def check_auto_root_routing():
    """Режим авто-раскладки по КОРНЯМ (свитч автораспределения).

    - _clean_auto_roots нормализует payload: мусор, дубли, лимит;
    - АКТИВНЫЙ корень (первый в списке) побеждает БЕЗУСЛОВНО — это
      ровно то, что юзер выбрал в поле «Путь» (dir_source='auto-root');
      запасной корень ('auto-root-hit') берёмся только если активный недоступен;
    - тип не опознан -> корень/other и dir_source='' (попадает в
      фронтовский фильтр «Нераспределённые» / needsReview);
    - закладки/pinned в этом режиме НЕ читаются.
    """
    print("6. Проверка авто-раскладки по корням (prepare_naming) …")
    import os
    import shutil
    import tempfile
    # hf_core_server импортирует соседние модули голыми именами
    # (from civitai_client import ...) — как их запускает main.py,
    # положив src/ в sys.path. Повторяем то же для теста.
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    # --- нормализация списка корней ---
    assert H._clean_auto_roots(None) == []
    assert H._clean_auto_roots("not a list") == []
    assert H._clean_auto_roots([" a ", "a", "", None, "b"]) == ["a", "b"]
    assert H._clean_auto_roots([1, 2, "c"]) == ["c"]
    # Лимит: 8 уникальных корней, остальное отбрасывается
    assert len(H._clean_auto_roots([f"x{i}" for i in range(20)])) == 8

    # Активный корень ВСЕГДА первый, даже если фронт прислал пустой список
    # (юзер ввёл корень в поле, но не нажал чипс «+»). Регрессия: в этом
    # случае задача уходила в классическую раскладку (pinned > закладка типа
    # > base/type) и могла попасть в папку ручной закладки вместо корня/типа.
    assert H._effective_auto_roots(True, True, [], "D:/RootA") == ["D:/RootA"]
    assert H._effective_auto_roots(True, True, ["D:/RootB"], "D:/RootA") == \
        ["D:/RootA", "D:/RootB"]
    assert H._effective_auto_roots(True, True, ["D:/RootA", "D:/RootB"], "D:/RootA") == \
        ["D:/RootA", "D:/RootB"]
    # Дедуп по normcase/normpath: тот же путь с ".." не дублируется
    assert H._effective_auto_roots(True, True, ["D:/a/../RootA", "D:/B"], "D:/RootA") == \
        ["D:/RootA", "D:/B"]
    # Флаги выключены либо активного корня нет — авто-раскладку не применяем
    assert H._effective_auto_roots(False, False, ["D:/RootA"], "D:/RootA") == []
    assert H._effective_auto_roots(True, False, ["D:/RootA"], "D:/RootA") == []
    assert H._effective_auto_roots(True, True, [], "") == []
    assert len(H._effective_auto_roots(True, True, [f"D:/r{i}" for i in range(20)],
                                       "D:/active")) == 8

    tmp = tempfile.mkdtemp(prefix="hfdl_auto_roots_")
    try:
        root_a = os.path.join(tmp, "rootA")
        root_b = os.path.join(tmp, "rootB")
        root_c = os.path.join(tmp, "rootC")
        os.makedirs(os.path.join(root_b, "loras"))
        os.makedirs(os.path.join(root_a, "other"))
        os.makedirs(root_c)  # свежий корень, без loras

        def st_for(name, roots):
            return {
                "kind": "file",
                "source": "civitai_blue",  # без сети: classify_civitai локальный
                "name": name,
                "link": "", "url": "",
                "meta": {"model_type": "LORA" if "lora" in name.lower() else ""},
                "dir": tmp,  # dir_base — не участвует, roots важнее
                "auto_dir": True,
                "auto_root": True,
                "auto_roots": roots,
                "use_prefix": False, "prefix": "",
            }

        # 1) Активный корень C, в B loras уже есть — файл всё равно идёт в C.
        # Регрессия: ищался «первый корень, где уже есть подпапка
        # типа», и активный пропускался, если подпапки ещё не было — файл
        # уезжал в B. На живых данных юзер выбрал ...\models\test_download, а файл
        # лёг в ...\models\loras (там loras уже был только там). Активный корень
        # побеждает безусловно. Отдельный корень (rootC) — чтобы
        # случай 2 (претест что rootA/loras ещё несуществует).
        st = st_for("cool_lora.safetensors", [root_c, root_b])
        H.prepare_naming(st, "main", "t1")
        assert st["type"] == "lora", st["type"]
        assert os.path.normcase(st["dir"]) == os.path.normcase(
            os.path.join(root_c, "loras")), st["dir"]
        assert st["dir_source"] == "auto-root", st["dir_source"]

        # 2) Ни в одном корне нет loras -> активный корень + loras.
        # Превентивное создание: prepare_naming сам создаёт папку на диске.
        st = st_for("fresh_lora.safetensors", [root_a])
        assert not os.path.isdir(os.path.join(root_a, "loras")), "pre-test: не должен существовать"
        H.prepare_naming(st, "main", "t2")
        assert os.path.normcase(st["dir"]) == os.path.normcase(
            os.path.join(root_a, "loras")), st["dir"]
        assert st["dir_source"] == "auto-root", st["dir_source"]
        assert os.path.isdir(st["dir"]), "папка должна быть создана превентивно"

        # 3) Тип не опознан -> корень/other, dir_source пуст (needsReview).
        st = st_for("mystery.bin", [root_a, root_b])
        H.prepare_naming(st, "main", "t3")
        assert st["type"] == "other", st["type"]
        assert os.path.normcase(st["dir"]) == os.path.normcase(
            os.path.join(root_a, "other")), st["dir"]
        assert st["dir_source"] == "", st["dir_source"]
        assert os.path.isdir(st["dir"]), st["dir"]

        # 4) Пустой список после чистки -> fallback на dir_base + подпапка.
        st = st_for("cool_lora.safetensors", ["", "   "])
        H.prepare_naming(st, "main", "t4")
        assert os.path.normcase(st["dir"]) == os.path.normcase(
            os.path.join(H.safe_subdir(tmp), "loras")), st["dir"]
        assert os.path.isdir(st["dir"]), st["dir"]

        # 4b) Активный корень НЕДОСТУПЕН (нет диска/прав) -> запасной
        #     корень и dir_source='auto-root-hit' (в карточке видно, что ушло не туда).
        real_safe = H.safe_subdir

        def _no_root_c(rel, allow_absolute=True):
            if os.path.normcase(str(rel or "").strip()) == os.path.normcase(root_c):
                raise H.CoreError(400, "bad path")
            return real_safe(rel, allow_absolute=allow_absolute)

        H.safe_subdir = _no_root_c
        try:
            st = st_for("cool_lora.safetensors", [root_c, root_b])
            H.prepare_naming(st, "main", "t4b")
        finally:
            H.safe_subdir = real_safe
        assert os.path.normcase(st["dir"]) == os.path.normcase(
            os.path.join(root_b, "loras")), st["dir"]
        assert st["dir_source"] == "auto-root-hit", st["dir_source"]

        # 5) Ручной режим (auto_dir=False) не трогаем: dir = dir_base.
        st = st_for("cool_lora.safetensors", [])
        st["auto_dir"] = False
        st["auto_root"] = False
        H.prepare_naming(st, "main", "t5")
        assert st["dir"] == tmp, st["dir"]
        assert st["dir_source"] == "", st["dir_source"]

        # 6) Совсем свежий корень (его нет на диске) — создаются и корень,
        #    и подпапка типа одной цепочкой makedirs.
        root_d = os.path.join(tmp, "rootD")  # не занят раньше (случаи 1/4b занят rootC)
        st = st_for("cool_lora.safetensors", [root_d])
        assert not os.path.isdir(root_d), "pre-test: корня быть не должно"
        H.prepare_naming(st, "main", "t6")
        assert os.path.normcase(st["dir"]) == os.path.normcase(
            os.path.join(root_d, "loras")), st["dir"]
        assert os.path.isdir(root_d), "корень должен создаться автоматически"
        assert os.path.isdir(st["dir"]), "и подпапка типа тоже"

        # 7) repo_path из ссылки: путь файла внутри репо для классификатора.
        assert H.repo_path_from_file_url(
            "https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/"
            "clip_vision/dino_v3_vit_l.safetensors") == \
            "clip_vision/dino_v3_vit_l.safetensors"
        assert H.repo_path_from_file_url(
            "https://huggingface.co/o/r/blob/main/file.bin") == "file.bin"
        assert H.repo_path_from_file_url(
            "https://huggingface.co/o/r") == ""

        p = H.parse_link(
            "https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/"
            "diffusion_models/trellis_2_bf16.safetensors")
        assert p and p["repo_path"] == "diffusion_models/trellis_2_bf16.safetensors", p
        assert p["name"] == "trellis_2_bf16.safetensors", p

        # 8) prepare_naming для HF-задачи без repo_path: путь восстанавливается
        #    из ссылки, тип берётся из папки репо (clip_vision), а не other.
        #    meta hf_loaded=True — классификация без обращения к сети.
        st = {
            "kind": "file", "source": "hf",
            "name": "dino_v3_vit_l.safetensors",
            "link": "https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/"
                    "clip_vision/dino_v3_vit_l.safetensors",
            "url": "",
            "meta": {"hf_loaded": True},
            "dir": tmp, "auto_dir": True, "auto_root": True,
            "auto_roots": [root_a], "use_prefix": False, "prefix": "",
        }
        H.prepare_naming(st, "main", "t8")
        assert st["type"] == "clip_vision", st["type"]
        assert os.path.isdir(os.path.join(root_a, "clip_vision")), st["dir"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  OK")


def check_open_location_cmd():
    """Формат команды explorer /select: путь слит с флагом, обёрнут в кавычки.

    Регрессия: subprocess.Popen(["explorer.exe", "/select,", path]) для путей
    с пробелами давал '/select, C:\\...\\Cool Model.safetensors' — explorer
    не парсил это и открывал окно по умолчанию (рабочий стол) вместо папки.
    """
    print("7. Проверка команды explorer /select …")
    import os
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    # Кейс-регрессия: имя файла и папка с пробелами
    cmd = H._explorer_select_cmd(r"C:\My Models\Cool Model-v8-lora.safetensors")
    assert cmd == 'explorer.exe /select,"C:\\My Models\\Cool Model-v8-lora.safetensors"', cmd
    # Флаг и открывающая кавычка слитны, отдельного "/select, " не осталось
    assert ' /select,"' in cmd
    assert " /select, " not in cmd
    # Путь без пробелов — тот же формат
    cmd2 = H._explorer_select_cmd(r"D:\Models\loras\file.safetensors")
    assert cmd2 == 'explorer.exe /select,"D:\\Models\\loras\\file.safetensors"', cmd2
    # Относительный путь превращается в абсолютный
    cmd3 = H._explorer_select_cmd("rel\\file.bin")
    inner = cmd3.split('/select,"', 1)[1].rstrip('"')
    assert os.path.isabs(inner), cmd3
    print("  OK")


def check_auto_root_persistence():
    """Серверный слой корня авто-раскладки: save/load, перезапись, сброс.

    Путь переживает перезапуск даже при пустом localStorage: фронт пишет
    активный корень в .last_auto_root.txt (POST /api/last_auto_root) и
    восстанавливает его при старте (GET), если localStorage пуст.
    """
    print("8. Проверка сохранения корня авто-режима (.last_auto_root.txt) …")
    import os
    import shutil
    import tempfile
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    tmpdir = tempfile.mkdtemp(prefix="hfdl_ar_")
    old = H.AUTO_ROOT_FILE
    H.AUTO_ROOT_FILE = os.path.join(tmpdir, ".last_auto_root.txt")
    try:
        # Файла нет — пусто (не падаем, фронт решает fallback сам)
        assert H.load_auto_root() == ""
        # Запись/чтение
        H.save_auto_root(r"D:\Models")
        assert H.load_auto_root() == r"D:\Models"
        # Перезапись: юзер сменил корень между сессиями
        H.save_auto_root("E:/ComfyUI/models")
        assert H.load_auto_root() == "E:/ComfyUI/models"
        # Пустое значение = сброс (файл перезаписывается пустым)
        H.save_auto_root("")
        assert H.load_auto_root() == ""
    finally:
        H.AUTO_ROOT_FILE = old
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("  OK")


def check_origin_and_static_policy():
    """Политика доступа: чужой сайт не дёрнет ядро, страница не раздаёт файлы.

    Регрессия на две реальные дыры:
      1) браузеры не отправляют Origin на no-cors GET-подресурсы (<img>,
         <script>), поэтому «нет Origin» нельзя считать разрешением — иначе
         чужой сайт мог стереть журнал или подменить язык ядра;
      2) статик-сервер сайта отдавал весь cwd проекта (.env, .tasks.json,
         .hfdl_log.txt, downloads/**) — утечка через DNS-rebinding.
    """
    print("9. Проверка политики Origin и раздачи статики …")
    import http.server
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    class _FakeReq:
        """Заготовка вместо BaseHTTPRequestHandler: нужен лишь headers.get()."""
        _ref_ok = H.Handler._ref_ok
        _origin_ok = H.Handler._origin_ok

        def __init__(self, headers):
            self.headers = dict(headers)

    port = H._actual_web_port
    local = f"http://127.0.0.1:{port}/"
    localhost = f"http://localhost:{port}/"
    cases = [
        ({}, True, "curl/CLI: ни Origin, ни Referer"),
        ({"Referer": local}, True, "same-origin GET страницы (Referer наш)"),
        ({"Referer": localhost + "index.html"}, True, "localhost-вариант Referer"),
        ({"Referer": "http://evil.example/"}, False, "cross-site no-cors GET"),
        ({"Origin": local.rstrip("/")}, True, "наш Origin"),
        ({"Origin": "http://evil.example"}, False, "чужой Origin"),
        ({"Origin": "null", "Referer": local}, True, "pywebview: Origin null + наш Referer"),
        ({"Origin": "null"}, False, "Origin null без Referer (file://)"),
        ({"Origin": "null", "Referer": "file:///C:/evil.html"}, False, "Origin null + чужой Referer"),
    ]
    for headers, expected, why in cases:
        got = _FakeReq(headers)._origin_ok()
        assert got is expected, f"{why}: ожидалось {expected}, получено {got}"

    # Раздача статики: только сама страница, всё остальное — 404.
    import main as M
    assert Path(M._site_static_root()) == ROOT / "site", \
        f"корень раздачи должен быть site/, а не {M._site_static_root()}"
    for p in ("/", "/index.html"):
        assert M._site_path_allowed(p), f"страница обязана отдаваться: {p}"
    for p in ("/.env", "/.env.example", "/.tasks.json", "/.last_dir.txt",
              "/.last_auto_root.txt", "/.last_auto_roots.json", "/.history.json",
              "/.hfdl_log.txt", "/hfdl_bookmarks.json",
              "/main.py", "/src/hf_core_server.py", "/downloads/loras/x.safetensors",
              "/index.html.bak", "/list/", "/favicon.ico", "/%2e%2e/.env"):
        assert not M._site_path_allowed(p), f"не должно отдаваться: {p}"

    # _SiteHandler.__init__ обязан передать в базовый класс directory=site/
    # (иначе SimpleHTTPRequestHandler возьмёт os.getcwd() = корень проекта).
    captured = {}
    real_init = http.server.SimpleHTTPRequestHandler.__init__

    def _fake_init(self, *a, **kw):
        captured.update(kw)

    try:
        http.server.SimpleHTTPRequestHandler.__init__ = _fake_init
        M._SiteHandler(object(), None, None)
    finally:
        http.server.SimpleHTTPRequestHandler.__init__ = real_init
    assert captured.get("directory") == str(ROOT / "site"), \
        f"directory не передан в базовый класс: {captured!r}"
    print("  OK")


def check_atomic_state_save():
    """Атомарный сейв состояния: tmp + os.replace, .bak-fallback при порче.

    Регрессия на потерю всех задач: прямая запись open(path, "w") при
    kill/BSOD в середине оставляла обрезанный .tasks.json, и при старте
    load_tasks_state возвращал {} — задачи молча исчезали.
    """
    print("10. Проверка атомарной записи состояния (tmp + replace + .bak) …")
    import os
    import shutil
    import tempfile
    import threading
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    tmpdir = tempfile.mkdtemp(prefix="hfdl_atomic_")
    old_tasks, old_bak = H._TASKS_FILE, H._TASKS_BAK_FILE
    H._TASKS_FILE = os.path.join(tmpdir, ".tasks.json")
    H._TASKS_BAK_FILE = os.path.join(tmpdir, ".tasks.bak.json")
    old_tasks_map = H.TASKS
    H.TASKS = {}
    # Файловые константы мелких state-файлов — тоже на tmpdir,
    # чтобы тест не трогал реальные закладки/пути проекта.
    old_bm, old_ld, old_ar = H.BOOKMARKS_FILE, H.LAST_DIR_FILE, H.AUTO_ROOT_FILE
    H.BOOKMARKS_FILE = os.path.join(tmpdir, "hfdl_bookmarks.json")
    H.LAST_DIR_FILE = os.path.join(tmpdir, ".last_dir.txt")
    H.AUTO_ROOT_FILE = os.path.join(tmpdir, ".last_auto_root.txt")
    try:
        st = {
            "kind": "file", "source": "hf", "name": "m.safetensors",
            "url": "https://huggingface.co/o/r/resolve/main/m.safetensors?token=zzz",
            "link": "https://huggingface.co/o/r/blob/main/m.safetensors",
            "repo": "o/r", "repo_path": "", "rtype": "models", "branch": "main",
            "dir": tmpdir, "status": "downloading", "downloaded": 5, "total": 10,
            "speed": 0, "run": threading.Event(),
        }
        st["run"].set()
        H.TASKS["t1"] = st
        # Инвариант гонки save-vs-finish: downloading обязана попасть в снапшот.
        H.save_tasks_state()
        assert os.path.isfile(H._TASKS_FILE), "снапшот не записан"
        assert not os.path.exists(H._TASKS_FILE + ".tmp"), ".tmp не убран после replace"
        with open(H._TASKS_FILE, encoding="utf-8") as fh:
            import json as _j
            data = _j.load(fh)
        assert len(data) == 1 and data[0]["id"] == "t1", "задача потеряна при сейве"
        assert "token" not in data[0], "токен не должен лежать на диске"
        assert "token=" not in data[0]["url"], "токен в URL не вырезан"
        # Второй сейв кладёт предыдущий снапшот в .bak
        st["downloaded"] = 7
        H.save_tasks_state()
        assert os.path.isfile(H._TASKS_BAK_FILE), ".bak не создан"
        # Порча основного файла (обрезанный JSON как после kill) — старт
        # восстанавливается из .bak, а не теряет всё.
        with open(H._TASKS_FILE, "w", encoding="utf-8") as fh:
            fh.write('[{"id": "t1", "status": "downl')
        restored = H.load_tasks_state()
        assert "t1" in restored, "битый файл + .bak: задача потеряна"
        # Биты оба файла — пусто, но без исключения.
        with open(H._TASKS_FILE, "w", encoding="utf-8") as fh:
            fh.write("not json")
        with open(H._TASKS_BAK_FILE, "w", encoding="utf-8") as fh:
            fh.write("not json")
        assert H.load_tasks_state() == {}
        # Атомарность закладок/путей: после сейва нет .tmp-хвостов.
        H.save_bookmarks(["D:/A", "D:/B"])
        H.save_last_dir(tmpdir)
        H.save_auto_root("D:/Models")
        for p in (H.BOOKMARKS_FILE, H.LAST_DIR_FILE, H.AUTO_ROOT_FILE):
            assert not os.path.exists(p + ".tmp"), f".tmp-хвост у {p}"
    finally:
        H._TASKS_FILE, H._TASKS_BAK_FILE = old_tasks, old_bak
        H.TASKS = old_tasks_map
        H.BOOKMARKS_FILE, H.LAST_DIR_FILE, H.AUTO_ROOT_FILE = old_bm, old_ld, old_ar
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("  OK")


def check_download_integrity():
    """Целостность скачивания без сети: сверка размера + watchdog + ретраи.

    Регрессия на два тихих повреждения:
      1) усечённый файл (CDN отдал меньше заявленного) помечался done;
      2) зависший CDN (соединение живо, байт нет) держал задачу до 15 минут.
    Мокаем requests.get: подменяем requests.get внутри stream_to_file через
    monkeypatch requests.get — реальная сеть не используется.
    """
    print("11. Проверка целостности скачивания (размер + watchdog) …")
    import os
    import shutil
    import tempfile
    import threading
    import time
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    tmpdir = tempfile.mkdtemp(prefix="hfdl_integ_")
    real_get = H.requests.get
    try:
        class _Resp:
            def __init__(self, status=200, headers=None, chunks=()):
                self.status_code = status
                self.headers = dict(headers or {})
                self._chunks = list(chunks)

            def iter_content(self, chunk_size=1):
                return iter(self._chunks)

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise H.requests.exceptions.HTTPError(self.status_code)

            def close(self):
                pass

        def _st():
            st = {"cancel": False, "run": threading.Event(),
                  "speed_limit": 0, "base": 0, "base_total": 0,
                  "downloaded": 0, "total": 0, "speed": 0}
            st["run"].set()
            return st

        # 1) Усечённый файл: заявлено 10 байт, отдано 5 → CoreError(-3).
        H.requests.get = lambda *a, **k: _Resp(
            headers={"content-length": "10"}, chunks=[b"12345"])
        try:
            H.stream_to_file("https://x/y.bin", os.path.join(tmpdir, "t.bin"),
                             "", _st())
            raise AssertionError("truncated принят как done")
        except H.CoreError as e:
            assert e.status == -3, f"ожидался CoreError(-3), а не {e.status}"
        assert not os.path.exists(os.path.join(tmpdir, "t.bin")), \
            "усечённый файл должен удаляться"
        # 2) Ровный файл: заявлено 5, отдано 5 → ok, размер совпал.
        H.requests.get = lambda *a, **k: _Resp(
            headers={"content-length": "5"}, chunks=[b"12345"])
        n = H.stream_to_file("https://x/y.bin", os.path.join(tmpdir, "ok.bin"),
                             "", _st())
        assert n == 5, f"размер: {n}"
        # 3) Сервер не сообщил размер (total_size==0): принимаем как есть.
        H.requests.get = lambda *a, **k: _Resp(headers={}, chunks=[b"abc"])
        n = H.stream_to_file("https://x/y.bin", os.path.join(tmpdir, "u.bin"),
                             "", _st())
        assert n == 3, f"размер без content-length: {n}"
        # 4) Watchdog: keep-alive пустышки с паузами дольше STALL_TIMEOUT.
        # Реалистично: iter_content ждёт следующий чанк (sleep внутри
        # генератора), байт нет — через STALL_TIMEOUT рвём как Timeout
        # (а Timeout уже входит в _RETRYABLE → докачка через Range с .part).
        old_stall = H.STALL_TIMEOUT
        H.STALL_TIMEOUT = 0.05

        class _StalledResp(_Resp):
            def iter_content(self, chunk_size=1):
                for _ in range(1000):
                    time.sleep(0.02)
                    yield b""

        try:
            H.requests.get = lambda *a, **k: _StalledResp(
                headers={"content-length": "100"})
            t0 = time.monotonic()
            try:
                H.stream_to_file("https://x/y.bin",
                                 os.path.join(tmpdir, "s.bin"), "", _st())
                raise AssertionError("stall не распознан")
            except H.requests.exceptions.Timeout:
                pass
            assert time.monotonic() - t0 < 20, "watchdog сработал слишком поздно"
        finally:
            H.STALL_TIMEOUT = old_stall
        assert H.requests.exceptions.Timeout in H._RETRYABLE, \
            "Timeout обязан быть ретраибельным (докачка с .part)"
        assert H.STALL_TIMEOUT == 60.0, "дефолт watchdog — 60 секунд"

        # 5) Прогресс задачи: downloaded/total/speed пишутся в st во время
        # записи. Регрессия: весь блок прогресса оказался телом ветки elif
        # watchdog'а — то есть ПОСЛЕ raise и недостижимым. UI вечно показывал
        # «0 Б · 0 %» (и .tasks.json сохранял нули), хотя файл качался.
        class _SlowResp(_Resp):
            def iter_content(self, chunk_size=1):
                for c in self._chunks:
                    time.sleep(0.5)  # > 0.4 с — чтобы посчиталась скорость
                    yield c

        st5 = _st()
        H.requests.get = lambda *a, **k: _SlowResp(
            headers={"content-length": "10"}, chunks=[b"12345", b"12345"])
        H.stream_to_file("https://x/y.bin", os.path.join(tmpdir, "p.bin"),
                         "", st5)
        assert st5["downloaded"] == 10, f"прогресс не пишется: {st5['downloaded']}"
        assert st5["total"] == 10, f"total не пишется: {st5['total']}"
        assert st5["speed"] > 0, f"скорость не считается: {st5['speed']}"

        # 6) Лимит скорости: окно window_bytes реально учитывается. 2 чанка по
        # 1 МБ при лимите 1 МБ/с должны занять не меньше секунды (в мёртвом
        # коде лимит не работал вообще — sleep не вызывался ни разу).
        one_mb = b"x" * (1024 * 1024)
        st6 = _st()
        st6["speed_limit"] = 1  # МБ/с
        H.requests.get = lambda *a, **k: _Resp(
            headers={"content-length": str(2 * len(one_mb))},
            chunks=[one_mb, one_mb])
        t1 = time.monotonic()
        H.stream_to_file("https://x/y.bin", os.path.join(tmpdir, "l.bin"),
                         "", st6)
        elapsed = time.monotonic() - t1
        assert elapsed >= 1.5, f"лимит скорости не соблюдается: {elapsed:.2f}s"
        assert st6["downloaded"] == 2 * len(one_mb), st6["downloaded"]
        assert st6["total"] == 2 * len(one_mb), st6["total"]
        # 7) ДОКАЧКА (Range + 206): прогресс обязан учитывать уже скачанный
        # префикс .part. Регрессия: `downloaded - start` отбрасывал докачанное,
        # и после ретрая/рестарта счётчик прыгал на ~0 % — задача выглядела
        # «скачивается заново», хотя файл дописывался (проверено на живой
        # задаче: .part 5.30 ГБ против 2.05 ГБ в UI — минус префикс 3.25 ГБ).
        dest7 = os.path.join(tmpdir, "r.bin")
        with open(dest7 + ".part", "wb") as fh7:
            fh7.write(b"AAA")  # 3 байта скачано до обрыва
        seen7 = {}

        def _get7(url, headers=None, **kw):
            seen7["headers"] = dict(headers or {})
            return _Resp(status=206,
                         headers={"Content-Range": "bytes 3-7/8",
                                  "content-length": "5"},
                         chunks=[b"BBBBB"])

        H.requests.get = _get7
        st7 = _st()
        n7 = H.stream_to_file("https://x/y.bin", dest7, "", st7)
        rng = seen7["headers"].get("Range")
        assert rng == "bytes=3-", f"докачка без заголовка Range: {rng}"
        with open(dest7, "rb") as fh7:
            assert fh7.read() == b"AAABBBBB", "докачка испортила префикс .part"
        assert n7 == 8, f"размер после докачки: {n7}"
        got7 = st7["downloaded"]
        assert got7 == 8, f"прогресс сбросился на докачке: {got7} (ждём 8)"
        assert st7["total"] == 8, f"total после докачки: {st7['total']}"
        # 8) Докачанный объём виден ДО первого чанка: восстановленная задача
        # не должна мигать «0 Б», пока идёт редирект на CDN.
        dest8 = os.path.join(tmpdir, "r2.bin")
        with open(dest8 + ".part", "wb") as fh8:
            fh8.write(b"X" * 4096)
        st8 = _st()
        seen8 = []

        class _NoBodyResp(_Resp):
            def iter_content(self, chunk_size=1):
                seen8.append(st8["downloaded"])
                return iter(())

        H.requests.get = lambda *a, **k: _NoBodyResp(
            headers={"content-length": "0"}, chunks=[])
        H.stream_to_file("https://x/y.bin", dest8, "", st8)
        assert seen8 and seen8[0] == 4096, (
            f"до первого чанка прогресс должен быть 4096, а не {seen8}")
    finally:
        H.requests.get = real_get
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("  OK")


def check_auto_roots_list_persistence():
    """Серверный слой СПИСКА корней авто-раскладки (.last_auto_roots.json).

    Раньше список корней жил только в localStorage, а на диск писался лишь
    активный корень: при слетевшем профиле WebView2 терялись все корни, кроме
    активного, и «класть в первый корень, где уже есть loras/checkpoints»
    (dir_source='auto-root-hit') переставало работать.
    """
    print("12. Проверка сохранения СПИСКА корней (.last_auto_roots.json) …")
    import os
    import shutil
    import tempfile
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    tmpdir = tempfile.mkdtemp(prefix="hfdl_ar_list_")
    old = H.AUTO_ROOTS_FILE
    H.AUTO_ROOTS_FILE = os.path.join(tmpdir, ".last_auto_roots.json")
    try:
        # Файла нет — пустой список (не падаем, фронт решает fallback сам)
        assert H.load_auto_roots() == []
        # Запись/чтение с сохранением порядка (активный = [0])
        assert H.save_auto_roots([r"D:\Models", r"E:\ComfyUI\models"])
        assert H.load_auto_roots() == [r"D:\Models", r"E:\ComfyUI\models"]
        # Нормализация как в payload задачи: мусор, дубли, не-строки
        H.save_auto_roots([" a ", "a", "", None, 5, "b"])
        assert H.load_auto_roots() == ["a", "b"]
        # Лимит — 8 корней
        H.save_auto_roots([f"r{i}" for i in range(20)])
        assert len(H.load_auto_roots()) == 8
        # Атомарная запись: .tmp-хвостов не остаётся
        assert not os.path.exists(H.AUTO_ROOTS_FILE + ".tmp"), ".tmp-хвост"
        # Битый файл — пустой список, без исключения
        with open(H.AUTO_ROOTS_FILE, "w", encoding="utf-8") as fh:
            fh.write("{")
        assert H.load_auto_roots() == []
    finally:
        H.AUTO_ROOTS_FILE = old
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("  OK")


def check_download_history():
    """История скачивания (.history.json): путь файла, лимит, отсутствие токена.

    .tasks.json хранит только незавершённые задачи, поэтому после done путь
    файла терялся. История пишется в run_task() (done/error) и отдаётся через
    GET /api/history.
    """
    print("13. Проверка истории скачивания (.history.json) …")
    import os
    import shutil
    import tempfile
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from src import hf_core_server as H

    tmpdir = tempfile.mkdtemp(prefix="hfdl_hist_")
    old_file, old_max = H.HISTORY_FILE, H.HISTORY_MAX
    H.HISTORY_FILE = os.path.join(tmpdir, ".history.json")
    H.HISTORY_MAX = 3  # чтобы не писать 500 записей ради ротации
    try:
        # Файла нет — пустая история
        assert H.load_history() == []
        # Репо-задача: «путь файла» — папка репозитория
        repo_entry = H._history_entry({"kind": "repo", "dir": r"D:\Models\repo",
                                       "name": "org/repo", "status": "done"})
        assert os.path.normcase(repo_entry["path"]) == os.path.normcase(r"D:\Models\repo"), repo_entry

        # file-задача: путь = папка + имя НА ДИСКЕ (final_name с префиксом)
        for i in range(5):
            H.append_history({
                "kind": "file", "dir": r"D:\Models\loras",
                "name": f"f{i}.safetensors", "final_name": f"pref_f{i}.safetensors",
                "status": "done", "downloaded": 10 + i, "type": "lora",
                "dir_source": "auto-root", "token": "hf_secret_value",
            })
        items = H.load_history()
        # Ротация: максимум HISTORY_MAX, новейшие первыми
        assert len(items) == 3, len(items)
        assert items[0]["name"] == "f4.safetensors", items[0]
        assert os.path.normcase(items[0]["path"]) == os.path.normcase(
            os.path.join(r"D:\Models\loras", "pref_f4.safetensors")), items[0]["path"]
        assert items[0]["size"] == 14, items[0]["size"]
        # limit отдаёт только N последних
        assert len(H.load_history(limit=1)) == 1
        # Токен в файл истории не попадает (как и в .tasks.json)
        with open(H.HISTORY_FILE, encoding="utf-8") as fh:
            raw = fh.read()
        assert "hf_secret_value" not in raw, "токен утёк в историю"
        assert "token" not in raw, "поле token не должно писаться в историю"
        # Битый файл — пустая история, без исключения
        with open(H.HISTORY_FILE, "w", encoding="utf-8") as fh:
            fh.write("not json")
        assert H.load_history() == []
        # clear_history оставляет валидный пустой список
        assert H.save_history([{"a": 1}])
        H.clear_history()
        assert H.load_history() == []

        # id задачи обязан попадть в запись истории. Раньше он жив только
        # КЛЮЧЕМ в TASKS, а в самом словаре задачи его не было — .history.json
        # получал id="". run_task кладёт id в st (setdefault),
        # поэтому проверяем и перенос поля, и сам факт
        # инициализации в run_task.
        with_id = H._history_entry({"kind": "file", "dir": r"D:\Models\loras",
                                    "name": "b.safetensors", "status": "done",
                                    "downloaded": 7, "id": "t123-1"})
        assert with_id["id"] == "t123-1", with_id["id"]
        run_src = (ROOT / "src" / "hf_core_server.py").read_text(encoding="utf-8")
        assert 'st.setdefault("id", tid)' in run_src, (
            "run_task не инициализирует id — история получит пустой id")
    finally:
        H.HISTORY_FILE, H.HISTORY_MAX = old_file, old_max
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("  OK")


def check_no_dead_code_after_raise():
    """Нет операторов после raise в одном блоке (недостижимый код).

    Регрессия: в stream_to_file() весь блок прогресса оказался телом ветки
    elif watchdog'а — после raise, то есть недостижимым. Python это «съедает»
    молча, ruff тоже (синтаксически валидно), а UI показывал 0 Б / 0 % при
    реально качающемся файле.
    """
    print("14. Проверка мёртвого кода после raise …")
    import ast
    targets = [ROOT / "main.py", *sorted((ROOT / "src").glob("*.py")),
               ROOT / "tests" / "test_smoke.py"]
    bad = []
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list):
                continue
            for i, stmt in enumerate(body[:-1]):
                if isinstance(stmt, ast.Raise):
                    nxt = body[i + 1]
                    bad.append(f"{path.name}:{nxt.lineno} (после raise на {stmt.lineno})")
    assert not bad, "недостижимый код после raise: " + ", ".join(bad)
    print("  OK")


def check_ui_init_order():
    """UI (index.html): состояние журнала/истории готово ДО блока init.

    Регрессия: applyLang() вызывается в блоке init, а `var logsFilter` /
    `var logsCache` исполнялись ниже по файлу — при вызове из init они были
    `undefined` (hoisting). Любой renderLogs() из applyLang падал на
    `logsCache.filter`, applyLang() обрывал цепочку init, `initClipPerm()`
    не выполнялся — наблюдатель буфера не стартовал, и скопированные ссылки
    не попадали в список (буфер в UI оставался пустым).
    """
    print("15. Проверка порядка инициализации UI (index.html) …")
    lines = (ROOT / "site" / "index.html").read_text(encoding="utf-8").splitlines()

    def first_line(needle, exact=False):
        for i, line in enumerate(lines, 1):
            hit = (line == needle) if exact else (needle in line)
            if hit:
                return i
        raise AssertionError(f"не найдено в site/index.html: {needle!r}")

    init_marker = first_line("/* ---------- init ---------- */")
    # Именно top-level вызовы цепочки init (в обработчике меню языка тоже есть
    # applyLang(), поэтому сверяем строку целиком, а не подстроку).
    init_apply = first_line("  applyLang();", exact=True)
    init_clip = first_line("  initClipPerm();", exact=True)
    # Порядок init-цепочки: язык/разметка → задачи ядра → наблюдатель буфера.
    assert init_marker < init_apply < init_clip, (init_marker, init_apply, init_clip)
    # Опрос буфера стартует только по флагу clipboardPolling (его ставит
    # initClipPerm после разрешения) — гвард обязан остаться на месте.
    assert "if (!clipboardPolling) return;" in "\n".join(lines), "нет гварда опроса буфера"
    for decl in ("var logsFilter = 'all';", "var logsCache = [];",
                 "var logsOpen = false;", "var logsLastErrorCount = 0;",
                 "var historyCache = [];"):
        ln = first_line(decl)
        assert ln < init_marker, f"{decl} объявлен ниже блока init ({ln} > {init_marker})"
    # Наблюдатель буфера стартует только по флагу clipboardPolling — init
    # обязан дойти до initClipPerm(), иначе ссылки не попадут в список.
    assert first_line("function initClipPerm()") < init_clip, "initClipPerm не вызван"
    print("  OK")


def _js_lang_blocks(body):
    import re
    """(код языка, текст блока) для объектного литерала вида { EN: {...}, ... }.

    Скобки считаем ПОТОЧНО, потому что в значениях встречаются фигурные
    скобки плейсхолдеров ({0}, {1}) — наивный regex по всему блоку здесь
    ошибается.
    """
    out = []
    for m in re.finditer(r"^([ \t]*)([A-Z]{2}):[ \t]*\{", body, re.M):
        st = m.end() - 1
        depth, k = 0, st
        while k < len(body):
            if body[k] == "{":
                depth += 1
            elif body[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append((m.group(2), body[st:k + 1]))
    return out


def _js_entries(blk):
    import re
    """Ключи верхнего уровня объектного литерала (строковые значения).

    Пропускает ЗАПЯТЫЕ и КОММЕНТАРИИ (// и /* */) — без этого разбор
    обрывался на "// CivitAI" внутри блока EN и давал ложные пропуски.
    """
    key_re = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
    out = []
    i, n = 1, len(blk) - 1
    while i < n:
        while i < n:
            c = blk[i]
            if c.isspace() or c == ",":
                i += 1
            elif c == "/" and i + 1 < n and blk[i + 1] == "/":
                j = blk.find("\n", i)
                i = n if j < 0 else j + 1
            elif c == "/" and i + 1 < n and blk[i + 1] == "*":
                j = blk.find("*/", i + 2)
                i = n if j < 0 else j + 2
            else:
                break
        if i >= n:
            break
        m = key_re.match(blk, i)
        if not m:
            break
        out.append(m.group(0))
        i = m.end()
        while i < n and blk[i] != ":":
            i += 1
        i += 1
        if i < n and blk[i] in "\"'":
            q = blk[i]
            i += 1
            while i < n:
                if blk[i] == "\\":
                    i += 2
                    continue
                if blk[i] == q:
                    break
                i += 1
            i += 1
        else:
            depth = 0
            while i < n:
                c = blk[i]
                if c in "\"'":
                    q = c
                    i += 1
                    while i < n:
                        if blk[i] == "\\":
                            i += 2
                            continue
                        if blk[i] == q:
                            break
                        i += 1
                elif c in "{[(":
                    depth += 1
                elif c in "}])":
                    if depth == 0:
                        break
                    depth -= 1
                elif c == "," and depth == 0:
                    break
                i += 1
    return set(out)


def check_ui_i18n_parity():
    """Встроенные словари UI (T и I18N_EXTRA) одинаковы во всех 12 языках.

    Регрессия: часть фич (CivitAI, автораспределение, префикс имени,
    фильтр «Не разобрано», вкладка «Скачано») была заведена только в
    RU/EN, и в остальных 10 языках молча показывалась английская строка
    (fallback). Плюс три подсказки были зашитыми русскими в HTML и не
    переназначались вообще. Теперь это проверяется тестом.
    """
    print("16. Проверка паритета переводов UI (T / I18N_EXTRA) …")
    src = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    import re
    for label, a, b in (("T", "var T = {", "\n  };"),
                        ("I18N_EXTRA", "I18N_EXTRA = {", "function E()")):
        i = src.find(a)
        assert i > 0, f"не найден {label} в site/index.html"
        j = src.find(b, i)
        assert j > i, f"не найден конец {label}"
        bl = _js_lang_blocks(src[i:j])
        assert len(bl) == 12, f"{label}: ожидалось 12 языков, найдено {len(bl)}"
        keys = dict((code, _js_entries(blk)) for code, blk in bl)
        en = keys["EN"]
        assert en, f"{label}: блок EN пуст"
        for code, k in keys.items():
            miss = sorted(en - k)
            extra = sorted(k - en)
            assert not miss, f"{label}/{code}: нет ключей {miss}"
            assert not extra, f"{label}/{code}: лишние ключи {extra}"
        print(f"    {label}: {len(en)} ключей в 12 языках — OK")
    # Три подсказки, которые раньше не переводились никогда
    # Ведущий пробел в значении — ошибка: было
    # folder:' фолдер' в урду и менялось метку метки). Завершающий пробел
    # у relHint — там он нужен, поэтому проверяем только ведущий.
    for _l, _a, _b in (("T", "var T = {", "\n  };"),
                      ("I18N_EXTRA", "I18N_EXTRA = {", "function E()")):
        _i = src.find(_a)
        _j = src.find(_b, _i)
        for _c, _blk in _js_lang_blocks(src[_i:_j]):
            _bad = re.search(r":'[ \t\u00a0]", _blk)
            assert _bad is None, (
                f"{_l}/{_c}: ведущий пробел в значении: "
                f"{_blk[_bad.start():_bad.start() + 30]!r}")
    for needle in ("$('logsBtn').title = u.logsTtl;",
                   "$('pasteTokBtn').title = e.pasteTokTip;",
                   "$('autoRootInp').placeholder = e.autoRootPh;"):
        assert needle in src, f"applyLang не переводит: {needle}"
    print("  OK")


def main():
    checks = [
        check_locale_files,
        check_updater_version,
        check_html_size,
        check_no_secrets_in_history,
        check_model_naming,
        check_auto_root_routing,
        check_open_location_cmd,
        check_auto_root_persistence,
        check_origin_and_static_policy,
        check_atomic_state_save,
        check_download_integrity,
        check_auto_roots_list_persistence,
        check_download_history,
        check_no_dead_code_after_raise,
        check_ui_init_order,
        check_ui_i18n_parity,
    ]
    failed = 0
    for c in checks:
        try:
            c()
        except AssertionError as e:
            print("  FAIL:", e)
            failed += 1
        except Exception:
            print("  ERROR:")
            traceback.print_exc()
            failed += 1
    print()
    if failed:
        print(f"FAILED: {failed} check(s)")
        sys.exit(1)
    print("All smoke checks passed.")


if __name__ == "__main__":
    main()
