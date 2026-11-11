# Curmudgeon

**Prove it. Then I'll grumble.**

Curmudgeon is a review plugin for Claude Code. It reviews code, interfaces, documents and plans the way a grumpy senior engineer would, but it has to show its work: every finding needs a quoted line, a failing case and a vote, and findings are checked again by someone who didn't write them.

Most AI reviewers fail in one of two ways. They miss real bugs, or they bury them under confident false alarms. Curmudgeon is built against the second failure. A finding survives only if it makes it through the steps below:

1. Reviewers work **blind**: three in a full review, one for a small change. Each is told the code came from an unknown contractor, sees the files in a different order, and never sees the other reviewers. A script proctor checks each reviewer's transcript when it finishes and voids a review whose agent saw another's work.
2. A **Python script** does the counting. A model never does.
3. Surviving findings are checked again by a **blind verifier**: in a full review every one except Lows the reviewers all agreed were Low and scripted measurements (contrast, focus, budgets) that leave nothing to reproduce; in a lite review the Critical and High ones; in the smallest the contested ones; and in every tier, findings only an outside reviewer raised and findings whose reviewers disagreed on the impact. A run that skips a verdict its tier requires, or whose scripted checks didn't run, says DEGRADED in its counts, and the teardown can't be stamped without that line. The verifier starts from "this is not a defect" and must reproduce or trace the failure. It may lower an impact, but never raise one.
4. False alarms are **measured** with decoys (code that looks wrong but isn't) and clean twins (the same app without the planted bugs). It isn't just a promise.

## Install

```
/plugin install curmudgeon --marketplace truerevelationR2D2/curmudgeon
```

That form works inside a Claude Code session on version 2.1.275 or later. From your shell, `claude plugin install curmudgeon --marketplace truerevelationR2D2/curmudgeon` needs version 2.1.292 or later. On older versions, do it in two steps:

```
/plugin marketplace add truerevelationR2D2/curmudgeon
/plugin install curmudgeon@curmudgeon
```

You need Python 3.9 or later. The browser checks also need Playwright with Chromium (`pip install playwright && playwright install chromium`). Without Playwright, those checks are reported as unavailable, never as passed. Curmudgeon never installs Playwright or anything else for you; install it yourself if you want the browser checks.

## Commands

| Command | What it does |
|---|---|
| `/curmudgeon:review [what]` | Reviews and changes nothing. Writes `.critic/last-review.md`. |
| `/curmudgeon:review fix [what]` | Reviews, then fixes. Each fix must pass a re-check before it counts. |
| `/curmudgeon:review deep [what]` | Forces the full three-reviewer run, whatever the size of the change. |
| `/curmudgeon:review quiet [what]` | The same review with a shorter teardown: Critical and High in full, Medium and Low one line each. Every count stays exact. |
| `/curmudgeon:review audit [what]` | Audits someone else's system: the full review, changing nothing, with rules of engagement (active tests only on what `.critic/scope.json` lists), stated-versus-inferred requirements, and findings that give difficulty, an exploit scenario and short- and long-term fixes. |
| `/curmudgeon:review security [what]` | The security scan: the same blind panel as the review's size calls for, focused on security only, with the security checks, the browser integrity check and, if you switch it on, the local security database. See [Security scan](#security-scan). |
| `/curmudgeon:fix patch [id]` | Fixes one finding. |
| `/curmudgeon:fix iterate [part]` | Goes deeper on one part, or tries another approach. |
| `/curmudgeon:fix approve` | Keeps the last refactor. |
| `/curmudgeon:fix rollback` | Undoes the last refactor from its restore point. |
| `/curmudgeon:gate on\|async\|off` | Turns the optional stop gate on or off. When it's on, the session can't finish while reviewed files have changed since the last review, or while Critical or High findings are still open. |
| `/curmudgeon:check-updates` | Says whether a newer Curmudgeon is on GitHub, and how to update. One request to GitHub; nothing about you or your project is sent, and nothing is installed. |

You can also just say "tear this apart" or "review my work".

## Examples

Each of these works as typed, in any project:

1. **Review a change before you commit it.** `/curmudgeon:review` reviews what git shows as changed (or, with nothing changed, asks what to review). It sizes the run to the change, runs the free scripted checks, and writes the teardown to `.critic/last-review.md`. Nothing in your project is changed.
2. **Tear apart one file or folder, with the full panel.** `/curmudgeon:review deep src/payments/` runs three blind reviewers and blind verification on that folder, whatever its size, and lists what it did not check.
3. **Find and fix, then prove the fix.** `/curmudgeon:review fix src/app.js` reviews the file, fixes the findings, and re-checks each fix (it fixes the target, adds no new defect, and keeps working behaviour working). `/curmudgeon:fix rollback` puts the file back exactly if you don't like the result.
4. **A security pass.** `/curmudgeon:review security .` focuses the reviewers on security only and runs the security checks. The first time, it asks whether to build the local vulnerability database; say no and dependencies are checked offline only.
5. **Check an interface in a real browser.** `/curmudgeon:review site/index.html` serves the page on your own computer and checks keyboard reach, focus, a screen-reader view, reflow on a phone-width screen and dead controls, alongside the code review (needs Playwright).
6. **Audit someone else's system without touching it.** `/curmudgeon:review audit .` reviews in full and changes nothing, even if you ask it to fix; findings come with difficulty, an exploit scenario and short- and long-term fixes.

To try it on code with known bugs, the test apps in `eval/` (for example `eval/fixture`, a notes app with 16 planted bugs, and its clean twin `eval/fixture-clean`) have answer keys in `eval/answer_key*.json`, so you can check what it found.

## How a review runs

1. **Size it.** A script sets the tier from what changed and how sensitive it is:
   - trivial: one reviewer, with verification of contested findings only;
   - lite: one reviewer, plus verification of Critical and High findings;
   - full: three blind reviewers and full verification.
   The same script lists what calls the changed code.

   **A security scan** (`/curmudgeon:review security [what]`) is sized the same way, one reviewer for a small change and three for a large one, and it changes no file in your project. What differs:
   - the reviewers' briefs ask about security only: injection, access control, secrets, unsafe parsing, server-side requests, path traversal, the supply chain, and what a page loads, links to or posts to;
   - the report keeps only the security rows of the scripted checks: secrets, dependencies, CI and supply chain, agent and MCP configuration, browser integrity, and secrets in logs or DEBUG left on;
   - the **local security database is off by default.** The first security scan asks you once whether to build it, with Off as the default, and an unattended run never asks. With it off, dependencies are checked offline only (unpinned versions, install scripts, packages from URLs). If you say yes, you pick its folder, see a size estimate and sign off on it, and choose how often it refreshes. After that, each security scan refreshes it first when your schedule says it is due, and stops to ask again if it would grow more than 25% past the size you signed off on. The database is checked on your machine, so no package name leaves it. [Security scan](#security-scan) below has the details and the sources.
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
   - browser integrity, for a page that may have been altered (see [Security scan](#security-scan));
   - in a real browser: axe-core (WCAG 2.0 to 2.2, when axe-core is installed), keyboard reach, focus hidden behind other content, a screen-reader view, reflow at 320 and 390 px, layout shift, speed (median of three loads), visual baselines, and dead controls. Controls that look destructive (named, linked or titled like Delete, Pay or Send) are clicked only in the simulation described in the next item, so nothing they send leaves your machine; other controls are clicked on the page as it is served, which for a running app means real requests to it;
   - a step-by-step browser driver for reviewers and verifiers (`browse.py`): go to, click, type, select, check, press and wait, with the page's controls, console errors, network log and a screenshot after every step. Clicks run on a simulated page: local files are served on 127.0.0.1 by Curmudgeon itself, and a running app or live test site is recorded once (GET only) and then replayed offline, so anything a click tries to send is answered by the simulation and never reaches a real server. That makes even Delete safe to try. With `--expect`, a step returns before-and-after screenshots, the text that changed and what the page tried to send, for the reviewer to compare with what should have happened. Chromium can reach nothing but the page's own origin. Clicks are real mouse clicks, checked as they land. Sending data to your real local server, or recording a live test site listed in `.critic/scope.json`, needs your yes first, asked with a one-line reason;
3. **Three blind reviewers**, as described above. All three are the same model, so their agreement isn't independent the way three people's would be. The decoys, the clean twins and the optional outside reviewer are the defence against blind spots they share.
4. **The count.** The script drops any finding whose quoted code isn't at the cited line. It keeps findings that two of three reviewers agree on, or that come with an executed failing case. A Critical, High or Medium only one reviewer raised goes to a blind verifier instead of being dropped; a single-vote Medium is kept only if the verifier confirms it. A dedup step merges the same issue worded differently, so votes count issues, not phrasings.
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

Checked against Anthropic's documentation on 28 October 2026 ([`/code-review`](https://code.claude.com/docs/en/code-review-local), [ultrareview](https://code.claude.com/docs/en/ultrareview), [Code Review](https://code.claude.com/docs/en/code-review)). `/code-review` and Anthropic's code-review plugin were measured head to head on the same planted-bug tests, most recently on 29 October 2026 (see Benchmarks); ultrareview and the managed Code Review were not.

| | Curmudgeon | `/code-review` (`/review` is an alias) | `/code-review ultra` (ultrareview) | Code Review (managed) |
|---|---|---|---|---|
| Where it runs | Your Claude Code session and your machine | Your Claude Code session, as a background subagent | A cloud sandbox on Anthropic's infrastructure | Anthropic's infrastructure, on GitHub pull requests |
| What leaves your machine, beyond the session's own model calls | Nothing by default (the opt-in network calls are listed under [What it runs, reads and sends](#what-it-runs-reads-and-sends)) | Nothing | For a branch review, your repository state is bundled and uploaded; a PR review clones from GitHub | The GitHub App reads the repository |
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
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with: { fetch-depth: 0 }
      - uses: anthropics/claude-code-action@4845bacbb38b3c4b15d948f035349786f678e068  # v1.0.267
        env:
          CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS: "0"   # wait for the background reviewers (see below)
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: https://github.com/truerevelationR2D2/curmudgeon.git
          plugins: curmudgeon@curmudgeon
          prompt: "/curmudgeon:review the changes in this pull request, compared with origin/${{ github.base_ref }}"
      - uses: github/codeql-action/upload-sarif@9b3254085494b55a0f7c4c2b3d2d52cc712ce370  # v4.39.1
        if: always() && hashFiles('.critic/findings.sarif') != ''
        with: { sarif_file: .critic/findings.sarif }
```

Each action is pinned to a full commit SHA, with its version in a comment, as this repository's own `ci.yml` does; a tag can be moved to other code, a commit can't. Update a pin by looking up the new tag's commit yourself. Keep the API key in a repository secret, never in the file.

**Headless and CI runs need `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`.** In print mode (`claude -p`), Claude Code 2.1.182 and later stops waiting for background agents after ten minutes by default, and `0` removes that ceiling ([Claude Code docs](https://code.claude.com/docs/en/headless)). A full review's reviewers and verifiers run in the background and can take longer, so without the variable a run can end with no review, having spent the reviewers' tokens, and nothing warns you (it happened in our own testing). The action runs Claude Code through the Agent SDK and passes the step's environment to it (`base-action/src/parse-sdk-options.ts` at the pinned commit); we haven't confirmed that the SDK path has the same ceiling, and setting the variable is harmless either way. Set it for any other headless run too.

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
- **browser integrity**, for a page that may have been altered: a link whose visible address goes somewhere else, a host that mixes alphabets (a Cyrillic letter in a Latin name, plain or in punycode; a Japanese, Chinese or Korean name that mixes its own scripts is fine), a form (or a button's `formaction`) that posts over plain `http` or to another site, a script from another site with no valid `integrity=` hash, and a weak Content-Security-Policy (in a `<meta>` tag or a `_headers`, `vercel.json`, `netlify.toml`, `nginx.conf` or `.htaccess` file). Run `critic_scan.py . --integrity-record` once on a version you trust, and later scans fail any link whose target changed, any form that now posts somewhere new, and any script or frame from a site the trusted version never used, and any page that now names another site as its own. A `<base href>` decides where relative targets go, so it is followed, never trusted. The recorded copy, `.critic/integrity-baseline.json`, holds link labels and host names only, and is used only when you recorded it on this machine: one that came with the code is ignored until you check it and run `critic_scan.py . --integrity-adopt`, which prints every host it lists and a code, then `--integrity-adopt --confirm CODE` to trust exactly what you saw. It is kept out of git, since a copy git tracks could have come with anyone's code and is never used (untrack it with `git rm --cached` first).

**The security database (off until you say yes).** The first security scan asks you once whether to build a local database of public vulnerability data. Off is the default; with it off nothing is downloaded and dependencies are checked offline only. An unattended run never asks. If you say yes:

1. A folder window opens (on macOS and Windows, and on Linux when zenity or kdialog is already installed; otherwise you type the folder's full path). You choose, or create, the folder the database goes in.
2. Curmudgeon asks each source how big its file is (a size-only request that sends nothing about your project) and shows you an estimate of the compressed database's size and your free space. The first estimate is an upper bound: CISA's server doesn't say how big its file is, so its size limit is counted, and on a real build in October 2026 an estimate of up to about 284 MB gave a 73.5 MB database (about 245 MB downloaded). Later estimates use the size the last build measured.
3. You sign off on that size and choose how often to refresh: daily, weekly, every two weeks or monthly.
4. The database is built in your folder as one file, `curmudgeon-security.sqlite`. Run in a terminal, the build shows its download and build progress.

A refresh happens when a security scan starts and your schedule says it is due. If a refresh would make the database more than 25% bigger than the size you signed off on, it downloads nothing and asks you again. `security_feed.py status` shows where things stand; `security_feed.py set --cadence off` turns it off, after which the database is not read.

With the database on, the scan checks your lockfiles (`package-lock.json` versions 1 to 3, aliases included, and exact `==` pins in `requirements*.txt`) against it on your machine, so no package name or version leaves it. `yarn.lock` and `pnpm-lock.yaml` are not read yet: the scan says so in a WARN row, and the dependency check doesn't pass on them. A wildcard pin (`==1.0.*`) is listed, never looked up, and a requirements file named for development (`requirements-dev.txt`, `requirements_test.txt`) counts as dev-only. Then, like the big security vendors who keep a local signature database and check it against a global list, every match is checked against CISA's list of vulnerabilities known to be exploited in the wild: a match CISA lists is a FAIL, any other match a WARN (a NOTE for a dev-only package). A package whose ecosystem isn't in the database is never counted as checked; the scan says how many weren't.

**How the database is built** is fixed in `skills/review/references/feed-rules.json` (in the plugin folder), so every installation builds the same database from the same sources: what is kept from each record (ids, CVE aliases, a short summary, package names, affected versions and ranges) and what is dropped, the compression (each advisory as a zlib-compressed blob in SQLite), the tables, the size estimate, every check on the downloads, and how a match is judged.

Where the data comes from (every user downloads the same files; nothing about your project is sent):

| Source | Address | What it gives | Licence |
|---|---|---|---|
| OSV.dev bulk export | `https://storage.googleapis.com/osv-vulnerabilities/<ECOSYSTEM>/all.zip` (npm and PyPI) | Known vulnerable package versions, gathered by OSV from GitHub and other advisory databases | Each record keeps its source's licence; GitHub Advisory Database records are CC-BY 4.0 |
| CISA Known Exploited Vulnerabilities | `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` | The global list: CVEs known to be exploited in the wild | CC0 1.0 |

Neither source signs its files, so each download is checked before the new database replaces the old one: HTTPS only, a size limit, the zip's own checksum test, every record must parse and have an id, and a new copy may not lose more than half the records of the last one. The SHA-256 of every download is kept in the database and in `feed-log.jsonl`. The new database is built beside the old one and swapped in only when every check passes; it is only ever read, never run. Your settings (the folder, the schedule, the signed-off size) are kept in `~/.curmudgeon/feed`, outside every project, where the skill and the background check both find them (`CURMUDGEON_FEED_DIR` overrides). Settings from an older version kept in the plugin's data folder are moved there once.

## Optional modules

Five features stay off until you ask for them. The review skill reads the instructions for the first four only on a run that uses them (`plugin/skills/review/references/modules/`); the fifth belongs to the gate skill.

| Module | Turn it on | What it needs |
|---|---|---|
| Browser checks | give the scan a page (`--page dist/index.html`) | Playwright with Chromium, which you install yourself |
| Live sites | a page that isn't on this computer, listed in `.critic/scope.json` | the host typed on each run (and your approval of the scope file, when git tracks it or it came in a download) |
| Mutation testing | `--mutate <files>` | a test command (`--test-cmd`, or an approved `rules.md`) |
| Local security database | security mode, then your yes | a folder you pick and a size you sign off on |
| Background stop check | `/curmudgeon:gate async` | nothing more |

Without them, and without `--online` (package names to the OSV database) or `--project-checks` (your approved project commands), a review runs only Curmudgeon's own scripts and agents, on this computer.

## Add your own checks

Drop a JSON file of rules into your project's `.critic/rules/` (or, to contribute one for everyone, into `plugin/skills/review/rules/`). Each rule is an id, a severity, an area, a regular expression matched line by line, a message, and optional file patterns; see `plugin/skills/review/rules/README.md`. Rules are data, never code, and their rows are reported as `rule-<id>`, so they can't pose as built-in checks. A project's rule files must be plain files (at most 256 KB each, 50 files and 2,000 rules in all); they run in a separate process with a 20-second limit and at most 50 matches per rule, and they can warn but never fail, so a slow, greedy or hostile rule file can't hang a review or flood it with findings. The background stop check skips them.

## What it runs, reads and sends

- **Runs:** its own Python scripts, plus a test command if you opt in to mutation testing: one you type with `--test-cmd`, or the one in `.critic/rules.md` only when you also pass `--project-checks` and have approved that exact file with `critic_ledger.py approve rules.md` (it shows you the commands first; any change needs approving again). A `rules.md` or `scope.json` your repository tracks, or one in a folder that isn't the top of its own git repository (a downloaded zip, even inside another repository), could have come with the code, so it isn't used at all until you approve it the same way. Your approvals and consents are kept outside the project, in `~/.curmudgeon` (or `CURMUDGEON_STATE_DIR`), so a repository can't ship one. Every script a review starts and every outside command or network call it starts itself (git, npm, a Chromium launch, your test or check commands when asked, the opt-in OSV lookup) is listed in `.critic/runlog.jsonl`. The security database's downloads are not project calls, so they are listed in its own `feed-log.jsonl` beside its settings in `~/.curmudgeon/feed` instead. The requests a page makes inside the browser aren't listed one by one. Tokens, passwords, keys, cookies and signed-URL signatures are masked. The log is git-ignored, and if your repository already tracks it, nothing is written to it and you're told why. In the browser checks it serves your files on `127.0.0.1` and blocks any request that leaves that origin. The scan's own browser checks and the step-by-step driver (`browse.py`) click controls that look destructive (by name, id, link, form action or title: Delete, Pay, Send) only on a simulated page: whatever the page sends is answered locally and never leaves the machine. The driver goes further: it records a running app once (reads only) and replays it offline for every click. The scan clicks other controls on the page as it is served, so a control that changes data under an innocent name (say, a button labelled "Tidy" that deletes) does reach a running app; point the scan at a test instance, never at real data. Sending for real from the driver needs your yes, and only the driver can do it.
- **Reads:** the files under review, and your CI's SARIF or JUnit output if present. It never reads its own earlier output as evidence.
- **Writes:** only inside `.critic/`, unless you ask for fixes, with three exceptions you choose: the security database goes in the folder you picked, its settings go in `~/.curmudgeon/feed`; mutation testing (`--mutate`) changes one source file at a time while your tests run and puts it back each time, keeping a backup beside it and a private list of those backups in the plugin's data folder, so a killed run is restored on the next one. Before a fix it saves exact copies of the files it will change in `.critic/restore/` (private to you, git-ignored, never read by any report), so rollback is exact. If your code holds keys, so do those copies. A guard hook blocks direct edits to `.critic/` state. Each run moves the last run's raw reviews to `.critic/history/`, so they are never counted again. The raw reviews and other files that hold reviewers' exact quotes are git-ignored; everything Curmudgeon writes itself has secrets masked.
- **Sends:** nothing, by default. It declares no connectors or MCP servers, and it never contacts another AI: the outside reviewer is something you paste to and from yourself, only if you said yes. Four opt-in features reach the network: the security database, once you switch it on, asks the sources for their file sizes and downloads public vulnerability files, sending nothing about your project (see [Security scan](#security-scan)); `--online` sends package names and versions to the free OSV vulnerability API (`api.osv.dev`), only after you agree on that run (recorded by `critic_ledger.py consent online`); a live URL is loaded only when you list its origin in `.critic/scope.json` and confirm the host on that run (`--allow-live HOST`, with your consent recorded by `critic_ledger.py consent live HOST`; then only GET, HEAD and OPTIONS, up to a request cap); and `/curmudgeon:check-updates`, only when you type it, asks GitHub for the plugin's public version number, sending nothing about you or your project. Curmudgeon's reviewers and verifiers are refused the network and install commands it can recognise in their copy (`curl`, `wget`, `npx`, `git fetch`/`push`, package installs, inline code that opens a connection), and writes it can recognise into your project outside their copy and notes, or into Curmudgeon's record of your approvals and consent; that is a tripwire, not a sandbox (a test command they run can still fetch its dependencies, for example), and the real limit is Claude Code's permission mode. Without them, the page checks serve files only on this computer and block any request that would leave it. Secrets found in your code are redacted in every report.
- **Personal data:** Curmudgeon collects, stores and sends no personal data for itself: no accounts, tracking or analytics (the full privacy policy is in [PRIVACY.md](https://github.com/truerevelationR2D2/curmudgeon/blob/main/plugin/PRIVACY.md); security reports go through [SECURITY.md](https://github.com/truerevelationR2D2/curmudgeon/blob/main/SECURITY.md)). If the code you review contains personal data, the quoted lines, screenshots and restore copies it keeps in your local `.critic/` folder can include it. That folder stays on your machine, but only part of it is git-ignored: the findings, the teardown, the ledger and the scan's screenshots are not, so add `.critic/` to your own `.gitignore` if you don't want them committed ([PRIVACY.md](https://github.com/truerevelationR2D2/curmudgeon/blob/main/plugin/PRIVACY.md) lists both halves).
- **Limits:**
  - Restore copies are exact, so they keep a key that a fix removed until you delete them.
  - On native Windows, which ignores POSIX modes, the copies' folder is locked to you and SYSTEM with Windows' own permissions (`icacls`). If that fails, no copy is saved, and Curmudgeon says why.
  - **Native Windows:** CI runs the script tests on native Windows and on macOS, and since 4 November 2026 a failure on either fails the CI run. On commit b52d73f, of 423 tests, Windows passed 410 and skipped 13, each for a stated reason (POSIX modes, `/proc`, a shell-script stand-in); macOS and WSL2 each passed 412 and skipped 11. A full Claude Code session on native Windows hasn't yet been checked by hand. The hooks find Python themselves: a small launcher, `hooks/run.sh`, tries `python3`, then `python`, then `py -3`, and uses the first that really starts Python 3.9 or later, so the Microsoft Store placeholder is skipped. It runs under Git Bash on Windows, which Claude Code needs for its Bash tool there. Without Git Bash the hooks can't start, and the file-write and read guards then let your work go ahead instead of blocking it (a Windows run on 5 November 2026 showed the old form blocking every write when `python3` was the Store placeholder).
  - `.gitignore` doesn't stop a Docker build context, a zip or a sync tool from picking up `.critic/`.
  - Ignore rules don't cover files already committed. If an earlier version let you commit `.critic/` review or ledger files, remove them from git with `git rm --cached` (Curmudgeon warns when it sees tracked ones).
  - The verifier's "no hedging" rule is a word list: it stops "probably" or "seems", but not a confident, wrong refutation that cites a real line. Spot-checks (above) are how you catch those.
- **A project inside a folder named `.critic`** (say `~/.critic/projects/app`): the scripts take the first `.critic` in a path to be the project's own, so set `CRITIC_ROOT` to the project folder before a review there. The hooks use the folder your session started in, so they get it right either way. Start Claude in the project folder, never inside its `.critic` folder: from there the hooks would take that folder as the project.
- **Hooks:**
  - Stop: the optional gate, off until you turn it on;
  - Stop, background re-scan: free scripted checks on files edited since the last review, in one scan with a 5-minute limit, run without blocking, off until you turn it on with `/curmudgeon:gate async`;
  - SubagentStop: checks that each reviewer's and verifier's output follows the contract (it runs only for those two agents), and saves each verifier's verdict list, unchanged, in `.critic/verdicts/`, so the lead never retypes one. When the agent really finishes, it deletes the agent's private copy and keeps its notes in `.critic/scratch/<agent id>/notes/`; a copy left by an interrupted run is deleted when the next run starts. The same hook is the proctor: when a reviewer finishes, a script reads that reviewer's own transcript on your machine (the output of every command it ran and every file it read) for anything it must not have seen: the unique mark Curmudgeon writes into each brief, each reviewer's review (on every line), the scan report, the tally, the counts and each verification packet. Only marks count, never similar wording, so two reviewers who saw the same test failure are never voided. A reviewer that saw any is voided: its votes don't count and the counts name it. A finding only it raised goes to a blind verifier and is kept only if the verifier reproduces it by running it, labelled, with no vote and never at a higher impact. A reviewer that needs something outside its copy asks the proctor's request command, which hands over files elsewhere and the project's history but never `.critic/`, Curmudgeon's or Claude's own folders, and lists each request in `.critic/proctor/requests.jsonl`. Nothing leaves your machine;
  - SubagentStop, cost: during a review run, reads each Curmudgeon agent's own transcript and records its token use in `.critic/cost.jsonl` (`critic_ledger.py tokens` totals it by role). Nothing leaves your machine;
  - PreToolUse: protects `.critic/` state.
  - PostToolUse, while-you-work scan: after Claude writes or edits a file in a project where Curmudgeon has run, the free scripted checks scan that one file (about a quarter of a second, no model tokens, no project commands) and hand any blocking problem straight back to Claude, once per version of the file. `/curmudgeon:gate off` turns it off; `gate on` or `gate async` turns it back on.
  - PostToolUse, stuck detection: a script watches each Curmudgeon agent's own recent tool calls. The same action with the same result three times, the same action failing three times, or two actions ping-ponging gets the agent one "rope" (what it repeated, and two ways out: change approach, or declare "cannot verify"). If it happens again, the agent is told to stop that scenario and move on, the repeated action is refused, and a typed STUCK record is listed in the teardown, never hidden. Other sessions and agents are never watched.
  - PreToolUse, blindness guard: each reviewer and verifier works in its own private, frozen copy of the project, made in its scratch folder when the agent starts (see SubagentStart below). The copy has no `.critic/` folder, so the agent's searches and relative paths can only find code. The guard holds it there. Bash commands must start with `cd <its copy> &&` (or, for git, `git -C <its copy>` on its own, because Claude Code asks before a `cd` followed by `git`), and a command whose paths lead to the project's `.critic/` (another agent's copy included), to a folder above it, or back to the project (`cd -`, `$OLDPWD`) is refused. Each later `cd` is followed, and one that would leave the copy is refused. Reads of the project's `.critic/` are limited to what the role needs: never the other reviews, the scan, the tally, the teardown or other agents' scratch folders, a verifier reads verification packets only by path, with the Read tool, one batch at most, and no reviewer, verifier or dedup agent reads your project's own `.git` (its history and authors). A write that a link inside the copy (`node_modules`, `.venv`) would carry into your real project, or one it can recognise by its path as going into your project outside the copy, is refused. Paths are resolved, links followed and case ignored. This stops an honest agent from seeing what it shouldn't. It is not a sandbox against a hostile one, because any program you run can read any file you can. The guard also refuses a fork during a review run, because a fork inherits the whole conversation. Your own session is never limited. The same hook refuses the exact action a stuck Curmudgeon agent was told to stop repeating. Both run in one process that returns at once for any call that isn't a Curmudgeon agent's, so your own read-type tool calls pay one Python start (about 25 ms measured on Linux, down from about 85 ms for the two hooks this replaced), and the stuck watcher after each call about 30 ms;
  - SubagentStart: gives each Curmudgeon agent its own private scratch folder, `.critic/scratch/<agent id>/`, and gives each reviewer and verifier its private copy of the project in `.critic/scratch/<agent id>/payload/` (Claude Code lets an agent change directory only inside your project). In a git project the copy holds the files git tracks or would track (so build output and ignored files stay out); it never holds `.critic/` or files over 5 MB, links dependency folders such as `node_modules` instead of copying them (unless a link inside one leads outside the project; then the folder is left out and the agent is told), turns a link to anything outside the project into a short note instead of a copy, and stops at 500 MB (the agent is told when its copy is partial). The copy is its own git repository with no history: one commit holding your last commit, by an anonymous author, holding only that commit's files (no older versions, no `.critic/`), so `git diff` shows your uncommitted edits but no author, email or commit message reaches a blind reviewer through git (the last commit message reaches reviewers only as the change's stated intent, in their brief), and `git stash` or `reset` in it can't touch your real files. Making it can take a few seconds on a large project;

## Benchmarks

**Against Anthropic's review options, version 5.2.4** (29 October 2026; Sonnet 5.5 for every run; the seven death-match tasks five times each, plus eight more clean apps once each: 43 runs per reviewer; every run completed). Planted bugs are matched by script against the answer keys. Every other finding (1,150 in all) was judged by two blind labellers, with a third breaking their 89 ties, and 60 that only restated a planted bug already counted are left out; they agreed on 92% (Cohen's kappa 0.86 on the main tasks, 0.89 on the extra apps) and both judged all 24 known-truth controls correctly. Full method, limits and every file: [`eval/benchmark-5.2.4/`](https://github.com/truerevelationR2D2/curmudgeon/tree/main/eval/benchmark-5.2.4).

| Reviewer | Planted bugs found (95% CI) | Other findings judged real and actionable | Clean runs with a false alarm | Cost per run | Cost per confirmed bug | Launched agents |
|---|---|---|---|---|---|---|
| Curmudgeon 5.2.4, full | **225 of 245, 92%** (86–100%) | **95%** (245 real, 6 trivial, 6 wrong) | 6 of 23 | $1.42 | $0.130 | 43 of 43 runs |
| Curmudgeon 5.2.4, lite | **222 of 245, 91%** (85–100%) | 94% (199, 9, 3) | 1 of 23 | $0.75 | $0.077 | 43 of 43 runs |
| Claude Code's built-in `/code-review` | 76 of 245, 31% (20–68%) | 72% (215, 69, 16) | 9 of 23 | $0.10 | $0.015 | not visible |
| Anthropic's code-review plugin, given its PR facts and told to follow its steps | 64 of 245, 26% (14–48%) | 84% (36, 7, 0) | 0 of 23 | $1.00 | $0.431 | 43 of 43 runs |
| Anthropic's code-review plugin, as it runs | 48 of 245, 20% (8–53%) | 85% (72, 8, 5) | 2 of 23 | $0.09 | $0.032 | **0 of 43 runs** |

Run as it is, the code-review plugin launched none of the agents its instructions name, in every run; told to follow its own steps, it launched them every time and found a third more planted bugs (64 against 48) at eleven times the cost. The lite tier found 222 planted bugs to the full tier's 225 at 53% of the cost; the full tier found 1.14 more confirmed bugs a run (95% CI 0.45 to 1.80), about $0.59 for each extra one, and raised a false alarm on more clean apps. A confirmed bug is a planted bug found or a finding judged real and actionable; findings are not de-duplicated across a run, which can favour a reviewer that repeats itself. The intervals are cluster bootstraps over the four planted apps, so they are wide: the built-in `/code-review`'s 20–68% is how little four apps can pin down. The usage limit voided 47 of the first 175 runs; all were rerun and are on record. A blind review of the benchmark's own harness found nine defects; all were fixed, with tests, before these numbers, and a blind relabel of a 200-finding sample under the fixed harness agreed with the final labels as often as the two labellers agreed with each other. On 3 November 2026 the plugin's free-form replies were rescored with a fixed splitter (it had cut each finding's claim from its location), which raised the plugin as it runs from 34 to 48 planted bugs; the [write-up](https://github.com/truerevelationR2D2/curmudgeon/tree/main/eval/benchmark-5.2.4) has the details.

**Read the planted-bug column with this in mind:** the four planted apps are the ones Curmudgeon has been tuned on since 4.x, and its shipped checklist names several of their defect classes. Plain Claude given that checklist found 165 of 245 planted bugs, against 89 without it, so the checklist explains much of the lead. A benchmark on apps Curmudgeon has never seen hasn't been run yet; until it is, treat these as an upper bound on unfamiliar code.

**Planted-bug tests, version 5.2.1**, measured on 27 and 28 October 2026 with Sonnet 5.5, three blind reviewers per run and the eval kit in `eval/`. The 5.2 release gate ran three reviews of every test (21 runs); 5.2.1 changes no agent's instructions (its briefs now quote the stated intent on one line), so it got a smoke run of one review per test. A finding counts only when it points at the planted bug's lines.

| Test | 5.2 gate, planted bugs (3 runs) | 5.2 gate, findings that are real bugs | 5.2.1 smoke, planted bugs (1 run) |
|---|---|---|---|
| Notes app (16 planted bugs) | **48/48** | 65/66 | 15/16 |
| Orders dashboard (27 planted bugs) | **75/81** | 82/82 | 23/27 |
| Recipe app (9 decoys that look buggy but aren't, 2 real bugs) | **6/6**; no decoy flagged | 23/23 | 2/2; no decoy flagged |
| Invoices (4 real bugs behind guards that look right) | **12/12** | 28/29 | 4/4 |
| Clean twins (nothing planted) | 2 BLOCK runs of 9 | – | 2 BLOCK runs of 3 |

Every BLOCK on a clean twin rests on a High that independent labellers, blind to the answer keys and to which version wrote it, judged a real bug nobody planted: one tab's save overwriting another tab's notes, and an invoice Send whose network failure is never shown (every earlier blind label for them said real: 24 of 24 and 68 of 68). Cost per run: $1.44 for 5.2 (21 runs, $30.18), $1.41 for the 5.2.1 smoke. The accept/kill gate (`score.py --gate`) passed 5.2 on all seven tests. Labels are in `eval/labels-2026-10-27.json`.

Two ways to make reviews cheaper were measured and left out because they found fewer planted bugs: shorter reviewer output with dedup on Haiku 5.5 (13% cheaper; 45/48 and 72/81 on the first two tests), Haiku 5.5 for dedup alone (about 2.5 cents a run cheaper, twice as slow, and on identical inputs it merged two separate XSS sites into one, losing a Critical, in 2 of 10 runs), and short reviews in the lite tier (6% cheaper; 127 against 132 of 147). Details in `eval/lite-2026-10-28.md`.

Scripted lenses, measured without a model (`python3 eval/lens.py eval/lensN.json` reproduces each row):

| Scripted lens | Planted defects found | Wrong rows | Decoy and clean-twin rows |
|---|---|---|---|
| Tests of the tests | 7 of 7 | 0 | 0 |
| CI and supply chain | 13 of 13 | 0 | 0 |
| Agent and MCP configuration | 7 of 7 | 0 | 0 |
| Release and rollback | 7 of 7 | 0 | 0 |
| Requirements and intent | 4 of 4 | 0 | 0 |
| Operations | 6 of 6 | 0 | 0 |
| Code rules read code, not strings or comments | 6 of 6 | 0 | 0 |
| Browser integrity (look-alike links, insecure or off-site forms, unpinned scripts, weak CSP) | 10 of 10 | 0 | 0 |

The strict YAML reader was compared with PyYAML on 6,191 files and 75,000 generated documents: 0 read differently. The local security database was built for real on Windows from the full OSV and CISA feeds (about 245 MB downloaded, a 73.5 MB database in 30 seconds: 230,123 npm and 26,063 PyPI advisories, 1,760 CVEs CISA lists as exploited) and found a known-vulnerable lodash in a sample project.

Budgets, measured with `claude plugin details` on 10 November 2026 (5.5.0, loaded from the repository with `--plugin-dir`): about 919 tokens added to every session (5.3.0: about 864, before the `/curmudgeon:check-updates` listing of about 50); the review skill about 8.9k tokens when it runs (5.4.2: about 8.7k, for the plan step, abort, decision corrections and run logging; 5.5.0 adds the proctor's steps; 5.3.0: about 8.5k) (5.2.6: about 8.8k, measured from its tag; 5.2.1: about 7.8k; 5.0.0: about 7.1k; 4.2.1: about 5.6k). Earlier always-on figures: 5.2.6 about 864, 5.2.1 about 862, 4.2.1 about 1,516.

**Earlier measurements, for the record.** Measured on 24 October 2026: version 5.0.0 against 4.2.2, three review runs of each on every test, Sonnet 5.5, three blind reviewers per run, with the eval kit in `eval/`. Every finding that matched no planted bug was labelled by independent models that read and ran the code, saw no answer keys and were not told which version wrote it (none was labelled wrong; the rest were real bugs nobody planted, or true but trivial). A finding counts only when it points at the planted bug's lines. One 4.2.2 run of the invoices test fell back to a single context and is left out. All numbers are recorded in `eval/baseline.json` (5.0.0, now the baseline) and `eval/labels-2026-10-24.json`.

| Test (three runs pooled) | Planted bugs found, 4.2.2 → 5.0.0 | Findings that are real bugs, 4.2.2 → 5.0.0 | Report format checks passed, 4.2.2 → 5.0.0 |
|---|---|---|---|
| Notes app (16 planted bugs) | 42/48 → **48/48** | 51/51 → 58/58 | 29/33 → 32/33 |
| Orders dashboard (27 planted bugs) | 61/81 → **71/81** | 67/71 → **77/77** | 28/33 → 31/33 |
| Recipe app (9 decoys that look buggy but aren't, 2 real bugs) | 5/6 → **6/6**; no decoy flagged | 15/15 → 20/21 | 28/33 → 32/33 |
| Invoices (4 real bugs behind guards that look right) | 8/8 (2 runs) → 12/12 | 17/20 → 26/30 | 17/22 (2 runs) → 31/33 |
| Clean twins of the notes, dashboard and invoices apps (nothing planted) | – | Medium-or-worse findings: 12 real bugs nobody planted → 26 real and 2 trivial; no BLOCK in any run | – |

Cost: $1.01 a run for 4.2.2, $1.33 for 5.0.0 (the whole session, lead and agents). The accept/kill gate (`score.py --gate`) passes 5.0.0 on all seven tests. 5.0.0 found more planted bugs in every test; the one bug it found less often (2 of 3 runs against 3 of 3) was dropped on votes in one run. The first 5.0.0 build measured lost real findings because reviewers cited wrong line numbers (`cat -n` over several files) and the quote check retracted them, as it should; the reviewers' instructions were fixed and the quote check was left strict.

**Against the alternatives** (death match, 24 October 2026, the same seven tasks, three runs each, Sonnet 5.5, one scorer, blind labels; details in `eval/deathmatch-2026-10-24.md`). This and the next death match were scored before the splitter fix of 3 November 2026, and their raw replies weren't kept, so the free-form reviewers here may be under-credited:

| Reviewer | Planted bugs found | Wrong findings | Real share of all findings | Cost per run |
|---|---|---|---|---|
| Curmudgeon 5.0.0 | **134 of 147 (91%)** | **0** | **79%** | $1.57 |
| Plain Claude | 84 of 147 (57%) | 3 | 69% | $0.11 |
| Anthropic's code-review plugin | 44 of 147 (30%) | 1 | 65% | $0.10 |
| Claude Code's built-in `/code-review` | 44 of 147 (30%) | 4 | 59% | $0.10 |
| Semgrep (its own rules) | 6 of 147 (4%) | 39 | 30% | $0 |

**Against two orchestration plugins** (death match, 27 October 2026, Curmudgeon 5.2, the same tasks and method; details in `eval/deathmatch-2026-10-27.md`):

| Reviewer | Planted bugs found | Wrong findings | Real share of all findings | Cost per run |
|---|---|---|---|---|
| Curmudgeon 5.2 | **130 of 147 (88%)** | **1** | **87%** | $1.52 |
| BVarvill orchestrator-agent-plugin (its reviewer agent) | 84 of 147 (57%) | 8 | 69% | $0.13 |
| rbenzing Orchestrator (its code-reviewer agent) | 83 of 147 (56%) | 51 | 71% | $0.21 |

Version 4.0.0, measured on 18 October 2026 with a looser scorer, for the record: notes app 16/16 found, 96% real (27 of 28); orders dashboard 27/27, 95% (35 of 37); decoy app 2/2 with no decoy at Medium or above, but only 30% of its findings real (3 decoys and several true-but-trivial nitpicks flagged at Low).

In that 4.0.0 run, after the fix stage, the fixed apps passed 9 of 9 and 12 of 13 browser behaviour tests. The miss was an animation that ignores the reduced-motion setting.

The report format score (`contract` in the eval) is the share of checks on how the written teardown follows its required format (11 checks for a review, 14 for a review and fix, which adds the refactoring manifest, the state ledger and the closure table): headers, a single verdict, counts that match the findings, evidence on every finding, and so on. It measures the report's form, not whether the findings are right.

These are small apps, so treat the numbers as indicative: with 58 findings, "58 of 58" could plausibly be anything from about 94% to 100%. Most of the noise left is in Low findings: true, but not worth anyone's time.

Curmudgeon also reviewed its own code. A fresh reviewer then checked each round of fixes, five rounds in all. The rounds turned up real bugs in its own scripts (two of them Critical), and each now has a regression test.

The fixtures, answer keys, decoys and scorer are in `eval/` (see `eval/README.md`). Run them yourself, and report runs where Curmudgeon was wrong. Those are the most useful reports there are.

## Changes

What changed in each release, from the first Critic skill to now: [CHANGELOG.md](https://github.com/truerevelationR2D2/curmudgeon/blob/main/CHANGELOG.md).

## Credits and licence

MIT licence; see `LICENSE`. All code here is original. Some checks were inspired by open-source tools, and none of their code or rule text was copied. The tool that inspired each check is named in that script's header: gitleaks, Nu Html Checker, dependency-cruiser, knip, jscpd, ESLint, no-unsanitized, Stylelint, Bandit, OSV-Scanner, Stryker and axe-core. axe-core is used only if it is already installed, and is never bundled.

Contributions are welcome; see `CONTRIBUTING.md`.
