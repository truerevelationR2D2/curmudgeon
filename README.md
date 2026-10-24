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
   - Python safety, read with Python's own parser, so strings and comments don't trigger false alarms;
   - WCAG 2.2 rules;
   - dependency hygiene and licences (strong copyleft such as GPL is flagged; missing, unrecognised and proprietary licences are noted);
   - your own rule files (see "Add your own checks");
   - in a real browser: keyboard reach, focus hidden behind other content, a screen-reader view, reflow at 320 px, speed, and dead controls.
3. **Three blind reviewers**, as described above.
4. **The count.** The script drops any finding whose quoted code isn't at the cited line. It keeps findings that two of three reviewers agree on, or that come with an executed failing case. A dedup step merges the same issue worded differently, so votes count issues, not phrasings.
   **Optional outside reviewer.** Reviewers from one model family share blind spots. In two double-blind tests, another AI's review and Curmudgeon's own overlapped on none of 23 real findings the first time and 2 of 14 the second ([details](docs/double-blind-test.md)). So Curmudgeon asks once whether you want an outside reviewer; the default is no. If you say yes, it writes a brief for that change, with the commit, raw file links and an output format, and none of its own findings. You paste the brief into another AI yourself, then paste the answer back. Those findings get the same quote check as Curmudgeon's own. Where one agrees with Curmudgeon's reviewers, it counts as one more vote. One only the outside AI raised always goes to blind verification, and a run Curmudgeon can't see never counts as proof.
5. **Blind verification**, one finding at a time.
6. **The teardown.** Counts are copied from the script. Every finding carries a confidence. The teardown always ends with "Not checked" and "Not reviewed" lines, so you know what *wasn't* looked at.
7. **Fixes** (only when you ask). A fix must earn three claims: it fixes the target, adds no new defect, and keeps working behaviour working. The third round only verifies.

Results build up in a per-project ledger (`.critic/`):
- findings keep stable ids across runs, so you can see what's new, already known or regressed;
- **memory that never hides anything:** when you dismiss three similar findings for the same reason, Curmudgeon remembers. In later reviews, a look-alike finding is still shown and still counted, with a note naming your earlier reason, so you can decide in seconds. `critic_ledger.py dismiss --like N "why"` closes them on purpose. Memories only note Medium and Low findings (never High or Critical), `dismiss --like` only closes open ones, the verifier never sees notes, and they expire after 90 days unused;
- **spot-checks:** after a review it can show you three random findings and one of the verifier's refutations to judge (real, wrong or unsure). Your answers give a precision figure from your own projects, and show whether the verifier ever drops a real bug or lowers one's impact (counted separately). Every refutation and downgrade is kept in `.critic/refutations.jsonl`;
- the ledger tracks how many findings you actually acted on.

## Add your own checks

Drop a JSON file of rules into your project's `.critic/rules/` (or, to contribute one for everyone, into `plugin/skills/review/rules/`). Each rule is an id, a severity, an area, a regular expression matched line by line, a message, and optional file patterns; see `plugin/skills/review/rules/README.md`. Rules are data, never code, and their rows are reported as `rule-<id>`, so they can't pose as built-in checks. A project's rule files must be plain files (at most 256 KB each, 50 files and 2,000 rules in all); they run in a separate process with a 20-second limit and at most 50 matches per rule, and they can warn but never fail, so a slow, greedy or hostile rule file can't hang a review or flood it with findings. The background stop check skips them.

## What it runs, reads and sends

