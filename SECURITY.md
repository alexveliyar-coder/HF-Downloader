# Security

## What we do to protect your data

HF Downloader is designed so that nothing important leaks:

- **Servers listen only on `127.0.0.1`** — they cannot be reached from the internet or your local network. Only you, on your own machine.
- **Hugging Face token** is sent over HTTPS to `huggingface.co` by the local download core — no third-party server of ours ever sees it. The app never writes it to its state: it is stripped from `.tasks.json` (and removed from download URLs) and masked in the log. The UI keeps it in the webview's `localStorage` so you don't have to retype it, which means it *is* stored on your machine, inside the webview profile — turn the token switch off (or clear the field) to drop that copy.
- **CivitAI API token** is sent over HTTPS to `civitai.com` or `civitai.red` the same way: it is never written to the app's state files and is masked in the log. The token is required for all CivitAI downloads.
- **Local cache** (`downloads/`, `.tasks.json`, `.lang.txt`, `.last_dir.txt`, `.last_auto_root.txt`, `.last_auto_roots.json`, `.history.json`, `.hfdl_log.txt`, `hfdl_bookmarks.json`) sits next to the app and is accessible only to you.
- **The local web server serves only the app page** (`site/index.html`). Every other path — including the state files above and `downloads/**` — answers `404`, so nothing in the project folder is reachable over HTTP.
- **Downloaded files** go to the folder you choose (by default `downloads/<the folder you chose>/`) and never leave your computer.

## What we do **not** do

- No telemetry.
- No inbound open ports.
- We never run downloaded files, unpack archives, or execute scripts.
- We never touch your disk except (a) the download folder you pick, and (b) the app's own state files next to the app (`.tasks.json`, `.lang.txt`, `.last_dir.txt`, `.last_auto_root.txt`, `.last_auto_roots.json`, `.history.json`, `.hfdl_log.txt`, `hfdl_bookmarks.json`). Nothing else is modified.
- We never expose those state files over HTTP: the local web server answers only the app page and returns `404` for everything else.

## Reporting a vulnerability

Found a security hole? **Do not open a public issue** — a vulnerability description could be used by attackers before a patch ships.

Instead, contact the maintainer directly:
- **Email**: `security@your-domain.example` (if not set up yet, check the maintainer's GitHub profile)
- **Or** via GitHub: [Security → Advisories → New draft security advisory](https://github.com/alexveliyar-coder/HF-Downloader/security/advisories/new)

We aim to respond within **72 hours**. We don't promise a specific fix timeline in advance — it depends on severity.

### What to include in a report

1. **Description**: what exactly is wrong, which files/lines, how to reproduce it.
2. **Impact**: what an attacker could do (token leak? code execution? denial of service?).
3. **Environment**: HF Downloader version, OS, launch method (exe / from source).
4. **Proof-of-concept**: a minimal scenario, or a screenshot/log.

### Out of scope

- Vulnerabilities in **dependencies** (`requests`, `pywebview`) — report them upstream, not to us.
- Vulnerabilities in **Hugging Face itself** — that's not our project.
- Vulnerabilities in **CivitAI itself** — report them to CivitAI directly.
- Theoretical attacks that require physical access to an unlocked machine.

## Thanks

If you found and responsibly disclosed a vulnerability — thank you. Your name will appear in [CHANGELOG.md](./CHANGELOG.md) unless you ask us not to.
