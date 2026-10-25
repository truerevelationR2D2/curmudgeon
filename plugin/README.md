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
| `/curmudgeon:review quiet [what]` | The same review with a shorter teardown: Critical and High in full, Medium and Low one line each. Every count stays exact. |
| `/curmudgeon:review audit [what]` | Audits someone else's system: the full review, changing nothing, with rules of engagement (active tests only on what `.critic/scope.json` lists), stated-versus-inferred requirements, and findings that give difficulty, an exploit scenario and short- and long-term fixes. |
| `/curmudgeon:review security [what]` | The security scan: the same blind panel as the review's size calls for, focused on security only, with the security checks, the browser integrity check and, if you switch it on, the local security feed. See [Security scan](#security-scan). |
| `/curmudgeon:fix patch [id]` | Fixes one finding. |
| `/curmudgeon:fix iterate [part]` | Goes deeper on one part, or tries another approach. |
| `/curmudgeon:fix approve` | Keeps the last refactor. |
| `/curmudgeon:fix rollback` | Undoes the last refactor from its restore point. |
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
   - tests of the tests (Python): tests that check nothing, asserts that can never fail, two tests with one name (one never runs), failures swallowed by a broad `except`, skips with no reason;
   - CI and supply chain: untrusted text pasted into workflow scripts, `pull_request_target` running a PR's own code, always-true `if:`, missing `permissions:`, actions not pinned by SHA (or in `actions.lock`), secrets pasted into scripts, workspace uploads that carry the token (upload-artifact before v4.4, or with hidden files included), `curl | sh`, `--extra-index-url`, unpinned base images, and npm lockfile entries from other hosts or without an integrity hash. Workflows are read with a strict YAML reader written for this plugin; a file it can't read safely is reported as not checked;
   - agent and MCP configuration: committed `enableAllProjectMcpServers`, literal credentials in a server's settings, servers started by downloading and running code or in privileged containers, unpinned `npx`/`uvx` servers, allow rules for a whole server or every command, and the same server defined in two files;
   - release and rollback (PostgreSQL migrations in `.sql` files, Alembic and Django): indexes built without `CONCURRENTLY`, `NOT NULL` columns with no default, constraints validated in place, and migrations that can't be rolled back;
   - requirements and intent: a table of each requirement id (REQ-12, FR-3, US-4 and similar) and the tests that cite it, tests that cite a requirement nobody defined, and requirements no test cites. A finding that rests on an inferred requirement, not a written one, is capped at Medium by the script;
   - operations: secrets passed to log or print calls, DEBUG on in production settings, Prometheus alerts with no runbook or a runbook file that doesn't exist, and (as pedantic notes) Kubernetes containers with no probes or limits;
   - WCAG 2.2 rules;
   - dependency hygiene and licences (strong copyleft such as GPL is flagged; missing, unrecognised and proprietary licences are noted);
   - your own rule files (see "Add your own checks");
   - in a real browser: keyboard reach, focus hidden behind other content, a screen-reader view, reflow at 320 px, speed, and dead controls.
   - a step-by-step browser driver for reviewers and verifiers (`browse.py`): go to, click, type, select, check, press and wait, with the page's controls, console errors, network log and a screenshot after every step. Clicks run on a simulated page: local files are served on 127.0.0.1 by Curmudgeon itself, and a running app or live test site is recorded once (GET only) and then replayed offline, so anything a click tries to send is answered by the simulation and never reaches a real server. That makes even Delete safe to try. With `--expect`, a step returns before-and-after screenshots, the text that changed and what the page tried to send, for the reviewer to compare with what should have happened. Chromium can reach nothing but the page's own origin. Clicks are real mouse clicks, checked as they land. Sending data to your real local server, or recording a live test site listed in `.critic/scope.json`, needs your yes first, asked with a one-line reason;
3. **Three blind reviewers**, as described above. All three are the same model, so their agreement isn't independent the way three people's would be. The decoys, the clean twins and the optional outside reviewer are the defence against blind spots they share.
4. **The count.** The script drops any finding whose quoted code isn't at the cited line. It keeps findings that two of three reviewers agree on, or that come with an executed failing case. A dedup step merges the same issue worded differently, so votes count issues, not phrasings.
   **Optional outside reviewer.** Reviewers from one model family share blind spots. In two double-blind tests, another AI's review and Curmudgeon's own overlapped on none of 23 real findings the first time and 2 of 14 the second ([details](docs/double-blind-test.md)). So Curmudgeon asks once whether you want an outside reviewer; the default is no. If you say yes, it writes a brief for that change, with the commit, raw file links and an output format, and none of its own findings. You paste the brief into another AI yourself, then paste the answer back. Those findings get the same quote check as Curmudgeon's own. Where one agrees with Curmudgeon's reviewers, it counts as one more vote. One only the outside AI raised always goes to blind verification, and a run Curmudgeon can't see never counts as proof.
