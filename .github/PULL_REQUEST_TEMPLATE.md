# What changes

<!-- Short PR description in 1-3 sentences. Link to the issue: Fixes #123 -->


## Type of change

- [ ] 🐛 Bug fix (does not break existing behavior)
- [ ] ✨ New feature (adds capabilities)
- [ ] 💥 Breaking change (breaks compatibility — describe in detail)
- [ ] 📝 Documentation only
- [ ] 🌐 Translation
- [ ] 🔧 Internal / refactor (no user-facing behavior change)


## How to test

<!-- Step by step: what to do to reproduce / see the effect. -->


## Checklist

- [ ] Code is readable (comments explain _why_, not _what_)
- [ ] Ran `start_windows.bat` / `./start_mac_linux.sh` locally — works
- [ ] If I touched `site/index.html` — checked in all 12 languages (at least EN and one non-EN)
- [ ] If I touched `locales/*.json` — all files are valid (`python -c "import json; json.load(open('...'))"`)
- [ ] If I changed `updater.VERSION` — updated `CHANGELOG.md` and wrote down what changed
- [ ] If I added a dependency — updated `requirements.txt` and `pyproject.toml`
