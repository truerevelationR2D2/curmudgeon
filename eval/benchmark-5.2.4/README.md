# The 5.2.4 benchmark (29 October 2026)

Asked for in ruling §5.53: repeat the death match against Anthropic's code-review options with a stronger design,
keep the old tasks so the numbers stay comparable, report the code-review plugin's agent-launch behaviour, keep
planted-bug detection separate from independently judged real-world findings, and report the share of findings
independently confirmed as actionable, by severity. Budget rulings §5.54 and §5.55.

Every number below is recomputed by `python3 eval/bench_stats.py eval/benchmark-5.2.4/2026-10-29-015736
eval/benchmark-5.2.4/2026-10-29-093654` (no model calls); `stats.md` and `stats.json` here are its output.

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

| Arm | Planted bugs found (95% CI) | Findings judged real / trivial / wrong | Real and actionable | Clean runs with a false alarm (95% upper bound) | Cost per run | Cost per confirmed bug (95% CI) | Median time | Runs that launched agents |
|---|---|---|---|---|---|---|---|---|
| Curmudgeon, full | **222 of 245, 91%** (86% to 96%) | 277 / 6 / 6 | 96% | 6 of 23 (48%) | $1.42 | $0.123 ($0.107 to $0.146) | 273 s | 43 of 43 |
| Curmudgeon, lite | **222 of 245, 91%** (87% to 95%) | 215 / 10 / 3 | 94% | 1 of 23 (22%) | $0.75 | $0.074 ($0.064 to $0.088) | 236 s | 43 of 43 |
| Built-in `/code-review` | 76 of 245, 31% (24% to 42%) | 220 / 71 / 16 | 72% | 9 of 23 (62%) | $0.10 | $0.014 ($0.012 to $0.017) | 38 s | not visible (see below) |
| Code-review plugin, best effort | 64 of 245, 26% (17% to 34%) | 42 / 9 / 0 | 82% | 0 of 23 (13%) | $1.00 | $0.407 ($0.320 to $0.577) | 74 s | 43 of 43 |
| Code-review plugin, as it runs | 33 of 245, 13% (6% to 22%) | 114 / 10 / 7 | 86% | 3 of 23 (34%) | $0.09 | $0.027 ($0.020 to $0.039) | 22 s | **0 of 43** |

Real and actionable findings by severity, as a share of each arm's judged findings:

| Arm | Critical | High | Medium | Low |
|---|---|---|---|---|
| Curmudgeon, full | 1 (0.3%) | 22 (8%) | 150 (52%) | 104 (36%) |
| Curmudgeon, lite | 1 (0.4%) | 16 (7%) | 118 (52%) | 80 (35%) |
| Built-in `/code-review` | 2 (1%) | 28 (9%) | 94 (31%) | 96 (31%) |
| Code-review plugin, best effort | 1 (2%) | 9 (18%) | 22 (43%) | 10 (20%) |
| Code-review plugin, as it runs | 3 (2%) | 43 (33%) | 42 (32%) | 25 (19%) |

Paired on the same task and run (43 pairs each), Curmudgeon full against:

| Other arm | Confirmed bugs per run, full minus other (95% CI) | Runs full did better / worse / tied | Cost per run, full minus other (95% CI) |
|---|---|---|---|
| Curmudgeon, lite | +1.44 (0.74 to 2.14) | 27 / 8 / 8 | +$0.67 ($0.62 to $0.73) |
| Built-in `/code-review` | +4.72 (2.81 to 6.81) | 35 / 8 / 0 | +$1.33 ($1.23 to $1.43) |
| Code-review plugin, best effort | +9.14 (7.35 to 11.07) | 41 / 0 / 2 | +$0.42 ($0.32 to $0.52) |
| Code-review plugin, as it runs | +8.21 (6.44 to 10.07) | 41 / 2 / 0 | +$1.33 ($1.24 to $1.44) |

What the numbers say:

1. **Planted bugs.** Both Curmudgeon tiers found 91%; the best of the others found 31%. The lite tier found
   exactly as many planted bugs as the full tier at 53% of its cost.
2. **The code-review plugin's agent launch.** As it runs, the plugin launched no agent in any of its 43 runs,
   though its instructions name several; it read the diff itself and replied in about 20 seconds. Given the facts
   its first step asks for and told to follow its steps, it launched agents in all 43 runs (8.8 a run) and found
   twice as many planted bugs (64 against 33), at eleven times the cost.
