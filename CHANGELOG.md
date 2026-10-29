# Changelog

Every release of Curmudgeon, newest first. The repository's history starts at 4.2.1; earlier versions are summarised from the project's own build and review records. Numbers are the ones measured at the time; the README's Benchmarks section has the current ones and how they were measured.

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
