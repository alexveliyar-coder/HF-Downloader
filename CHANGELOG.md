# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/), and versioning follows [Semantic Versioning](https://semver.org/).

> How to read: `MAJOR.MINOR.PATCH`. `MAJOR` breaks compatibility, `MINOR` adds features, `PATCH` fixes bugs.

## [Unreleased]

## [1.2.0] — 2026-10-19

### Added
- **Readable file names for downloaded models**: the file name gets a prefix built from the source metadata — `{Model}-v{Version}-{base}-{type}-{fp}` for CivitAI (`DreamShaper-v8-sd15-checkpoint-fp16_dreamshaper_8.safetensors`) and `{owner}-{Repo}-[{branch}-]{type}` for Hugging Face. It fixes the usual "who is this and what is it for" problem with names like `diffusion_pytorch_model.safetensors`.
- **Auto-sorting into folders** (new switch in the UI): single files go to a ComfyUI-compatible subfolder by model type — `checkpoints`, `loras`, `vae`, `text_encoders`, `controlnet`, `embeddings`, `upscale_models`, `hypernetworks`, `poses`, `other`. Types come from CivitAI `model.type` or from HF tags / `pipeline_tag` / diffusers `config` class, with a file-name fallback; something that cannot be identified honestly lands in `other` instead of a random folder.
- **Bookmark-first routing**: with auto-sort on, a file first looks for a matching folder among your bookmarks (silent mode — first folder-name match wins: `D:/Models/loras`, `E:/ComfyUI/models/text_encoder`, …), otherwise it falls back to a subfolder under the chosen path. Saved tasks keep the resolved folder (`dir`), so a retry never moves a file after a bookmark reorder; the card shows where it really went.
- **File-name prefix switch** (on by default): prepends a metadata prefix (`{Model}-v{Version}-{base}-{type}` for CivitAI, `{owner}-{Repo}-{type}` for HF). Off = file name stays exactly as hosted; the manual prefix field is ignored. Independent from the folder switch.
- **Pinned bookmark wins**: if the path field matches one of your bookmarks, the file goes straight there (`dir_source=pinned`) — no auto-search, no surprises.
- **"Unsorted" quarantine instead of a second list**: files whose type was not recognized (`other`, auto-sort on, no bookmark/pinned hit) keep downloading into `.../other` but are marked with a "needs folder" tag and a filter button with a counter in the task header — a computed flag, no new state or `.tasks.json` migration.
- Optional manual **file name prefix** field (empty = built automatically from the metadata).
- New `src/model_naming.py` — pure, network-free naming/classification logic, covered by `tests/test_smoke.py` (`python -m tests.test_smoke`).
- New HF metadata fetch (`/api/models/{repo}`) used for type detection; network failures never break a download (metadata is best-effort).
- **Download history with paths** (`.history.json` + the new “Downloaded” tab in the journal): every finished/failed task is recorded with its folder and the real file path on disk, so you can still tell where a model went after a restart — `.tasks.json` keeps only unfinished tasks. Served by `GET /api/history`, cleared by `POST /api/history/clear`; tokens are never written there.
- **The auto-layout roots list is now stored on disk** (`.last_auto_roots.json`, `GET/POST /api/last_auto_roots`): the whole ordered list of roots survives a wiped `localStorage` (WebView2 profile reset) instead of degrading to the single active root.
- New smoke checks: `check_auto_roots_list_persistence()`, `check_download_history()`, `check_no_dead_code_after_raise()` (the last one scans the AST for statements after `raise` — exactly how the progress reporting bug stayed invisible) and `check_ui_init_order()` (UI state must be declared before the init block; otherwise `applyLang()` aborts the init chain and the clipboard watcher never starts).

