# Curmudgeon privacy policy

Last updated: 28 October 2026. Applies to Curmudgeon 5.2.1 and later, the free, open-source (MIT) review plugin for Claude Code at https://github.com/truerevelationR2D2/curmudgeon.

## What Curmudgeon collects

Nothing, for itself. It has no accounts, no telemetry, no analytics and no tracking, and its author runs no server that it talks to. Everything it makes stays on your computer:

- **Review results** go in the `.critic/` folder of the project you review: findings, quoted lines of your code, screenshots of pages it checked, a run log (with tokens, passwords, keys and cookies masked) and token counts per agent. If your code contains personal data, quoted lines and screenshots can contain it too. The folder is git-ignored, and you can delete it at any time.
- **Restore copies** of files it changes when you ask for fixes are kept in `.critic/restore/`, so a rollback is exact. They are private to you and never read by any report.
- **Settings for the optional security database** (the folder you chose, the schedule, the size you signed off on) and the database itself stay in the plugin's data folder and in the folder you picked.

Your conversation with Claude is handled by Claude Code and Anthropic under Anthropic's own terms. Curmudgeon doesn't read Claude's memory or chat history, and doesn't send your conversation anywhere.

## What can leave your computer, and only when you choose it

Curmudgeon makes no network call unless you switch on one of these features:

| Feature | When | What is sent | To whom | Their privacy policy |
|---|---|---|---|---|
| Local security database | Only after you say yes, pick a folder and sign off on the size; then on your chosen schedule | Size requests and downloads of public files. Nothing about your project is sent | OSV.dev bulk files on Google Cloud Storage (`storage.googleapis.com`), and CISA (`www.cisa.gov`) | Google: https://policies.google.com/privacy · CISA: https://www.cisa.gov/privacy-policy |
| Online dependency lookup | Only on a run with `--online` | The names and versions of the packages in your lockfiles | The OSV API (`api.osv.dev`), run by Google | https://policies.google.com/privacy |
| Live website check | Only for a site listed in your project's `.critic/scope.json`, with the host typed again on that run | Ordinary page requests (GET, HEAD and OPTIONS only, up to a request cap), as a browser would make | The site you named | That site's own policy |
| Outside reviewer | Only if you say yes, and only by your own hand | Whatever you copy and paste into another AI yourself. Curmudgeon never contacts another AI | The AI you choose | That service's own policy |

Each of these is described in the README, under "What it runs, reads and sends" and "Security scan".

## Retention

Curmudgeon keeps nothing anywhere but your computer. Files in `.critic/`, the restore copies, the security database and its settings stay until you delete them. Uninstalling the plugin removes its data folder (settings included) unless you choose to keep it; the database in the folder you picked is yours to delete.

## Children

Curmudgeon is a developer tool. It is not intended for people under 18.

## Contact

Questions or concerns: open an issue at https://github.com/truerevelationR2D2/curmudgeon/issues. For a security problem, follow [SECURITY.md](https://github.com/truerevelationR2D2/curmudgeon/blob/main/SECURITY.md) instead, so it can be fixed before it is public.

## Changes

Changes to this policy are made in this file, and the repository's history shows every change. A change to what Curmudgeon sends or where it sends it is noted in the release notes.