5. **Blind verification**, one finding at a time. Reviewers and verifiers use Claude Code's `LSP` tool for definitions and references when a code-intelligence plugin makes it work; what it shows still needs a quote. In the full tier, a **variant hunt** then looks for the same pattern as each confirmed Critical or High bug elsewhere in the project; each hit is verified blind too, and only confirmed variants are reported, in their own section.
6. **The teardown.** Counts are copied from the script. Every finding carries a confidence. The teardown always ends with "Not checked" and "Not reviewed" lines, so you know what *wasn't* looked at.
7. **Fixes** (only when you ask). A fix must earn three claims: it fixes the target, adds no new defect, and keeps working behaviour working. The third round only verifies.

Results build up in a per-project ledger (`.critic/`):
- findings keep stable ids across runs, so you can see what's new, already known or regressed;
- **memory that never hides anything:** when you dismiss three similar findings for the same reason, Curmudgeon remembers. In later reviews, a look-alike finding is still shown and still counted, with a note naming your earlier reason, so you can decide in seconds. `critic_ledger.py dismiss --like N "why"` closes them on purpose. Memories only note Medium and Low findings (never High or Critical), `dismiss --like` only closes open ones, the verifier never sees notes, and they expire after 90 days unused;
- **spot-checks:** after a review it can show you three random findings and one of the verifier's refutations to judge (real, wrong or unsure). Your answers give a precision figure from your own projects, and show whether the verifier ever drops a real bug or lowers one's impact (counted separately). Every refutation and downgrade is kept in `.critic/refutations.jsonl`;
- the ledger tracks how many findings you actually acted on.

## How it compares with Anthropic's own review options

Checked against Anthropic's documentation on 24 October 2026 ([`/code-review`](https://code.claude.com/docs/en/code-review-local), [ultrareview](https://code.claude.com/docs/en/ultrareview), [Code Review](https://code.claude.com/docs/en/code-review)). There is no head-to-head benchmark yet; the comparison runs are planned, and their results will go in Benchmarks below.