### Fixed
- **Download progress was never reported** — the card stayed at `0 B / 0 %`, with no speed and no ETA, and `.tasks.json` saved zeros (the file itself downloaded fine; a 2 GB `.part` was found on disk while the UI showed nothing). The whole progress block (speed calculation, speed limit, `downloaded` / `total` counters) sat in the `elif` branch of the stall watchdog *after* `raise`, which Python silently treats as unreachable code. The watchdog branch now stands after the progress block.
- **The speed limit never worked** — same unreachable block: `window_bytes` was never counted, so the limiter never slept. Covered by a regression step in `check_download_integrity()`.
- **The active auto-layout root is always the first root**: if you typed a root into the field without pressing the “+” chip, the task fell back to the classic routing (pinned > bookmarks-by-type > base/type) and could land in a bookmark folder instead of `root/type`. Now `_effective_auto_roots()` (mirrored in the frontend `autoFlags()`) puts the active root first.
- **The chosen auto-layout root was being overridden** - the resolver looked for "the first root that already has a subfolder for this type" and *skipped the active root* whenever that subfolder did not exist yet, so files landed in a different root than the one you picked. Real case: root `...\ComfyUI\models\test_download` was chosen, but `loras` already existed under `...\ComfyUI\models`, so the file went to `models\loras` (`dir_source: auto-root-hit`). The active root now always wins; the remaining roots are fallbacks used only when it is unavailable (missing drive / permissions), and `auto-root-hit` now means exactly that.
- **Half the UI was untranslated in 10 of 12 languages** - the in-page dictionaries `T` and
  `I18N_EXTRA` gained features over time only for RU/EN, so the rest fell back to English:
  the whole CivitAI block for PT/UR/DE/JA, and auto-layout, file-name prefix, the «Unsorted»
  filter, clear-all and the «Downloaded» tab for every non-RU/EN language. All dictionaries now
  have the same key set in all 12 languages, and every previously missing string is
  translated (DE, FR, ES, PT, ZH, JA, HI, AR, BN, UR).
- **A label had a stray leading space** - the Urdu «Folder» caption rendered as ` Folder` with
  a space in front (`T.UR.folder`); the label now starts at the word itself.
- **Three tooltips stayed Russian in every language** - the journal button, the paste-token
  button and the auto-layout root placeholder were hardcoded in the markup and never
  reassigned by `applyLang()`.
- **Resume restarted the progress bar from zero** — the counter subtracted the
  already-downloaded prefix (`downloaded - start`), so after any network retry, app
  restart or «Continue» the card showed ~0 % and climbed again, while the `.part`
  file kept growing normally. Measured live: 5.30 GB on disk vs 2.05 GB in the UI —
  exactly the 3.25 GB prefix. The byte count on disk is now reported as is, and a
  resumed task shows its real size before the first chunk arrives. Regression steps 7-8
  in `check_download_integrity()`.
- **Download history had an empty task id** — `id` lives as a *key* in the task map and
  never inside the task dict, so every row in «Downloaded» was written with `id: ""`.
  `run_task()` now seeds it (`st.setdefault("id", tid)`), which leaves ids restored from
  `.tasks.json` untouched.
- **Switching the language did not refresh the token row, confirm dialog or support texts** —
  `applyLang()` never touched the token label/note (they are owned by `updateUIForSource()` and
  only follow the active source tab), so the token row kept the previous language until reload.
  `applyLang()` now re-renders the token labels for the current source, redraws an open confirm
  dialog, and updates the support-modal texts when present.
- **Three buffer/branch strings stayed English in every language** — the «BUFFER» caption had no
  id and was never translated, the subfolder input placeholder (`subfolder (opt)`) and the
  `branch:` label in the link-preview line were hardcoded JS literals. All three now go through
  `tr()` with translations in all 12 languages, and the resume-without-token toast gained the
  previously-missing `tokMissing` key in every language (it used to fall back to English).

### Notes
- Repository downloads (`kind=repo`, e.g. diffusers repos) are intentionally **not** renamed or moved: their folder structure (`vae/`, `text_encoder/`, `unet/`) must stay intact.
- Files downloaded before this change keep their old names; a new download of the same model is stored under the new prefixed name.

## [1.1.0] — 2026-09-13

### Added
- **CivitAI (Blue & Red)** as a second download source: `civitai.com` / `civitai.red` models, version-specific links (`?modelVersionId=`), URN links (`urn:...:civitai:{modelId}@{versionId}+{fileId}`) and direct `/api/download/models/{id}` links.
- New `src/civitai_client.py` — CivitAI API client that resolves the real download URL, picks the right file and handles token auth.
- Clear CivitAI errors: 401 (invalid/missing token), 402 (paid / early access), 403 (gated), 404 (not found) — instead of a generic network error.
- Tasks without a CivitAI token are paused with "token required" and resume in place once the token is entered — no more lost tasks.
- UI: source tabs (HF / CivitAI Blue / CivitAI Red), "paste token from clipboard" button, live token sanitization.
- Auto-install of missing Python dependencies on first run.
- Periodic task-state autosave (every 5 seconds) — downloads survive a hard crash or power loss.

