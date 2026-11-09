---
name: check-updates
description: Checks whether a newer Curmudgeon is on GitHub. Runs only when the user types /curmudgeon:check-updates.
disable-model-invocation: true
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/review/scripts/check_updates.py"` (on Windows, `py -3` when `python3` isn't there) and show the user what it prints, word for word. It makes one request to GitHub for the latest version number, sends nothing about the user or the project, and downloads or installs nothing. Never update, download or install anything yourself: if an update is available, the output says how the user can do it.
