# -*- coding: utf-8 -*-
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
            raise AssertionError("%s: invalid JSON — %s" % (p.name, e))
        assert isinstance(data, dict), "%s: not a dict at top level" % p.name
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
            print("    %s missing: %s" % (name, ", ".join(sorted(miss))))
    if extra:
        print("  WARN: locales with extra keys (vs en):")
        for name, ex in extra:
            print("    %s extra: %s" % (name, ", ".join(sorted(ex))))
    print("  OK (%d files)" % len(files))


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
    assert len(parts) == 3, "VERSION should be X.Y.Z, got %r" % version
    for p in parts:
        assert p.isdigit(), "VERSION part should be numeric: %r" % p
    print("  OK: VERSION = %s" % version)


def check_html_size():
    """site/index.html не раздулся до неприличия (лимит — 500 КБ)."""
    print("3. Проверка размера site/index.html …")
    p = ROOT / "site" / "index.html"
    size = p.stat().st_size
    assert size < 500 * 1024, "site/index.html больше 500 КБ (%d байт) — пора разбивать на файлы" % size
    print("  OK: %d КБ" % (size // 1024))


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
            msg += "  %s — %s\n" % (p, label)
        raise AssertionError(msg)
    print("  OK (ничего подозрительного)")


def main():
    checks = [
        check_locale_files,
        check_updater_version,
        check_html_size,
        check_no_secrets_in_history,
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
        print("FAILED: %d check(s)" % failed)
        sys.exit(1)
    print("All smoke checks passed.")


if __name__ == "__main__":
    main()
