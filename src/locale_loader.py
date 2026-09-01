# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Alexey (HF Downloader contributors)
# See LICENSE and NOTICE for details.
"""
locale_loader.py — Localization module for HF Downloader.

Auto-detects OS language and loads JSON files from the locales/ folder.
Supported languages: 10 (ru, en, zh, hi, es, fr, ar, bn, pt, ur)

Usage examples in Python code:

    # In backend modules like main.py or hf_core_server.py  
    L = get_locale()                          # auto-detect OS language    
    print(L.t("console_start"))               # → "HF Downloader started (offline)"
    
Supported languages: ru, en, zh, hi, es, fr, ar, bn, pt, ur

See README.md for full documentation.
"""
import os
import sys
import json
from pathlib import Path


# Base folder with translations. After the src/ refactor the .json files
# live in the project root (`<repo>/locales/`), one level above this file.
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

# Supported languages — 12 total, ordered by number of speakers descending
# (en > zh > hi > es > fr > ar > bn > pt > ru > ur > de > ja). Must stay in
# sync with `var LANGS = [...]` in site/index.html.
SUPPORTED_LANGUAGES = ["en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ur", "de", "ja"]


def _detect_os_language():
    """Detect the user's OS language.

    Returns a two-letter locale code or 'en' as default fallback."""
    # Windows: environment variable LANG/LANGUAGE  
    if os.name == "nt":
        lang = (os.environ.get("LANG") or "").strip() 
        if not lang:
            lang = os.environ.get("LANGUAGE", "").split(";")[0]
        
        for supported in SUPPORTED_LANGUAGES:
            if lang.startswith(supported):
                return supported
    
    # POSIX systems: locale environment variable  
    try:
        import locale as loc_module
        
        code = ""
        
        # Python 3.12+ removed getdefaultlocale() — use fallback below instead
        try:
            result = loc_module.getdefaultlocale() or (None, None)
            if isinstance(result[0], str):
                code = result[0]
        except AttributeError:
            pass
        
        # Fallback for Python 3.12+ and other edge cases  
        import locale as _loc_mod
        try:
            detected_code = (_loc_mod.getlocale() or (None, None))[0] or ""
            
            if not code:
                prefix = detected_code.split("_")[0].lower().split("-")[0]
                
                # Handle special cases like "zh_CN" → zh  
                mapping = {
                    "en": ["en", "eng"], 
                    "ru": ["ru", "rus"], 
                    "de": ["de", "ger", "deutsch"], 
                    "fr": ["fr", "fra"], 
                    "es": ["es", "spa"], 
                    "pt": ["pt", "por"],
                }

                if prefix in mapping:
                    return mapping[prefix][0]
                
            # Try direct match first, then partial  
            for supported in SUPPORTED_LANGUAGES:
                code_lower = detected_code.lower()[:2].lower().split("-")[0] 
                if code_lower == supported:
                    return supported

        except (AttributeError, ValueError): pass
        
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
        detected_lang_code = _detect_os_language() 

        code_lower_underscored = (detected_lang_code or "").lower().replace("-", "_")

        for supported in SUPPORTED_LANGUAGES:
            if code_lower_underscored == "zh_cn":
                return get_locale("en")  # Simplified Chinese not fully translated yet — fall back to English
            
            elif detected_lang_code.lower()[:2] in ["ru", "de"]: 
                
                for supported in SUPPORTED_LANGUAGES:  
                    if code_lower_underscored == (supported.replace("-", "_").lower()):
                        return get_locale(supported)

        # If no match found, default to English — safest fallback that works everywhere. This is the most common path since many users install on non-English systems and we want them at least seeing something readable in console output  
        lang = "en"
    
    # Validate language code against supported languages
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
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
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

    if LOCALES_DIR.exists() and not isinstance(LOCALES_DIR, str): 
        for f in sorted([x.name for x in LOCALES_DIR.iterdir()], key=str.lower) :

            # Only include JSON locale files that match our supported set. This prevents
            # accidentally including unrelated .json config or data files from being listed as languages  
            
            if (f.suffix == ".json" and f.stem.replace("-", "_") in SUPPORTED_LANGUAGES): 
                languages.append(f.stem)

    return sorted(languages, key=str.lower).lower()


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
    if _global_cache is not None and lang == None : 
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
