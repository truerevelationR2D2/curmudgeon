# Design rulings referenced in the code

Comments in Curmudgeon's scripts and hooks cite the maintainer's design rulings as `§2` or `§5.NN` (sometimes
`03 §5.NN`, after the file they are kept in). This is the public index of every ruling the plugin's code, its tests and the eval kit cite: what
was decided, and when. The design invariants (`§2`) are the ones the README lists under "How it works".

| Ruling | Date | What was decided |
|---|---|---|
| §2 invariant 3 | from the start | A quote that isn't at its cited line retracts the finding. |
| §2 invariant 4 | from the start | Surviving findings are re-checked by a blind verifier whose default is "not a defect"; a verifier may lower an impact, never raise it; a refutation must cite a real guard as `file:line`. Which findings each tier verifies is stated exactly (§5.56). |
| §5.6 | 20 Oct 2026 | Proportionality: Curmudgeon sizes each job (a document doesn't get the sweep a large code change needs). |
| §5.8 | 20 Oct 2026 | Measure against the competition: the benchmark runs task by task against the alternatives, in an apples-to-apples death match. |
| §5.13 | 20 Oct 2026 | The step-by-step browser driver: security first; anything that loosens a security default asks the user, with a one-line reason. |
| §5.15 | 20 Oct 2026 | Never give up silently: an agent stuck on one thing gets a "rope" (change approach or declare it can't verify), then is moved on, and the stuck record is kept. |
| §5.20 | 23 Oct 2026 | The death match covers the specialist tools too (Semgrep and others that do one part of the job), not only Anthropic's own. |
| §5.22 | 24 Oct 2026 | The death match is a development benchmark of capability, parity and quality, not a feature of the plugin. |
| §5.29 | 24 Oct 2026 | Reviewer blindness is structural: each reviewer and verifier works in a private frozen copy of the project, and a guard keeps it there. |
| §5.37 | 24 Oct 2026 | Optimising never costs quality: every cost saving is measured against the baseline and kept only if recall, precision, impact misses, decoy hits and clean-twin results are no worse. |
| §5.38 | 24 Oct 2026 | The 5.1 plan (lead diet as a lab experiment, lite measured against full, batched verifiers, stricter Lows with Nits below them, fastest results first, the security scan as its own release). |
| §5.40 | 26 Oct 2026 | The security feed is a local database the user places and signs off on: nothing about the project leaves the machine, the user picks the folder and approves the size and schedule. |
| §5.45 | 27 Oct 2026 | Cost experiments ship first as a separate packaged branch, and are dropped if quality falls. |
| §5.46 | 28 Oct 2026 | 5.2.1: the cost-saving changes go into the lite tier only; the full tier is left as it was. |
| §5.47 | 28 Oct 2026 | The 5.2.1 builds were merged into one, after their measurements. |
| §5.56 | 29 Oct 2026 | Fixes from an independent combined review, approved item by item: the scan's FAILs reach the counts; a strict quote check (the cited line or one either side, case kept, at least 12 characters); split impacts filed at the highest and verified; one reviewer's findings never merged; self-reported runs capped below "confirmed"; one rule for what each tier verifies, with DEGRADED when a required verdict is missing; verifier verdicts saved by a hook; the teardown checked against the counts; a repository's own rules and scope files used only once approved; reviewer copies without git history; no writes through links, no installs, no network from reviewer copies; consent recorded per run for live sites and writes; verifiers limited to their own packets; rulings that hide only their exact finding; a record that each reviewer worked in its private copy; CI on Windows and macOS, with Python 3.14. |

`§11` in `security_feed.py` is section 11 of the Semantic Versioning 2.0.0 specification, not a ruling.