- **Runs:** its own Python scripts, plus a test command if you opt in to mutation testing: one you type with `--test-cmd`, or the one in `.critic/rules.md` only when you also pass `--project-checks` (a cloned repository can ship its own rules.md, so Curmudgeon shows you its commands and asks first). Every script a review starts and every outside command or network call it starts itself (git, npm, a Chromium launch, your test or check commands when asked, the opt-in OSV lookup) is listed in `.critic/runlog.jsonl`. The requests a page makes inside the browser aren't listed one by one. Tokens, passwords, keys, cookies and signed-URL signatures are masked. The log is git-ignored, and if your repository already tracks it, nothing is written to it and you're told why. In the browser checks it serves your files on `127.0.0.1` and blocks any request that leaves that origin. It never clicks a control that submits a form or sends data.
- **Reads:** the files under review, and your CI's SARIF or JUnit output if present. It never reads its own earlier output as evidence.
- **Writes:** only inside `.critic/`, unless you ask for fixes. Before a fix it saves exact copies of the files it will change in `.critic/restore/` (private to you, git-ignored, never read by any report), so rollback is exact. If your code holds keys, so do those copies. A guard hook blocks direct edits to `.critic/` state. Each run moves the last run's raw reviews to `.critic/history/`, so they are never counted again. The raw reviews and other files that hold reviewers' exact quotes are git-ignored; everything Curmudgeon writes itself has secrets masked.
- **Sends:** nothing, by default. It declares no connectors or MCP servers, and it never contacts another AI: the outside reviewer is something you paste to and from yourself, only if you said yes. Two opt-in flags reach the network: `--online` sends package names and versions to the free OSV vulnerability API (`api.osv.dev`), and `--allow-live` lets the page check load a live URL you give it. Without them, the page checks serve files only on this computer and block any request that would leave it. Secrets found in your code are redacted in every report.
- **Personal data:** Curmudgeon collects, stores and sends no personal data for itself: no accounts, tracking or analytics. If the code you review contains personal data, the quoted lines, screenshots and restore copies it keeps in your local `.critic/` folder can include it. That folder stays on your machine.
- **Limits:**
  - Restore copies are exact, so they keep a key that a fix removed until you delete them.
  - On Windows the copies' private folder permission (0700) has no effect.
  - `.gitignore` doesn't stop a Docker build context, a zip or a sync tool from picking up `.critic/`.
  - Ignore rules don't cover files already committed. If an earlier version let you commit `.critic/` review or ledger files, remove them from git with `git rm --cached` (Curmudgeon warns when it sees tracked ones).
  - The verifier's "no hedging" rule is a word list: it stops "probably" or "seems", but not a confident, wrong refutation that cites a real line. Spot-checks (above) are how you catch those.
- **Hooks:**
  - Stop: the optional gate, off until you turn it on;
  - Stop, background re-scan: free scripted checks on files edited since the last review, in one scan with a 5-minute limit, run without blocking, off until you turn it on with `/curmudgeon:gate async`;
  - SubagentStop: checks that each reviewer's and verifier's output follows the contract (it runs only for those two agents);
  - PreToolUse: protects `.critic/` state.

## Benchmarks

Measured on 18 October 2026 (version 4.0.0) with the eval kit in `eval/`. The notes app was a single-context review and fix; the orders dashboard used three blind reviewers. The release record doesn't say how many reviewers the decoy-app and clean-twin runs used. An independent model labelled every finding that didn't match a planted bug; it read and ran the code without seeing the answer keys. All numbers are as recorded in `eval/baseline.json`.

| Test | Planted bugs found | Share of findings that are real bugs | Report format score |
|---|---|---|---|
| Notes app (16 planted bugs), review and fix | 16/16 | 96% (27 of 28) | 100% |
| Orders dashboard (27 planted bugs) | 27/27 | 95% (35 of 37) | 45% |
| Decoy app (9 decoys that look buggy but aren't, 2 real bugs) | 2/2 | 30%: no decoy flagged at Medium or above; 3 decoys and several true-but-trivial nitpicks flagged at Low | 45% |
| Clean twin of the notes app | – | 0 false alarms; both findings were real bugs nobody planted |
| Clean twin of the dashboard | – | 1 trivial finding; the other 7 were real bugs nobody planted |

After the fix stage, the fixed apps passed 9 of 9 and 12 of 13 browser behaviour tests. The miss was an animation that ignores the reduced-motion setting.

The report format score (`contract` in the eval) is the share of checks on how the written teardown follows its required format (11 checks for a review, 14 for a review and fix, which adds the refactoring manifest, the state ledger and the closure table): headers, a single verdict, counts that match the findings, evidence on every finding, and so on. It measures the report's form, not whether the findings are right.

These are small apps, so treat the numbers as indicative: with 28 findings, "96%" could plausibly be anything from about 82% to 99%. Most of the noise left is in Low findings: true, but not worth anyone's time.

Curmudgeon also reviewed its own code. A fresh reviewer then checked each round of fixes, five rounds in all. The rounds turned up real bugs in its own scripts (two of them Critical), and each now has a regression test.

The fixtures, answer keys, decoys and scorer are in `eval/` (see `eval/README.md`). Run them yourself, and report runs where Curmudgeon was wrong. Those are the most useful reports there are.

## Credits and licence

MIT licence; see `LICENSE`. All code here is original. Some checks were inspired by open-source tools, and none of their code or rule text was copied. The tool that inspired each check is named in that script's header: gitleaks, Nu Html Checker, dependency-cruiser, knip, jscpd, ESLint, no-unsanitized, Stylelint, Bandit, OSV-Scanner, Stryker and axe-core. axe-core is used only if it is already installed, and is never bundled.

Contributions are welcome; see `CONTRIBUTING.md`.
