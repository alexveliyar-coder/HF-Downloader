# Security

## What we do to protect your data

HF Downloader is designed so that nothing important leaks:

- **Servers listen only on `127.0.0.1`** — they cannot be reached from the internet or your local network. Only you, on your own machine.
- **Hugging Face token** is sent directly from the browser (or pywebview window) to `huggingface.co` over HTTPS. No intermediate server ever sees or stores it. By default the token is not persisted at all — it lives only in the window's `localStorage` while the app is running.
- **Local cache** (`downloads/`, `.tasks.json`, `.lang.txt`, `.last_dir.txt`) sits next to the app and is accessible only to you.
- **Downloaded files** go to `downloads/<the folder you chose>/` and never leave your computer.

## What we do **not** do

- No telemetry.
- No inbound open ports.
- We never run downloaded files, unpack archives, or execute scripts.
- We never modify files outside `downloads/`.

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
- Theoretical attacks that require physical access to an unlocked machine.

## Thanks

If you found and responsibly disclosed a vulnerability — thank you. Your name will appear in [CHANGELOG.md](./CHANGELOG.md) unless you ask us not to.
