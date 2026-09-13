# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/), and versioning follows [Semantic Versioning](https://semver.org/).

> How to read: `MAJOR.MINOR.PATCH`. `MAJOR` breaks compatibility, `MINOR` adds features, `PATCH` fixes bugs.

## [Unreleased]

### Planned
- Something still in progress

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

[Unreleased]: https://github.com/alexveliyar-coder/HF-Downloader/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/alexveliyar-coder/HF-Downloader/releases/tag/v1.1.0
[1.0.0]: https://github.com/alexveliyar-coder/HF-Downloader/releases/tag/v1.0.0
