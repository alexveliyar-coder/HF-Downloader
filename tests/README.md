# tests/

Smoke tests for HF Downloader. Run:

```bash
python -m tests.test_smoke
```

Why these exist:
- verify all `locales/*.json` files are valid and consistent
- catch an accidentally committed token / API key
- make sure `site/index.html` hasn't ballooned to an unreasonable size

These are **not** unit tests — they don't check behavior under load, don't mock network calls, etc. For that we'd need pytest + responses/httpx-mock, and when the test suite grows we'll move there.

## Adding a check

1. Write a `def check_xxx():` function — no arguments, prints `OK` or `FAIL`.
2. Add it to the `checks` list in `main()` in `test_smoke.py`.
3. Run it — make sure the new check is green.
4. Open a PR.

## What we don't need

- ❌ A pytest fixture for every little thing — this is a small project.
- ❌ UI tests for `site/index.html` — that would need Selenium / Playwright, overkill.
- ❌ Mock tests for `requests` — we have one call site and it's inherently integration-style.