3. **Real findings beyond the plants.** Of the findings that matched no planted bug, the labellers judged 96%
   (full) and 94% (lite) of Curmudgeon's real and actionable, against 72% to 86% for the others. Most of
   Curmudgeon's are Medium.
4. **Full against lite.** Full found 1.44 more confirmed bugs a run for $0.67 more, about $0.47 per extra
   confirmed bug, and raised a false alarm on more clean runs (6 of 23 against 1 of 23).
5. **False alarms.** Only the best-effort plugin raised none on the clean apps (0 of 23; the 95% upper bound is
   13%). With 23 clean runs per arm, every bound here is wide.

## How findings were judged

- **Planted bugs** are matched by script against the answer keys (`eval/keymatch.py`): a finding counts only when
  it points at the planted lines and states the planted defect. Nothing here relabels them.
- **Every other finding** (1,150 in all) was judged blind by two labellers (`eval/label.py`, brief in
  `eval/labeller-brief.md`): Sonnet 5.5 agents that saw only the finding's words, with markdown removed, and a bare
  copy of the app outside `eval/`, never the arm, the run or the answer key. Verdicts: real, trivial (true but not
  worth acting on), wrong, or none (a heading or note, not a finding; left out of every share). Where the two
  disagreed on the verdict or on actionable, a third labeller (Opus 5.5) decided, seeing neither label. When they
  agreed but differed on severity, the lower was taken.
- **Agreement:** 865 of 945 (92%, Cohen's kappa 0.86) on the main tasks and 196 of 205 (96%, kappa 0.89) on the
  extra clean apps; 89 ties went to the tiebreaker.
- **Known-truth controls,** mixed in blind: 12 planted-bug findings shown against their own app (truth: real) and
  against the clean twin where the bug is fixed (truth: wrong). Both labellers judged all 24 correctly.
- **False alarm** on a clean app: a finding judged wrong, or one that cites a line and was not labelled. A
  finding judged trivial or none is not a false alarm.
- **Confirmed bugs** = planted bugs found + findings judged real and actionable.

## Limits

- **Findings are counted, not de-duplicated across a run.** A reviewer that reports one bug twice gets two
  confirmed findings. Curmudgeon merges duplicates before it reports; the other arms were not checked for this,
  so the count can favour a reviewer that repeats itself.
- **The labellers are models,** not people. The controls and the high agreement show they can tell a planted bug
  from a fixed one; they don't prove every judgement.
- **The built-in `/code-review`** runs as a background subagent; Claude Code reported 0 tokens for it and its
  transcript shows no agent calls, so its agent use is not visible here. Its cost is Claude Code's own figure.
- **Usage limits:** the 5-hour limit voided 47 of the first 175 main runs: 12 best-effort plugin runs, and all 35
  built-in `/code-review` runs, which Claude Code reported as successes with 0 tokens. All 47 were rerun after the
  limit reset and are recorded in `2026-10-29-015736/voided.jsonl`. That is over the 20% kill line; Ryan ruled to
  rerun and go on (§5.55). The scorer now treats a 0-token run whose reply is empty or a limit message as failed.
- **Small apps.** Each of the 15 apps is 2 to 11 files and 18 to 354 lines; treat the shares as indicative.

## Spend

$150.94 by Claude Code's own cost reports: $122.41 for the scored main runs, $22.34 for the extra clean apps, $2.11
for runs voided by the limit, and $4.08 for the smoke runs before the main run. About $1.50 more went on one extra
clean-app run that was stopped by hand and discarded; its cost was not recorded. Labelling used 84 agent runs (72
labellers, 12 tiebreakers) inside the maintainer's session; their cost is not in these figures.

## Files

- `2026-10-29-015736/` (main tasks) and `2026-10-29-093654/` (extra clean apps): each arm's reply (`output.md`)
  and findings (`findings.jsonl`) per run, `meta.json` (cost, tokens, time, agents launched), `results.json` (the
  scorer's output), `labels.json` and `labels-detail.json`, `run.json` (settings), and `labelling/` (the blind
  packets, the id map, the controls, each labeller's labels and the agreement). The long-form review reports
  (`last-review.md`) are left out.
- `stats.md`, `stats.json`: the statistics above.
- Tools: `eval/deathmatch.py` (runs and scores), `eval/label.py` (blind labelling), `eval/bench_stats.py`
  (statistics).
