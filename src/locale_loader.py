# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
locale_loader.py — Localization module for HF Downloader.

Auto-detects OS language and loads JSON files from the locales/ folder.
Supported languages: 12 (en, zh, hi, es, fr, ar, bn, pt, ru, ur, de, ja)

Usage examples in Python code:

    # In backend modules like main.py or hf_core_server.py
    L = get_locale()                          # auto-detect OS language
    print(L.t("console_start"))               # → "HF Downloader started (offline)"

Supported languages: en, zh, hi, es, fr, ar, bn, pt, ru, ur, de, ja

See README.md for full documentation.
"""
import json
import os
import sys
from pathlib import Path

# Base folder with translations. After the src/ refactor the .json files
# live in the project root (`<repo>/locales/`), one level above this file.
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

# Supported languages — 12 total, ordered by number of speakers descending
# (en > zh > hi > es > fr > ar > bn > pt > ru > ur > de > ja). Must stay in
# sync with `var LANGS = [...]` in site/index.html.
SUPPORTED_LANGUAGES = ["en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ur", "de", "ja"]


def _normalize_code(raw):
    """'ru_RU', 'ru-RU', 'RUS', 'rus' -> 'ru'. Returns '' if unknown."""
    if not raw:
        return ""
    s = str(raw).strip().lower().replace("-", "_")
    first = s.split("_")[0].split(";")[0].split(".")[0].split("@")[0]
    # 3-letter / long names -> 2-letter code
    _aliases = {
        "eng": "en", "english": "en",
        "rus": "ru", "russian": "ru",
        "ger": "de", "deu": "de", "deutsch": "de",
        "fra": "fr", "fre": "fr", "french": "fr",
        "spa": "es", "spanish": "es",
        "por": "pt", "portuguese": "pt",
        "chi": "zh", "zho": "zh", "chinese": "zh",
        "hin": "hi", "hindi": "hi",
        "ara": "ar", "arabic": "ar",
        "ben": "bn", "bengali": "bn",
        "urd": "ur", "urdu": "ur",
        "jpn": "ja", "jap": "ja", "japanese": "ja",
    }
    if first in _aliases:
        return _aliases[first]
    prefix = first[:2]
    if prefix in SUPPORTED_LANGUAGES:
        return prefix
    return ""


def _detect_os_language():
    """Detect the user's OS language.

    Returns a two-letter locale code or 'en' as default fallback."""
    # 0) Explicit env override (works on all OSes, incl. Windows)
    for var in ("HFDL_LANG", "LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        raw = (os.environ.get(var) or "").strip().split(";")[0].split(",")[0]
        code = _normalize_code(raw)
        if code:
            return code

    # Windows: GetUserDefaultLocaleName via ctypes (real OS language,
    # not env vars which are usually empty on Windows).
    if os.name == "nt":
        try:
            import ctypes
            _buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(_buf, 85):
                code = _normalize_code(_buf.value)
                if code:
                    return code
        except Exception:
            pass

    # POSIX systems: locale module
    try:
        import locale as loc_module

        candidates = []
        for getter in ("getdefaultlocale", "getlocale"):
            try:
                fn = getattr(loc_module, getter, None)
                if fn is None:
                    continue
                res = fn()
                if isinstance(res, (list, tuple)):
                    candidates.extend([x for x in res if isinstance(x, str)])
                elif isinstance(res, str):
                    candidates.append(res)
            except Exception:
                continue
        for cand in candidates:
            code = _normalize_code(cand)
            if code:
                return code
    except ImportError:
        pass

    # Fallback — English as default language for all systems that can't detect locale properly. This is the safest choice since most users will have a working browser anyway and we only need this to set console output messages correctly
    return "en"


def _load_language(code):
    """Load translation JSON file for specified language code."""
    filepath = LOCALES_DIR / f"{code}.json"

    if not filepath.exists():
        print(f"[locale] File {filepath} not found, falling back to en", file=sys.stderr)

        # Try English as fallback — this is the most common case when users install on non-English systems
        code = "en"
        filepath = LOCALES_DIR / f"{code}.json"

    # If even English is missing — just use empty dict and let UI show defaults
    try:
        with open(filepath, encoding="utf-8") as fh:
            data = json.load(fh)

        return {"data": data, "_lang_code_": code}

    except (OSError, ValueError):
        # If file is corrupted or unreadable — return empty locale
        print(f"[locale] Failed to load {filepath}, using defaults", file=sys.stderr)
        return {"data": {}, "_lang_code_": "en"}


def get_locale(lang=None):
    """Get a locale object for the specified or auto-detected language.

    Args:
        lang — explicit language override; None means use OS detection

    Returns:
        A LocaleObject with .t() method and .lang property

    Example usage in backend code::

            L = get_locale("ru")

            # Get a translated string, optionally substituting parameters via %s or {}
            msg1 = L.t("restore_tasks", 3)   → "restored 3 task(s)"
            msg2 = L.t("downloaded_file_0_bytes_of_total_n_bytes_are_complete" , filename="model.bin")
    """

    if lang is None:
        # Auto-detect from OS — this ensures the console output matches user's system language
        detected = _normalize_code(_detect_os_language())
        if detected in SUPPORTED_LANGUAGES:
            return get_locale(detected)
        # If no match found, default to English — safest fallback that works everywhere. This is the most common path since many users install on non-English systems and we want them at least seeing something readable in console output
        lang = "en"

    # Validate language code against supported languages (case-insensitive)
    if isinstance(lang, str):
        lang = _normalize_code(lang) or lang.strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        print(f"[locale] Language '{lang}' unsupported; falling back to en", file=sys.stderr)
        lang = "en"

    locale_data = _load_language(lang or "en")
    data_dict = dict(locale_data.get("data", {}))
    code = str(locale_data.get("_lang_code_", lang))

    class LocaleObject(dict):
        def __init__(self, d):
            self._dict_ = d
            self._code_ = code

        def __getattr__(self, name):
            if name in self._dict_:
                return self._dict_[name]
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        @property
        def t(self): return _Translator(self)

        @property
        def lang(self): return self._code_ or "en"

    class _Translator(dict):
        # All translatable strings — organized by module for easy maintenance.
        # Each key maps to a string that appears in the UI or console output,
        # optionally with %s placeholders for dynamic substitution (e.g., filenames).

        def __init__(self, locale_obj): self.locale = locale_obj
        def __getitem__(self, key):
            return str(self.locale._dict_.get(key, f"[{key}] untranslated"))
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError:
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'") from None
        def __call__(self, key, *args, **kwargs):
            """Allow calling as function: t('key') -> translated string.

            Optional substitution: if the string contains printf-style
            placeholders (e.g. %d, %s) and `args` are given, they're
            substituted via the % operator. If the string contains
            {name}-style placeholders and `kwargs` are given, they're
            substituted via str.format(). Any formatting error falls
            back to the raw template so the user still sees something.
            """
            s = str(self.locale._dict_.get(key, f"[{key}] untranslated"))
            if args and "%" in s:
                try:
                    return s % args
                except (TypeError, ValueError):
                    return s
            if kwargs:
                try:
                    return s.format(**kwargs)
                except (KeyError, IndexError, ValueError):
                    return s
            return s

    return LocaleObject(data_dict)


def get_available_languages():
    """Return list of available language codes from installed .json files."""
    languages = []

    if LOCALES_DIR.exists():
        for p in sorted(LOCALES_DIR.iterdir(), key=lambda x: x.name.lower()):

            # Only include JSON locale files that match our supported set. This prevents
            # accidentally including unrelated .json config or data files from being listed as languages

            if p.is_file() and p.suffix == ".json" and p.stem.replace("-", "_").lower() in SUPPORTED_LANGUAGES:
                languages.append(p.stem.lower())

    return sorted(languages, key=str.lower)


# Global cache for performance — initialized once at import time to avoid
# repeated filesystem lookups on every module load. This is a one-time cost that pays off during long-running sessions where get_locale() might be called multiple times (e.g., in error handlers or status updates)
_global_cache = None

def init_locale(lang=None):
    """Initialize and cache the global locale object for this process run.

    Args:
        lang: explicit language override; None means use saved preference or OS detection.

    Returns:
        A cached LocaleObject, or newly created one if not yet initialized.
    """
    global _global_cache

    # If already cached and no new language requested → return cache directly
    if _global_cache is not None and lang is None :
        return _global_cache

    # Initialize fresh locale object with the given (or auto-detected) language.
    # main.py calls init_locale(saved_lang_from_file), which overrides our initial OS detection —
    # this ensures console output matches what user actually selected, not just their system default.
    L = get_locale(lang)
    _global_cache = L
    return _global_cache


# If run directly as a script instead of imported module
if __name__ == "__main__":
    print("Available languages:", ", ".join(get_available_languages()))
