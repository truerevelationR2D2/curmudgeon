# Curmudgeon

**Prove it. Then I'll grumble.**

Curmudgeon is a review plugin for Claude Code. It reviews code, interfaces, documents and plans the way a grumpy senior engineer would, but it has to show its work: every finding needs a quoted line, a failing case and a vote, and every finding is checked again by someone who didn't write it.

Most AI reviewers fail in one of two ways. They miss real bugs, or they bury them under confident false alarms. Curmudgeon is built against the second failure. A finding survives only if it makes it through the steps below:

1. Three reviewers work **blind**. Each is told the code came from an unknown contractor, sees the files in a different order, and never sees the other reviewers.
2. A **Python script** does the counting. A model never does.
3. Each surviving finding is checked again by a **blind verifier**. The verifier starts from "this is not a defect" and must reproduce or trace the failure. It may lower an impact, but never raise one.
4. False alarms are **measured** with decoys (code that looks wrong but isn't) and clean twins (the same app without the planted bugs). It isn't just a promise.

## Install

```
/plugin install curmudgeon --marketplace truerevelationR2D2/curmudgeon
```

On Claude Code older than 2.1.275, do it in two steps:

```
/plugin marketplace add truerevelationR2D2/curmudgeon
/plugin install curmudgeon@curmudgeon
```

You need Python 3.9 or later. The browser checks also need Playwright with Chromium (`pip install playwright && playwright install chromium`). Without Playwright, those checks are reported as blocked rather than skipped silently.

## Commands

| Command | What it does |
|---|---|
| `/curmudgeon:review [what]` | Reviews and changes nothing. Writes `.critic/last-review.md`. |
| `/curmudgeon:review fix [what]` | Reviews, then fixes. Each fix must pass a re-check before it counts. |
| `/curmudgeon:review deep [what]` | Forces the full three-reviewer run, whatever the size of the change. |
| `/curmudgeon:patch [id]` | Fixes one finding. |
| `/curmudgeon:iterate [part]` | Goes deeper on one part, or tries another approach. |
| `/curmudgeon:approve` | Keeps the last refactor. |
| `/curmudgeon:rollback` | Undoes the last refactor from its restore point. |
| `/curmudgeon:gate on\|async\|off` | Turns the optional stop gate on or off. When it's on, the session can't finish while reviewed files have changed since the last review, or while Critical or High findings are still open. |

You can also just say "tear this apart" or "review my work".

## How a review runs

1. **Size it.** A script sets the tier from what changed and how sensitive it is:
   - trivial: one reviewer;
   - lite: one reviewer, plus verification of Critical and High findings;
   - full: three blind reviewers and full verification.
   The same script lists what calls the changed code.
2. **Detector.** Free scripted checks run, all written for this plugin. They cover:
   - secrets;
   - HTML validity;
   - import cycles and dead code;
   - injection sinks;
   - WCAG 2.2 rules;
   - dependency hygiene;
   - in a real browser: keyboard reach, focus hidden behind other content, a screen-reader view, reflow at 320 px, speed, and dead controls.
3. **Three blind reviewers**, as described above.
4. **The count.** The script drops any finding whose quoted code isn't at the cited line. It keeps findings that two of three reviewers agree on, or that come with an executed failing case. A dedup step merges the same issue worded differently, so votes count issues, not phrasings.
5. **Blind verification**, one finding at a time.
6. **The teardown.** Counts are copied from the script. Every finding carries a confidence. The teardown always ends with "Not checked" and "Not reviewed" lines, so you know what *wasn't* looked at.
7. **Fixes** (only when you ask). A fix must earn three claims: it fixes the target, adds no new defect, and keeps working behaviour working. The third round only verifies.

Results build up in a per-project ledger (`.critic/`):
- findings keep stable ids across runs, so you can see what's new, already known or regressed;
- false alarms you dismiss teach the next run, but never for Critical or High findings;
- the ledger tracks how many findings you actually acted on.

## What it runs, reads and sends

- **Runs:** its own Python scripts, plus your project's test command if you opt in to mutation testing (the command is set in `.critic/rules.md`). In the browser checks it serves your files on `127.0.0.1` and blocks any request that leaves that origin. It never clicks a control that submits a form or sends data.
- **Reads:** the files under review, and your CI's SARIF or JUnit output if present. It never reads its own earlier output as evidence.
- **Writes:** only inside `.critic/`, unless you ask for fixes. Before a fix it saves exact copies of the files it will change in `.critic/restore/` (private to you, git-ignored, never read by any report), so rollback is exact. If your code holds keys, so do those copies. A guard hook blocks direct edits to `.critic/` state.
- **Sends:** nothing, by default. It declares no connectors or MCP servers. Two opt-in flags reach the network: `--online` sends package names and versions to the free OSV vulnerability API (`api.osv.dev`), and `--allow-live` lets the page check load a live URL you give it. Without them, the page checks serve files only on this computer and block any request that would leave it. Secrets found in your code are redacted in every report.
- **Personal data:** Curmudgeon collects, stores and sends no personal data for itself: no accounts, tracking or analytics. If the code you review contains personal data, the quoted lines, screenshots and restore copies it keeps in your local `.critic/` folder can include it. That folder stays on your machine.
- **Hooks:**
  - Stop: the optional gate, off until you turn it on;
  - SubagentStop: checks that each reviewer's output follows the contract;
  - PreToolUse: protects `.critic/` state.

## Benchmarks

Measured on 18 October 2026 with the eval kit in `eval/`. Each review used three blind reviewers. An independent model labelled every finding that didn't match a planted bug; it read and ran the code without seeing the answer keys.

| Test | Planted bugs found | Share of findings that are real bugs |
|---|---|---|
| Notes app (16 planted bugs), review and fix | 16/16 | 96% |
| Orders dashboard (27 planted bugs) | 27/27 | 95% |
| Decoy app (9 decoys that look buggy but aren't, 2 real bugs) | 2/2 | No decoy flagged at Medium or above; 3 flagged at Low |
| Clean twin of the notes app | – | 0 false alarms; both findings were real bugs nobody planted |
| Clean twin of the dashboard | – | 1 trivial finding; the other 7 were real bugs nobody planted |

After the fix stage, the fixed apps passed 9 of 9 and 12 of 13 browser behaviour tests. The miss was an animation that ignores the reduced-motion setting.

These are small apps, so treat the numbers as indicative. Most of the noise left is in Low findings: true, but not worth anyone's time.

Curmudgeon also reviewed its own code. A fresh reviewer then checked each round of fixes, five rounds in all. The rounds turned up real bugs in its own scripts (two of them Critical), and each now has a regression test.

The fixtures, answer keys, decoys and scorer are in `eval/` (see `eval/README.md`). Run them yourself, and report runs where Curmudgeon was wrong. Those are the most useful reports there are.

## Credits and licence

MIT licence; see `LICENSE`. All code here is original. Some checks were inspired by open-source tools, and none of their code or rule text was copied. The tool that inspired each check is named in that script's header: gitleaks, Nu Html Checker, dependency-cruiser, knip, jscpd, ESLint, no-unsanitized, Stylelint, Bandit, OSV-Scanner, Stryker and axe-core. axe-core is used only if it is already installed, and is never bundled.

Contributions are welcome; see `CONTRIBUTING.md`.
