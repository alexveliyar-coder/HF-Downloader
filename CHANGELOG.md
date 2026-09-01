# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/), and versioning follows [Semantic Versioning](https://semver.org/).

> How to read: `MAJOR.MINOR.PATCH`. `MAJOR` breaks compatibility, `MINOR` adds features, `PATCH` fixes bugs.

## [Unreleased]

### Planned
- Something still in progress

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

[Unreleased]: https://github.com/alexveliyar-coder/HF-Downloader/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/alexveliyar-coder/HF-Downloader/releases/tag/v1.0.0