### Fixed
- URN links could fail with `InvalidSchema` after restoring old saved tasks — the source is now re-detected from the link and a raw URN never reaches the download engine.
- Resume on shutdown: `.part` files are kept (exit is a pause, not a cancel) and task state is saved before worker threads stop — the queue is no longer lost.
- Large files could hit `MemoryError` — download chunk reduced from 4 MB to 1 MB.
- Network vs HTTP errors: only network errors are retried (with backoff); 4xx/5xx surface immediately with a clear message.
- Rate limits on repo downloads: 0.5 s pause between files.
- Already-downloaded CivitAI files are skipped by declared size (no HEAD probe — the CDN replies 403 to HEAD).

### Security
- Tokens are masked in `.hfdl_log.txt`, including tokens passed in `?token=` query strings.
- Tokens are stripped from task state (`.tasks.json`) — credentials are never written to disk in plain text.
- The page server no longer serves the project folder: it answers only `site/index.html` and returns `404` for every other path, so `.env`, `.tasks.json`, `.last_dir.txt`, `.last_auto_root.txt`, `.hfdl_log.txt`, `hfdl_bookmarks.json`, `src/*.py` and `downloads/**` are unreachable over HTTP. Previously the static root was the process cwd (= the project folder when launched by `start_windows.bat`), which combined with DNS rebinding could leak a real token from `.env`.
- The core no longer treats a missing `Origin` header as permission: a request without `Origin` but with a foreign `Referer` is rejected with `403`. Browsers do not send `Origin` for `no-cors` GET subresources (`<img>`, `<script>`, `<link>`), so a third-party page could previously hit GET endpoints (only a `Referer` check closes that hole).
- `/api/logs/clear` and `/api/lang` are POST-only — as GETs they were CSRF-reachable from any site. This also fixes the journal's "Clear" button, which called `POST /api/logs/clear` while the core only had the GET variant.
- Docs honesty: `SECURITY.md` no longer claims the token is never stored (the UI keeps it in the webview's `localStorage`) and no longer claims nothing outside `downloads/` is touched (the app also writes its own state files next to the app). `.env.example` now states that `.env` is not read by the current version.

## [1.0.0] — 2026-09-01

### Added
- First public release.
- Download models / datasets / spaces from Hugging Face (single files and whole repos).
- Pause / resume with HTTP Range headers (resume after a crash).
- Task queue with a strict one-at-a-time mode.
- Bookmarks for frequently downloaded repos.
- Automatic clipboard link pickup (with user permission).
- Local event journal (WARN/ERROR) with filter and copy-to-clipboard.
- 12 UI languages: en, zh, hi, es, fr, ar, bn, pt, ru, ur, de, ja.
- Update check via GitHub Releases (notification only, no auto-download).
- Windows / macOS / Linux builds via GitHub Actions (tag `vX.Y.Z` → release).

### Fixed
- The journal modal could get "stuck" on the old language when switching languages with entries in the log — `renderLogs` overwrote `logsEmpty` via `innerHTML`, and `applyLang` crashed with `TypeError: Cannot set properties of null`. Now `renderLogs` only removes `.log-entry`, leaving the empty-state placeholder in the DOM. Bonus: log entries are rendered via `createElement` + `textContent` instead of HTML concatenation (XSS-safe).

### Security
- Masked HF tokens, Authorization headers, and repository names in `.hfdl_log.txt`.

---

## Template for future releases

```markdown
## [X.Y.Z] — YYYY-MM-DD

### Added
- New feature.

### Changed
- Changed behavior of an existing feature.

### Fixed
- Something fixed.

### Removed
- Something removed (deprecated).

### Security
- Something security-related.
```

[Unreleased]: https://github.com/alexveliyar-coder/HF-Downloader/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/alexveliyar-coder/HF-Downloader/releases/tag/v1.2.0
[1.1.0]: https://github.com/alexveliyar-coder/HF-Downloader/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/alexveliyar-coder/HF-Downloader/releases/tag/v1.0.0
