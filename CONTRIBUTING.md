# Contributing

Thanks for wanting to help. This is a short guide to make sure your time isn't wasted.

## Quick start for contributors

```bash
# 1. Fork the repository (Fork button on GitHub)
# 2. Clone your copy
git clone https://github.com/alexveliyar-coder/HF-Downloader.git
cd HF-Downloader

# 3. Create a branch for your task
git checkout -b fix/what-you-are-doing

# 4. Install dependencies and run
python -m pip install -r requirements.txt
python main.py
```

## Where to look in the code

| If you want to fix... | Look in... |
|---|---|
| UI translation | `locales/*.json` |
| Text / button / modal | `site/index.html` (one big file) |
| Download logic | `hf_core_server.py` |
| Entry point / startup / graceful shutdown | `main.py` |
| Update check | `updater.py` |
| Language auto-detection | `locale_loader.py` |
| Logger (WARN/ERROR + token masking) | `logger.py` |

## Code style

- **Code**: Python 3.9+ compatibility. No type-hint fanaticism, but if you write a new function, prefer adding types.
- **Names**: `lower_snake_case` for functions/variables, `UpperCamelCase` for classes. Constants — `UPPER_SNAKE_CASE`.
- **Comments**: explain **why**, not **what**. If the code is obvious, don't comment.
- **Strings**: use `str.format` or f-strings; `%` only for existing localization-aware code.
- **Logging**: for new user-facing messages, add a key to `locales/*.json` (at least `en.json`) and use `L.t("...")`.

## About translations

Every string a user sees must live in `locales/*.json`. Hardcoding in code (in Russian or English) is **not accepted**, except:

- logs (`logger.py`) — they're in English for grep/awk compatibility
- code comments
- URLs / HTTP headers

When you add a new key to `en.json`, **immediately** add it to every other `locales/*.json` file (even as an English placeholder — someone will translate it later).

## Pull Requests

1. **One PR = one logical change**. Don't mix "fixed a bug + renamed variables + updated README" into one PR — it's hard to review.
2. **Describe what changes** in the PR description (the template fills itself in).
3. **Test locally** that `start_windows.bat` / `./start_mac_linux.sh` runs without errors.
4. **If you touched `site/index.html`** — open the UI and make sure:
   - all 12 languages in the dropdown work
   - modals open/close
   - the Journal (📋) button shows the log
5. **CI** will run ruff and JSON validation for you. If it's red, look at the log and fix it.

## Don't do this

- ❌ Change `requirements.txt` without discussion. Every new dependency is about +10 MB to the exe and one more point of failure.
- ❌ Refactor "on the way". If you notice bad code in a nearby file, open a separate PR labeled `(refactor)`.
- ❌ Commit `downloads/`, `.env`, `.tasks.json`, `.lang.txt` — they're in `.gitignore` precisely because they're local.

## Commits

Messages in the style:
- `fix: ...` — bug fix
- `feat: ...` — new feature
- `docs: ...` — documentation only
- `i18n: ...` — translations
- `refactor: ...` — internal changes with no user-facing effect
- `chore: ...` — tooling (CI, .gitignore, scripts)

Examples of good messages:
- `fix: journal modal crashed on language switch with a non-empty log`
- `i18n: added logsClose to de.json`
- `chore: added GitHub Actions workflow for building releases`

## If something is unclear

- Open a [Discussion](../../discussions) (if enabled) or an Issue with the `question` label.
- Don't hesitate to ask — better to ask and do it right than to guess and redo it.

Thanks again for helping 💛
