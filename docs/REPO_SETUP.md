# One-Time Repository Setup

Before you push the first commit and make the repo public, replace every `alexveliyar-coder` placeholder with your real GitHub handle (e.g. `veliyar-ensophia`).

The text is the same in every file — `alexveliyar-coder` — so a single global find-and-replace works.

## Files that need the substitution

```
.env.example
CHANGELOG.md
COMMERCIAL_LICENSE.md
NOTICE
pyproject.toml
README.md
SECURITY.md
updater.py
.github/FUNDING.yml
.github/ISSUE_TEMPLATE/license.yml   (if you kept the license template)
```

## Quick PowerShell command

Run this from the project root (`D:\HFdownloader`) after committing nothing else. Adjust `your-handle` to your real GitHub username.

```powershell
$old = 'alexveliyar-coder'
$new = 'your-handle'

Get-ChildItem -LiteralPath . -Recurse -File -ErrorAction SilentlyContinue `
  | Where-Object { $_.FullName -notmatch '\\__pycache__\\' -and $_.FullName -notmatch '\\.git\\' } `
  | ForEach-Object {
      $c = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
      if ($c -and $c.Contains($old)) {
        $c2 = $c.Replace($old, $new)
        Set-Content -LiteralPath $_.FullName -Value $c2 -NoNewline
        Write-Host "updated: $($_.FullName)"
      }
    }
```

Verify with:

```powershell
Get-ChildItem -LiteralPath . -Recurse -File | Select-String 'alexveliyar-coder'
```

You should get no output.

## Notes

- `FUNDING.yml` only needs the replacement if you want the **"Sponsor"** button on your GitHub profile to point to the real repo. The Boosty custom URL stays as `https://boosty.to/veliyar_ensophia` regardless.
- `updater.py` has the same placeholder in the default value of the `REPO` constant. If you don't replace it, the updater will simply fail silently when checking for updates (caught and printed as a warning) — so it's not critical, but the replacement is what makes auto-update work.
- `CHANGELOG.md` has two URLs in the "Unreleased / 1.0.0" compare section. Both should point to the real repo after replacement.

## Other one-time things to check before pushing

- [ ] All `alexveliyar-coder` are replaced (see above)
- [ ] Optional: add a `docs/screenshot.png` so the README image isn't broken
- [ ] Optional: add `build/icon.ico` / `icon.icns` / `icon.png` if you want the PyInstaller builds to have a real app icon
- [ ] Optional: invite a few early users as collaborators to test v1.0.0 before the public release

That's it. Everything else (smoke tests, code, workflows, docs) is already in place and ready to commit.
