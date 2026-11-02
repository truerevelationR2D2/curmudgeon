# Changelog

Every release of Curmudgeon, newest first. The repository's history starts at 4.2.1; earlier versions are summarised from the project's own build and review records. Numbers are the ones measured at the time; the README's Benchmarks section has the current ones and how they were measured.

## 5.2.6 (unreleased): fixes from the full audit, batch 1 of 5

The full audit of 5.2.5 (six blind lenses, Curmudgeon's own full-tier review, three outside reviewers and mutation testing) confirmed 89 findings: 5 High, 27 Medium, 51 Low, 5 Nit. Batch 1 fixes the trust and evidence rules. Each fix has a test that fails on 5.2.5 (`plugin/tests/cases_7.py`).

**After upgrading**
- Run `/curmudgeon:gate on` (or `async`) again where you use the stop checks: the setting now lives outside the project, so the old marker alone does nothing.
- The first ledger command in each project sets your existing ledger aside, because 5.2.5 didn't record its checksum. Check its rulings with `critic_ledger.py adopt <file> --show`, then `adopt <file>` to take it back.

**Trust boundaries**
- A `.critic/ledger.json` counts as yours only when git doesn't track it and it is exactly the file Curmudgeon last saved on this computer (its checksum is kept outside the project). A read-only command (`show`, `check`) moves nothing, and if that outside folder can't be written, the command stops and changes nothing. A ledger that came in a zip, sits untracked inside another repository, or was changed after the last save is set aside on the next run and a new ledger starts; its rulings never apply. `critic_ledger.py adopt <file> --show` lists its rulings, and `adopt <file>` takes it back after you agree. (Before, a false-positive ruling in such a ledger could hide a Critical.)
- The page server answers a refused request with a 404, never from a file inside the served folder, and a folder's `index.html` that links outside is never served. (Before, a planted link at `.curmudgeon-refused/404` served any file you can read.)
- The browser driver and the scan serve a page only from inside the project: a page outside it, directly or through a link, is refused (its real folder would become the server's root). Copy it into the project, or run from its folder.
- Lockfiles, manifests and earlier CI results that link outside the project are never read, and each is listed once.
- `.critic/gate` and `.critic/gate-async` turn a stop check on only when you ran `/curmudgeon:gate`; a committed marker does nothing.
- Reviewers, verifiers and the detector can't record your sign-off on the security feed or start its downloads, and can't write into another agent's private folder.

**Evidence rules**
- A verifier may lower a finding to Nit only from Low. A downgrade of two or more steps, or from Critical or High, needs a run or a trace and a note that cites the reason as `file:line`; otherwise the old impact stays (03 §5.57.2).
- The review file names a finding's source; a reviewer can no longer mark its own finding as a scan row to skip the quote check.
- Verdicts applied from a file the verifier's stop hook didn't save mark the run DEGRADED and are named.
- A finding a verifier refuted stays refuted when the ledger loads again.
- In the full tier each Critical gets its own verifier, and `critic_run.py next` walks the variant hunt before the teardown.
- In round 3 a new unconfirmed Critical or High is recorded and marked held, so the stop gate shows it.
- Every finding at a line of a text file needs its quote (not only a list of code extensions), and a Low needs its failing case.
- A false-positive ruling hides nothing when it has no rule id (scan rows) or when its id was never scored (a Critical or High).
- The tally refuses to count when the ledger can't be read.
- A Medium only one reviewer raised, without a run, now goes to a blind verifier and is kept only if confirmed (before, it was dropped; the self-review lost a real High this way). A single-vote Critical or High was already verified, never dropped (03 §5.57.6).
- Every git command runs without the project's own commands from `.git/config` (`core.fsmonitor`, filter and diff drivers): a project that arrives with its own `.git` could otherwise make git run a program (03 §5.57.6).

**Privacy**
- `--online` sends package names only after you agree on that run (`critic_ledger.py consent online`); without it the lookup runs offline and the report says so.
- Text from earlier tools' SARIF results is masked like every other report field.

**Tests**
- New tests pin the quote check and the evidence floors where mutation testing found gaps (a missing file, the 60-character refutation, two-vote confirmation, quote windows).

## 5.2.5 (30 October 2026)

Fixes from an independent combined review (two outside reviews and two blind reviews, every claim reproduced or read), each with a test that fails on the code before it, and each batch put through three blind review rounds. [plugin/RULINGS.md](plugin/RULINGS.md) indexes the rulings the code cites.

**Evidence rules**
- The scan's FAILs reach the tally and the counts.
- The quote check is strict: the cited line or one either side, case kept, at least 12 characters.
- When reviewers disagree on a finding's impact, it is filed at the highest and always verified.
- One reviewer's findings are never merged into each other.
- A reviewer's own "executed" no longer makes a finding confirmed without a verifier.
- Each tier verifies exactly what its rule says, and a missing required verdict marks the run DEGRADED.
- Verifier verdicts are saved by a hook, unchanged.
- The teardown is checked against the counts.

**Trust boundaries**
- A `.critic/rules.md` or `scope.json` that may have come with the code is used only after you approve that exact file (`critic_ledger.py approve`, which shows the whole file). A file counts as yours only when your git work tree tracks no copy of it and you didn't get it in a zip.
- Approvals, and consent for live sites and writes (recorded per run), are kept outside the project in `~/.curmudgeon`.
- A reviewer's copy holds one anonymous commit of your last commit, without `.critic/`, older versions or a reflog.
- Reviewers and verifiers can't:
  - write into your project from their copy;
  - read your project's `.git`;
  - write the record of your approvals and consent;
  - use the network or install commands the guard recognises.
  This is a tripwire, not a sandbox (PRIVACY.md).
- Verifiers read packets only by path, one batch at most.
- A false-positive ruling hides only its exact finding.
- A review needs a stop-hook record showing it was written in a private copy, or the run is DEGRADED.

**Hooks, platforms and the eval kit**
- The always-on hooks are merged into one PreToolUse and one PostToolUse process: about 25 and 30 ms per call, down from about 85 and 47 ms.
- On a Mac or Windows machine with no one at the screen (CI, SSH), the security database's folder picker no longer waits ten minutes for a window.
- A browser start refuses missing consent before looking for Playwright.
- The skill says Curmudgeon never installs Playwright.
- CI pins actions v7 by commit and adds Python 3.14. A macOS job (all 244 script tests pass) and the full script tests on Windows (168 of 244 pass) run but are not yet required.
- The eval kit:
  - fills the planted key into each copy of the fixture, so no arm sees the placeholder's name;
  - widens one answer-key entry (E02) to the wording reviewers actually use;
  - computes its confidence intervals by app as well as by run;
  - archives three plain-Claude arms.
  The 5.2.4 benchmark write-up has the rescored figures; the README's Benchmarks section is updated in the next documentation pass.

## 5.2.4 (29 October 2026)

- The plugin, marketplace and review-skill descriptions, and the README's opening, now say what Curmudgeon does at every size: one to three blind reviewers sized to the risk, and findings re-checked blind (all of them in a full review, the Critical and High ones in a lite review, the contested ones in the smallest). They used to say three reviewers and every finding, which is true only of a full review.
- The plugin description mentions the security scan; keywords add audit and dependencies.
- This changelog.

## 5.2.3 (28 October 2026)

- The scanner tests' fake secrets are built from pieces at run time, like the other fake keys, so no file in the plugin carries a credential-shaped value (found by the plugin directory's validation).
- README: "How a review runs" explains the security scan, and that its local database is off by default.

## 5.2.2 (28 October 2026)

- Ready for Anthropic's plugin directory: the tests are split so no file in the plugin passes the directory's 256 KiB limit; `PRIVACY.md` (Curmudgeon collects nothing for itself; the four opt-in features, what each sends and to whom); `SECURITY.md` (how to report a vulnerability privately; a first reply within 7 days); a README Examples section with six prompts.
- README corrections, each checked against the code or Anthropic's docs: reviewer counts by tier, the shell install needs Claude Code 2.1.292, missing Playwright reads "unavailable", the full browser-check list, the comparison with Anthropic's review options re-checked, and what Curmudgeon writes.

## 5.2.1 (28 October 2026, the first release on `main` since 4.2.1)

It holds everything built since 4.2.1: 4.2.2, 5.0.0, the 5.1 work and 5.2. Measured: the 5.2 release gate passed on all seven tests (planted bugs 48/48, 75/81, 6/6, 12/12), and a 5.2.1 smoke run found 15/16, 23/27, 2/2 and 4/4 at $1.41 a run.

**Security suite (5.2)**
- `/curmudgeon:review security`: a security-only review, sized like any other, that changes no file.
- The browser integrity lens: look-alike links and hosts, forms that post over plain http or to another site, scripts from other sites with no integrity hash, a weak Content-Security-Policy, and a recorded copy of a trusted version to compare against. Measured on its own fixture: 10 of 10 planted defects, no row on decoys or the clean twin.
- The local security database, off until you say yes: built in a folder you pick in a folder window, after an estimate you sign off on, from OSV.dev's public npm and PyPI data, with every match checked against CISA's list of vulnerabilities exploited in the wild (a FAIL). Nothing about your project leaves your machine. Download and build progress in a terminal. Built for real on Windows: about 245 MB downloaded, a 73.5 MB database in 30 seconds.
- Without Playwright, Curmudgeon says how to install it and offers once; it never installs anything itself.

**Since 5.2**
- Decision 34: the scan's click check presses buttons named like Delete, Pay or Send only in the simulation (writes answered locally, a running app replayed from a one-time read-only recording), instead of skipping them.
- Fixes from a security scan of the plugin itself (2 High, 5 Medium) and two blind full-tier rounds (the database code: 2 High, 6 Medium, 5 Low; the 28 Oct changes: 8 Medium, 5 Low), each with a test that fails on the old code. Among them: a duplicate `href` can no longer hide a link's real target; mutation testing restores only backups it recorded itself, outside the project; a link to a private file outside the project is never copied into a reviewer's workspace; a committed ledger can't hide findings; the page server never serves `.critic/` or dotfiles; yarn and pnpm lockfiles are reported as not read instead of passing.
- The browser driver runs on Python 3.9 to 3.11 again, and database connections are closed (Windows locks open files). CI covers Python 3.9 to 3.13 and Windows.
- Two cost cuts were measured and left out because they found fewer planted bugs: shorter reviews with dedup on Haiku 5.5, and short reviews in the lite tier.

**The 5.1 work (24 and 25 October, never released on its own)**
- Fastest results first: the scripted results are shown while the reviewers still work.
- A Nits tier for true but trivial findings, listed and never counted.
- Two other cost cuts (batched verifiers, a lighter lead) measured worse and were reverted.
- Decision 39: a BLOCK on a clean twin fails the release gate only when nothing real backs it.

## 5.0.0 (24 October 2026)

- Structural blindness: each reviewer and verifier works in its own private, frozen copy of the project, with no `.critic/` folder in it, and a guard keeps it there.
- New scripted lenses, each measured on planted defects before it shipped: tests of the tests, CI and supply chain, agent and MCP configuration, release and rollback, requirements and intent, and operations.
- The audit mode for someone else's system, with a deny-by-default scope file for live checks.
- The browser driver: a step-by-step simulated page for reviewers and verifiers, with before-and-after checks.
- The variant hunt, LSP use by reviewers and verifiers, other scanners' SARIF read as evidence, and Semgrep noticed but never run.
- Real token accounting, the accept/kill gate, the golden and replay tests, and CI.
- One `/curmudgeon:fix` command for patch, iterate, approve and rollback.
- A leaner footprint: about 862 tokens in every session, down from about 1,516 in 4.2.1.
- Measured against 4.2.2 (three runs of each test): more planted bugs found in every test. Death match: 134 of 147 planted bugs, against 84 for plain Claude and 44 for Anthropic's code-review plugin.

## 4.2.2 (24 October 2026)

- Security and integrity fixes, reviewed blind over three rounds (the last round's fixes not re-reviewed). Released on `main` as part of 5.2.1.

## 4.2.1 (18 October 2026)

- Twelve fixes from a fresh blind review of 4.2.0. 57 script tests.

## 4.2.0 (18 October 2026)

- The optional outside reviewer: offered once, default no. Curmudgeon writes a brief, you paste it into another AI yourself and paste the answer back, and its findings get the same quote check and blind verification. Two double-blind tests had found almost no overlap between another AI's review and Curmudgeon's (0 of 23 findings, then 2 of 14).

## 4.1.1 (18 October 2026)

- Fixes for an outside double-blind review's findings.

## 4.1.0 (18 October 2026)

- Memory that notes and never hides: three similar dismissals become a note on look-alike Medium and Low findings, which stay counted.
- The refutation log, spot-checks and precision by category, the run log, Python checks read with Python's own parser, an SPDX licence check, and rule files.

## 4.0.1 to 4.0.5 (18 October 2026)

- Plugin-directory lint fixes, the icon, and credential-pattern flags.

## 4.0.0 (18 October 2026)

- Published as Curmudgeon under the MIT licence, renamed from Critic.
- Three blind reviewers with a vote counted by a script, blind per-finding verification that may lower an impact but never raise it, the quote check, risk tiers and a change map, stable finding ids in a ledger.
- Every free outside tool it learned from was rebuilt as its own code; it installs nothing.
- An eval kit that measures precision as well as recall, with decoys and clean twins. The goal changed from finding everything to few false alarms, with evidence for every finding.
- Five rounds of self-review before release.

## Before Curmudgeon: Critic (17 October 2026)

- Critic v1: a read-only review skill, with free scripted checks run first.
- Critic v2: a closed loop of teardown, refactor and re-check, with approve, iterate, patch and rollback.
- Critic v3 and v3.1: a plugin with separate judgment and detector agents, a DEGRADED banner, an intent gate, "no case, no finding", a three-round cap and the stop gate. Its self-review found 32 findings, all fixed in 3.1.