| | Curmudgeon | `/code-review` (`/review` is an alias) | `/code-review ultra` (ultrareview) | Code Review (managed) |
|---|---|---|---|---|
| Where it runs | Your Claude Code session and your machine | Your Claude Code session, as a background subagent | A cloud sandbox on Anthropic's infrastructure | Anthropic's infrastructure, on GitHub pull requests |
| What leaves your machine, beyond the session's own model calls | Nothing by default (opt-in network calls are listed above) | Nothing | For a branch review, your repository state is bundled and uploaded; a PR review clones from GitHub | The GitHub App reads the repository |
| Who can use it | Anyone with Claude Code | Any plan | Requires a claude.ai sign-in; not on Bedrock, Agent Platform or Foundry, ZDR, HIPAA or CMEK organisations | Team and Enterprise organisations, turned on by an Owner |
| Cost | Your session's usage; the scripted checks cost no tokens | Your session's usage | 3 free runs on Pro and Max, then typically $5 to $25 per review in usage credits | Billed per review (see Anthropic's cost page) |
| How findings are checked | Quote at the cited line, script-counted votes of three blind reviewers, then blind per-finding verification that can only lower an impact | Depth scales with the effort level | Every reported finding is independently reproduced and verified | A verification step filters false positives |
| Runs your code | Yes, in each agent's private copy, when it helps reproduce a failure | Not documented | Reproduces findings in its sandbox | No: it reads the diff and surrounding code |
| False alarms measured | Yes, with decoys and clean twins in `eval/` | Not published | Not published | Not published |
| Beyond code | Interfaces in a real browser, documents and plans | Code | Code | Code |

Curmudgeon is not a replacement for any of these. Running it next to them costs nothing extra in scripted checks, and its ledger keeps your rulings across runs.

## Run it in CI

A starting point with [claude-code-action](https://github.com/anthropics/claude-code-action) (MIT), which takes a `plugins` input and a `plugin_marketplaces` input. The input names are from the action's `action.yml` as of 24 October 2026; this workflow hasn't been run by us yet, so treat it as a recipe to adapt, not a tested file.

```yaml
name: curmudgeon
on: pull_request
permissions:
  contents: read
  security-events: write   # for the SARIF upload
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: https://github.com/truerevelationR2D2/curmudgeon.git
          plugins: curmudgeon@curmudgeon
          prompt: "/curmudgeon:review the changes in this pull request, compared with origin/${{ github.base_ref }}"
      - uses: github/codeql-action/upload-sarif@v4
        if: always() && hashFiles('.critic/findings.sarif') != ''
        with: { sarif_file: .critic/findings.sarif }
```

For a stricter pipeline, pin each action to a full commit SHA, as this repository's own `ci.yml` does. Keep the API key in a repository secret, never in the file.

## Using Semgrep or other scanners with it

Curmudgeon is free and runs its own checks, written for this plugin. It never installs or runs another scanner. If you already use one, it fills in around it instead of doing the same work twice:

- **Results you already produce are evidence.** Leave a SARIF file anywhere in the project (for example `semgrep --sarif --output semgrep.sarif`, or zizmor, actionlint, CodeQL, Bandit, gitleaks, Trivy, hadolint, squawk, pint), and the scan reads it under the matching lens: Semgrep, CodeQL and Bandit under safety, zizmor, actionlint and Trivy under supply chain, and so on (`TOOL_LENS` in `critic_scan.py`).
- **One row per line, credited to both.** When Curmudgeon's own check and the other tool flag the same line under the same lens, the report keeps one row and notes `also_found_by`.
- **Semgrep is noticed, never run.** A Semgrep config, a CI step that runs it, or `semgrep` on your PATH is reported in a note. Curmudgeon never reads Semgrep's login files: whether you pay for it can't be seen, and isn't needed. If there is no Semgrep SARIF, the note says how to produce one.
- **Room to integrate more.** To add a tool, add its name and lens to `TOOL_LENS` with a test, as `CONTRIBUTING.md` describes. Anything that would send code or results off your machine needs your yes first.

## Security scan

`/curmudgeon:review security [what]` is a separate scan, like the lite and full reviews. It keeps the blind panel the size of the change calls for (one reviewer for a small change, three for a large one), tells the reviewers to look only for security problems (injection, access control, secrets, unsafe parsing, server-side requests, path traversal, the supply chain, and what a page loads, links to or posts to), and shows only the security rows of the scripted checks. Verification, vote counting and the quote check are the same as in every review.

**What it checks with scripts, with no model:**

- secrets in any text file, and the code rules for injection points (`eval`, raw HTML, unencoded URLs);
- dependencies: unpinned versions, install scripts, packages from URLs, and known vulnerable versions (below);
- CI and supply chain, and agent and MCP configuration (the same lenses the full review runs);
- **browser integrity**, for a page that may have been altered: a link whose visible address goes somewhere else, a punycode or non-ASCII look-alike host, a form that posts over plain `http` or to another site, a script from another site with no `integrity=` hash, and a weak Content-Security-Policy (in a `<meta>` tag or a `_headers`, `vercel.json`, `netlify.toml`, `nginx.conf` or `.htaccess` file). Run `critic_scan.py . --integrity-record` once on a version you trust, and later scans fail any link whose target changed, any form that now posts somewhere new, and any script or frame from a site the trusted version never used. The recorded copy, `.critic/integrity-baseline.json`, holds link labels and host names only.

**The security feed (off until you say yes).** The first security scan asks you once whether to keep a local copy of public vulnerability data, and how often to refresh it: daily, weekly, every two weeks, monthly, or off. Off is the default; it never downloads anything, and the scan then checks dependencies offline only. An unattended run never asks and leaves it off. Change your answer at any time with `security_feed.py set --cadence ...`, and see where it stands with `security_feed.py status`. With the feed on, the scan matches your lockfiles (`package-lock.json`, `requirements*.txt`) against the local copy, so no package name or version leaves your machine; a vulnerable version is a WARN, and a FAIL when the CISA list says it is exploited in the wild. A refresh happens when a security scan starts and the schedule says it is due.

Where the feed gets its data (every user downloads the same files; nothing about your project is sent):

| Source | Address | What it gives | Licence |
|---|---|---|---|
| OSV.dev bulk export | `https://storage.googleapis.com/osv-vulnerabilities/<ECOSYSTEM>/all.zip` (npm and PyPI) | Known vulnerable package versions, gathered by OSV from GitHub, PyPA and other advisory databases | Each record keeps its source's licence; GitHub Advisory Database records are CC-BY 4.0 |
| CISA Known Exploited Vulnerabilities | `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` | CVEs known to be exploited in the wild | CC0 1.0 |

Neither source signs its files, so each download is checked before it replaces the old copy: HTTPS only, a size limit, the zip's own checksum test, every record must parse and have an id, and a new copy may not lose more than half the records of the last one. The SHA-256 of every download goes into `feed-log.jsonl`. The data is stored as JSON tables in the plugin's data folder (`${CLAUDE_PLUGIN_DATA}/feed`, or `~/.curmudgeon/feed`) and is only ever read, never run. If a check fails, the old copy stays.

## Add your own checks

Drop a JSON file of rules into your project's `.critic/rules/` (or, to contribute one for everyone, into `plugin/skills/review/rules/`). Each rule is an id, a severity, an area, a regular expression matched line by line, a message, and optional file patterns; see `plugin/skills/review/rules/README.md`. Rules are data, never code, and their rows are reported as `rule-<id>`, so they can't pose as built-in checks. A project's rule files must be plain files (at most 256 KB each, 50 files and 2,000 rules in all); they run in a separate process with a 20-second limit and at most 50 matches per rule, and they can warn but never fail, so a slow, greedy or hostile rule file can't hang a review or flood it with findings. The background stop check skips them.

## What it runs, reads and sends

- **Runs:** its own Python scripts, plus a test command if you opt in to mutation testing: one you type with `--test-cmd`, or the one in `.critic/rules.md` only when you also pass `--project-checks` (a cloned repository can ship its own rules.md, so Curmudgeon shows you its commands and asks first). Every script a review starts and every outside command or network call it starts itself (git, npm, a Chromium launch, your test or check commands when asked, the opt-in OSV lookup) is listed in `.critic/runlog.jsonl`. The requests a page makes inside the browser aren't listed one by one. Tokens, passwords, keys, cookies and signed-URL signatures are masked. The log is git-ignored, and if your repository already tracks it, nothing is written to it and you're told why. In the browser checks it serves your files on `127.0.0.1` and blocks any request that leaves that origin. The scan's own browser checks never click a control that submits a form or sends data. The step-by-step driver (`browse.py`) does click them, but only on its simulated page, where whatever the page sends is answered locally and never leaves the machine; sending for real needs your yes.
- **Reads:** the files under review, and your CI's SARIF or JUnit output if present. It never reads its own earlier output as evidence.
- **Writes:** only inside `.critic/`, unless you ask for fixes. Before a fix it saves exact copies of the files it will change in `.critic/restore/` (private to you, git-ignored, never read by any report), so rollback is exact. If your code holds keys, so do those copies. A guard hook blocks direct edits to `.critic/` state. Each run moves the last run's raw reviews to `.critic/history/`, so they are never counted again. The raw reviews and other files that hold reviewers' exact quotes are git-ignored; everything Curmudgeon writes itself has secrets masked.
- **Sends:** nothing, by default. It declares no connectors or MCP servers, and it never contacts another AI: the outside reviewer is something you paste to and from yourself, only if you said yes. Three opt-in features reach the network: the security feed, once you switch it on, downloads public vulnerability files and sends nothing about your project (see [Security scan](#security-scan)); `--online` sends package names and versions to the free OSV vulnerability API (`api.osv.dev`); and a live URL is loaded only when you list its origin in `.critic/scope.json` and confirm the host on that run with `--allow-live HOST` (then only GET, HEAD and OPTIONS, up to a request cap). Without them, the page checks serve files only on this computer and block any request that would leave it. Secrets found in your code are redacted in every report.
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
  - SubagentStop: checks that each reviewer's and verifier's output follows the contract (it runs only for those two agents). When the agent really finishes, it deletes the agent's private copy and keeps its notes in `.critic/scratch/<agent id>/notes/`; a copy left by an interrupted run is deleted when the next run starts;
  - SubagentStop, cost: during a review run, reads each Curmudgeon agent's own transcript and records its token use in `.critic/cost.jsonl` (`critic_ledger.py tokens` totals it by role). Nothing leaves your machine;
  - PreToolUse: protects `.critic/` state.
  - PostToolUse, while-you-work scan: after Claude writes or edits a file in a project where Curmudgeon has run, the free scripted checks scan that one file (about a quarter of a second, no model tokens, no project commands) and hand any blocking problem straight back to Claude, once per version of the file. `/curmudgeon:gate off` turns it off; `gate on` or `gate async` turns it back on.
  - PostToolUse, stuck detection: a script watches each Curmudgeon agent's own recent tool calls. The same action with the same result three times, the same action failing three times, or two actions ping-ponging gets the agent one "rope" (what it repeated, and two ways out: change approach, or declare "cannot verify"). If it happens again, the agent is told to stop that scenario and move on, the repeated action is refused, and a typed STUCK record is listed in the teardown, never hidden. Other sessions and agents are never watched.
  - PreToolUse, stuck refusal: refuses the exact action a stuck Curmudgeon agent was told to stop repeating.
  - PreToolUse, blindness guard: each reviewer and verifier works in its own private, frozen copy of the project, made in its scratch folder when the agent starts (see SubagentStart below). The copy has no `.critic/` folder, so the agent's searches and relative paths can only find code. The guard holds it there. Bash commands must start with `cd <its copy> &&` (or, for git, `git -C <its copy>` on its own, because Claude Code asks before a `cd` followed by `git`), and a command whose paths lead to the project's `.critic/` (another agent's copy included), to a folder above it, or back to the project (`cd -`, `$OLDPWD`) is refused. Reads of the project's `.critic/` are limited to what the role needs: never the other reviews, the scan, the tally, the teardown or other agents' scratch folders. Paths are resolved, links followed and case ignored. This stops an honest agent from seeing what it shouldn't. It is not a sandbox against a hostile one, because any program you run can read any file you can. The guard also refuses a fork during a review run, because a fork inherits the whole conversation. Your own session is never limited. It adds about 30 ms to each read-type tool call;
  - SubagentStart: gives each Curmudgeon agent its own private scratch folder, `.critic/scratch/<agent id>/`, and gives each reviewer and verifier its private copy of the project in `.critic/scratch/<agent id>/payload/` (Claude Code lets an agent change directory only inside your project). In a git project the copy holds the files git tracks or would track (so build output and ignored files stay out); it never holds `.critic/` or files over 5 MB, links dependency folders such as `node_modules` instead of copying them, and stops at 500 MB (the agent is told when its copy is partial). The copy is its own git repository, sharing the project's history, so `git log` and `blame` work there and `git stash` or `reset` in it can't touch your real files. Making it can take a few seconds on a large project;

## Benchmarks

**Version 5.0.0 has not been re-measured with models yet.** The table below is from 4.0.0; the model runs that would re-measure it (the baseline from three or more runs, and the death match against other tools) cost money and are the maintainer's call. What 5.0.0 adds that can be measured without a model is measured:

| Scripted lens (5.0.0, no model) | Planted defects found | Wrong rows | Decoy and clean-twin rows |
|---|---|---|---|
| Tests of the tests | 7 of 7 | 0 | 0 |
| CI and supply chain | 13 of 13 | 0 | 0 |
| Agent and MCP configuration | 7 of 7 | 0 | 0 |
| Release and rollback | 7 of 7 | 0 | 0 |
| Requirements and intent | 4 of 4 | 0 | 0 |
| Operations | 6 of 6 | 0 | 0 |
| Code rules read code, not strings or comments | 6 of 6 | 0 | 0 |

`python3 eval/lens.py eval/lensN.json` reproduces each row. The strict YAML reader was compared with PyYAML on 6,191 files and 75,000 generated documents: 0 read differently.

Budgets for 5.0.0, measured with `claude plugin details` and `wc -w`: about 862 tokens added to every session (4.2.1: about 1,516); the review skill about 7.1k tokens when it runs (4.2.1: about 5.6k); words of instructions a reviewer reads before any code, now only what the payload needs: 2,565 for a code change with no lens, 2,666 to 2,732 with one lens, 3,251 for an interface, 4,020 with everything (4.2.1: 3,333 for every payload; 5.0.0 before this change: 4,563).

Measured on 24 October 2026: version 5.0.0 against 4.2.2, three review runs of each on every test, Sonnet 5.5, three blind reviewers per run, with the eval kit in `eval/`. Every finding that matched no planted bug was labelled by independent models that read and ran the code, saw no answer keys and were not told which version wrote it (none was labelled wrong; the rest were real bugs nobody planted, or true but trivial). A finding counts only when it points at the planted bug's lines. One 4.2.2 run of the invoices test fell back to a single context and is left out. All numbers are recorded in `eval/baseline.json` (5.0.0, now the baseline) and `eval/labels-2026-10-24.json`.

| Test (three runs pooled) | Planted bugs found, 4.2.2 → 5.0.0 | Findings that are real bugs, 4.2.2 → 5.0.0 | Report format checks passed, 4.2.2 → 5.0.0 |
|---|---|---|---|
| Notes app (16 planted bugs) | 42/48 → **48/48** | 51/51 → 58/58 | 29/33 → 32/33 |
| Orders dashboard (27 planted bugs) | 61/81 → **71/81** | 67/71 → **77/77** | 28/33 → 31/33 |
| Recipe app (9 decoys that look buggy but aren't, 2 real bugs) | 5/6 → **6/6**; no decoy flagged | 15/15 → 20/21 | 28/33 → 32/33 |
| Invoices (4 real bugs behind guards that look right) | 8/8 (2 runs) → 12/12 | 17/20 → 26/30 | 17/22 (2 runs) → 31/33 |
| Clean twins of the notes, dashboard and invoices apps (nothing planted) | – | Medium-or-worse findings: 12 real bugs nobody planted → 26 real and 2 trivial; no BLOCK in any run | – |

Cost: $1.01 a run for 4.2.2, $1.33 for 5.0.0 (the whole session, lead and agents). The accept/kill gate (`score.py --gate`) passes 5.0.0 on all seven tests. 5.0.0 found more planted bugs in every test; the one bug it found less often (2 of 3 runs against 3 of 3) was dropped on votes in one run. The first 5.0.0 build measured lost real findings because reviewers cited wrong line numbers (`cat -n` over several files) and the quote check retracted them, as it should; the reviewers' instructions were fixed and the quote check was left strict.

**Against the alternatives** (death match, 24 October 2026, the same seven tasks, three runs each, Sonnet 5.5, one scorer, blind labels; details in `eval/deathmatch-2026-10-24.md`):

| Reviewer | Planted bugs found | Wrong findings | Real share of all findings | Cost per run |
|---|---|---|---|---|
| Curmudgeon 5.0.0 | **134 of 147 (91%)** | **0** | **79%** | $1.57 |
| Plain Claude | 84 of 147 (57%) | 3 | 69% | $0.11 |
| Anthropic's code-review plugin | 44 of 147 (30%) | 1 | 65% | $0.10 |
| Claude Code's built-in `/code-review` | 44 of 147 (30%) | 4 | 59% | $0.10 |
| Semgrep (its own rules) | 6 of 147 (4%) | 39 | 30% | $0 |

Version 4.0.0, measured on 18 October 2026 with a looser scorer, for the record: notes app 16/16 found, 96% real (27 of 28); orders dashboard 27/27, 95% (35 of 37); decoy app 2/2 with no decoy at Medium or above, but only 30% of its findings real (3 decoys and several true-but-trivial nitpicks flagged at Low).

In that 4.0.0 run, after the fix stage, the fixed apps passed 9 of 9 and 12 of 13 browser behaviour tests. The miss was an animation that ignores the reduced-motion setting.

The report format score (`contract` in the eval) is the share of checks on how the written teardown follows its required format (11 checks for a review, 14 for a review and fix, which adds the refactoring manifest, the state ledger and the closure table): headers, a single verdict, counts that match the findings, evidence on every finding, and so on. It measures the report's form, not whether the findings are right.

These are small apps, so treat the numbers as indicative: with 58 findings, "58 of 58" could plausibly be anything from about 94% to 100%. Most of the noise left is in Low findings: true, but not worth anyone's time.

Curmudgeon also reviewed its own code. A fresh reviewer then checked each round of fixes, five rounds in all. The rounds turned up real bugs in its own scripts (two of them Critical), and each now has a regression test.

The fixtures, answer keys, decoys and scorer are in `eval/` (see `eval/README.md`). Run them yourself, and report runs where Curmudgeon was wrong. Those are the most useful reports there are.

## Credits and licence

MIT licence; see `LICENSE`. All code here is original. Some checks were inspired by open-source tools, and none of their code or rule text was copied. The tool that inspired each check is named in that script's header: gitleaks, Nu Html Checker, dependency-cruiser, knip, jscpd, ESLint, no-unsanitized, Stylelint, Bandit, OSV-Scanner, Stryker and axe-core. axe-core is used only if it is already installed, and is never bundled.

Contributions are welcome; see `CONTRIBUTING.md`.
