# The 5.2.4 benchmark (29 October 2026)

Asked for in ruling §5.53: repeat the death match against Anthropic's code-review options with a stronger design,
keep the old tasks so the numbers stay comparable, report the code-review plugin's agent-launch behaviour, keep
planted-bug detection separate from independently judged real-world findings, and report the share of findings
independently confirmed as actionable, by severity. Budget rulings §5.54 and §5.55.

Every number below is recomputed by `python3 eval/bench_stats.py eval/benchmark-5.2.4/2026-10-29-015736
eval/benchmark-5.2.4/2026-10-29-093654` and `python3 eval/label.py recheck eval/benchmark-5.2.4/2026-10-29-015736
eval/benchmark-5.2.4/recheck` (no model calls); `stats.md` and `stats.json` here are the first command's output.

## Conditions

- Claude Code 2.1.312, model `claude-sonnet-5-5` for every run, headless (`claude -p`), each run in its own fresh
  temporary git repository holding one task's app.
- Curmudgeon: a frozen copy of `plugin/` at commit `6bf464c` (version 5.2.4). Every other installed plugin was
  switched off in every run, except the one arm's own (`run.json`, `plugins_off`).
- Tasks: the 7 death-match tasks (four planted-bug apps with 16, 27, 2 and 4 planted bugs, plus three clean twins),
  5 runs each per arm; and 8 more clean apps (the scripted lenses' clean twins), 1 run each per arm.
  43 runs per arm, 215 in all.
- Arms (prompts verbatim in `eval/deathmatch.json`):

| Arm | What runs |
|---|---|
| `curmudgeon` | `/curmudgeon:review deep .`: the full tier, three blind reviewers and blind verification of every finding |
| `curmudgeon-lite` | `/curmudgeon:review .` in the lite tier: one blind reviewer, Critical and High findings verified |
| `code-review` | Anthropic's code-review plugin as it runs: its command on a branch over an empty base, told to read the local diff and print instead of posting |
| `code-review-best` | The same plugin given everything its step 1 asks GitHub for, and told to follow its steps 2 to 7 exactly, launching every agent each step names |
| `cc-code-review` | Claude Code's built-in `/code-review` |

## Results

| Arm | Planted bugs found (95% CI) | Other findings judged real / trivial / wrong | Real and actionable | Clean runs with a false alarm (one-sided 95% upper bound) | Cost per run | Cost per confirmed bug (95% CI) | Median time | Runs that launched agents |
|---|---|---|---|---|---|---|---|---|
| Curmudgeon, full | **222 of 245, 91%** (86% to 96%) | 248 / 6 / 6 | 95% | 6 of 23 (45%) | $1.42 | $0.130 ($0.115 to $0.152) | 273 s | 43 of 43 |
| Curmudgeon, lite | **222 of 245, 91%** (87% to 95%) | 199 / 9 / 3 | 94% | 1 of 23 (19%) | $0.75 | $0.077 ($0.067 to $0.090) | 236 s | 43 of 43 |
| Built-in `/code-review` | 76 of 245, 31% (24% to 42%) | 215 / 69 / 16 | 72% | 9 of 23 (58%) | $0.10 | $0.015 ($0.012 to $0.018) | 38 s | not visible (see Limits) |
| Code-review plugin, best effort | 64 of 245, 26% (17% to 34%) | 35 / 9 / 0 | 80% | 0 of 23 (13%) | $1.00 | $0.435 ($0.343 to $0.618) | 74 s | 43 of 43 |
| Code-review plugin, as it runs | 33 of 245, 13% (6% to 22%) | 114 / 10 / 7 | 86% | 3 of 23 (30%) | $0.09 | $0.027 ($0.020 to $0.039) | 22 s | **0 of 43** |

Real and actionable findings by severity, as a share of each arm's judged findings:

| Arm | Critical | High | Medium | Low |
|---|---|---|---|---|
| Curmudgeon, full | 1 (0.4%) | 18 (7%) | 131 (50%) | 98 (38%) |
| Curmudgeon, lite | 1 (0.5%) | 16 (8%) | 106 (50%) | 76 (36%) |
| Built-in `/code-review` | 2 (0.7%) | 25 (8%) | 93 (31%) | 95 (32%) |
| Code-review plugin, best effort | 1 (2%) | 8 (18%) | 18 (41%) | 8 (18%) |
| Code-review plugin, as it runs | 3 (2%) | 43 (33%) | 42 (32%) | 25 (19%) |

Paired on the same task and run (43 pairs each), Curmudgeon full against:

| Other arm | Confirmed bugs per run, full minus other (95% CI) | Runs full did better / worse / tied | Cost per run, full minus other (95% CI) |
|---|---|---|---|
| Curmudgeon, lite | +1.14 (0.53 to 1.74) | 24 / 9 / 10 | +$0.67 ($0.62 to $0.73) |
| Built-in `/code-review` | +4.16 (2.47 to 6.00) | 34 / 9 / 0 | +$1.33 ($1.23 to $1.43) |
| Code-review plugin, best effort | +8.63 (7.02 to 10.33) | 41 / 0 / 2 | +$0.42 ($0.32 to $0.52) |
| Code-review plugin, as it runs | +7.53 (6.00 to 9.09) | 41 / 2 / 0 | +$1.33 ($1.24 to $1.44) |

What the numbers say:

1. **Planted bugs.** Both Curmudgeon tiers found 91%; the best of the others found 31%. The lite tier found
   exactly as many planted bugs as the full tier at 53% of its cost.
2. **The code-review plugin's agent launch.** As it runs, the plugin launched no agent in any of its 43 runs,
   though its instructions name several; it read the diff itself and replied in about 20 seconds. Given the facts
   its first step asks for and told to follow its steps, it launched agents in all 43 runs (8.8 a run) and found
   about twice as many planted bugs (64 against 33), at eleven times the cost.
3. **Real findings beyond the plants.** Of the findings that matched no planted bug, the labellers judged 95%
   (full) and 94% (lite) of Curmudgeon's real and actionable, against 72% to 86% for the others. Most of
   Curmudgeon's are Medium.
4. **Full against lite.** Full found 1.14 more confirmed bugs a run for $0.67 more, about $0.59 per extra
   confirmed bug, and raised a false alarm on more clean runs (6 of 23 against 1 of 23).
5. **False alarms.** Only the best-effort plugin raised none on the clean apps (0 of 23; the one-sided 95% upper
   bound by the rule of three is 13%). With 23 clean runs per arm, every bound here is wide.

## How findings were judged

- **Planted bugs** are matched by script against the answer keys (`eval/keymatch.py`): a finding counts only when
  it points at the planted lines and states the planted defect. Nothing here relabels them. A second finding that
  restates a planted bug already credited (its other site, or the same claim again) is not a separate bug: 60 such
  findings are left out of every count (29 full, 17 lite, 7 best-effort plugin, 7 built-in).
- **Every other finding** was judged blind by two labellers (`eval/label.py`, brief in `eval/labeller-brief.md`):
  Sonnet 5.5 agents that saw only the finding's words, with markdown removed, and a copy of the app outside
  `eval/`, never the arm, the run or the answer key. Verdicts: real, trivial (true but not worth acting on), wrong,
  or none (a heading or note, not a finding; left out of every share). Where the two disagreed on the verdict or on
  actionable, a third labeller (Opus 5.5) decided, seeing neither label. When they agreed but differed on
  severity, the lower was taken.
- **Agreement:** 865 of 945 (92%, Cohen's kappa 0.86) on the main tasks and 196 of 205 (96%, kappa 0.89) on the
  extra clean apps; 89 ties went to the tiebreaker.
- **Known-truth controls,** mixed in blind: 12 planted-bug findings shown against their own app (truth: real) and
  against the clean twin where the bug is fixed (truth: wrong). Both labellers judged all 24 correctly.
- **A blindness gap, and the check on it.** A blind review of this harness found that the labellers' packets named
  each app by its folder (`fixture-clean`, say), so a labeller could tell a clean twin from its planted app (which
  also made the controls easier); that the planted app and its twin were copied side by side; and that two apps
  carried giveaway text (a `__PLANTED_STRIPE_KEY__` literal and a "Decoys: …" comment). The harness now gives apps
  opaque names, copies each into its own folder and replaces those words line for line. To see whether the gap
  biased the labels, a fresh labeller relabelled a stratified sample (40 findings per arm, 200 in all, plus the 24
  controls) under the new export: it agreed with the final labels on 183 of 200 (91.5%), the same as the two
  original labellers' agreement with each other, against 190 of 200 for the first labeller, whose labels are part
  of the final ones. It judged all 24 controls correctly with the names hidden. Its changes were scattered between
  real and trivial, with no lean towards "wrong" on the clean twins. Within the sample, the code-review plugin's
  real-and-actionable share moved the most (83% to 69% of 40 findings). Files: `recheck/`.
- **False alarm** on a clean app: a finding judged wrong, or one that cites a line and was not labelled. A
  finding judged trivial or none is not a false alarm.
- **Confirmed bugs** = planted bugs found + other findings judged real and actionable.

## Limits

- **Findings beyond the plants are counted, not de-duplicated.** Two findings about the same unplanted bug count
  twice. Curmudgeon merges duplicates before it reports; the other arms were not checked for this, so the count can
  favour a reviewer that repeats itself.
- **The labellers are models,** not people. The controls, the agreement and the recheck show they can tell a planted
  bug from a fixed one and judge consistently; they don't prove every judgement.
- **The built-in `/code-review`** runs as a background subagent; Claude Code reported 0 tokens for it and its
  transcript shows no agent calls, so its agent use is not visible here. Its cost is Claude Code's own figure.
- **Usage limits:** the 5-hour limit voided 47 of the first 175 main runs: 12 best-effort plugin runs, and all 35
  built-in `/code-review` runs, which Claude Code reported as successes with 0 tokens. All 47 were rerun after the
  limit reset and are recorded in `2026-10-29-015736/voided.jsonl`. That is over the 20% kill line; Ryan ruled to
  rerun and go on (§5.55).
- **Small apps.** Each of the 15 apps is 2 to 11 files and 18 to 354 lines; treat the shares as indicative.

## Harness defects found while running it

Each was fixed with a test that fails on the old code (`plugin/tests/cases_3.py`, "5.2.4 benchmark").

1. The agent counter looked up a run's transcript by session id; every headless run inherits the parent's id, so
   it read an arbitrary run's file (a run that launched 10 agents read as 0). It now uses the run's own folder.
2. A usage limit that Claude Code reports as a success (0 tokens, the limit notice as the reply) was scored as a
   clean "found nothing" run. It is now a failed, voided run.
3. On a clean twin, a finding labelled trivial counted as a false alarm. Now only a finding judged wrong, or a cited
   one not yet labelled, does.

Found by a blind review of the harness (lite tier), all fixed before these numbers:

4. (High) A finding that restated a planted bug was labelled and counted again as a confirmed bug.
5. (High) The labeller blindness gap above.
6. (High) The cost-per-bug interval could be computed over NaN values when resamples confirmed nothing; such
   resamples now count as unbounded.
7. (High) A review that discussed a quota or rate-limit bug, with 0 tokens reported, would have been taken for a
   limit notice and voided; only a reply that is nothing but a short limit notice is now.
8. (Medium) A real failure could be taken for a limit void when a number in its metadata contained 429; only the
   failure's own text is read now.
9. (Medium) A failure rerun by hand was counted as a limit void and dropped from the completion rate.
10. (Low) The false-alarm upper bound used one-sided 95% for zero false alarms and 97.5% otherwise; it is one-sided
    95% throughout (the rule of three for zero, Clopper-Pearson otherwise).
11. (Low) The statistics could read scores older than the latest labels; they score again when the labels are newer.
12. (Low) `rerun` crashed on a run folder made before it recorded its settings (`run.json`); it now says why and stops.

None of 7 to 9 changed this run's numbers: all 47 voids were limit notices, and no run was rerun by hand.

## Spend

$150.94 by Claude Code's own cost reports: $122.41 for the scored main runs, $22.34 for the extra clean apps, $2.11
for runs voided by the limit, and $4.08 for the smoke runs before the main run. About $1.50 more went on one extra
clean-app run that was stopped by hand and discarded; its cost was not recorded. Labelling used 91 agent runs (72
labellers, 12 tiebreakers, 7 for the recheck) inside the maintainer's session; their cost is not in these figures.

## Files

- `2026-10-29-015736/` (main tasks) and `2026-10-29-093654/` (extra clean apps): each arm's reply (`output.md`)
  and findings (`findings.jsonl`) per run, `meta.json` (cost, tokens, time, agents launched), `results.json` (the
  scorer's output), `labels.json` and `labels-detail.json`, `run.json` (settings), `voided.jsonl`, and
  `labelling/` (the packets as the labellers saw them, the id map, the controls, each labeller's labels and the
  agreement). The long-form review reports (`last-review.md`) are left out.
- `recheck/`: the opaque-name packets, the name map, the sample and the relabel.
- `stats.md`, `stats.json`: the statistics above.
- Tools: `eval/deathmatch.py` (runs and scores), `eval/label.py` (blind labelling and the recheck),
  `eval/bench_stats.py` (statistics).
