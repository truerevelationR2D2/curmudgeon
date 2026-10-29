# 5.2.4 benchmark statistics

Run folders: 2026-10-29-015736, 2026-10-29-093654. Runs voided by a usage limit and run again: 47. Findings left out as second reports of a planted bug already counted: 60.
Labeller agreement: 2026-10-29-015736: 865 of 945 agreed, kappa 0.861, labeller A right on 24 of 24 known-truth controls (real 12 of 12, wrong 12 of 12), labeller B right on 24 of 24 known-truth controls (real 12 of 12, wrong 12 of 12); 2026-10-29-093654: 196 of 205 agreed, kappa 0.886.

| Arm | Completed | Planted recall (95% CI) | Assessed findings: real / trivial / wrong | Real and actionable | Clean runs with a false alarm (95% upper) | Cost | Confirmed bugs | Cost per confirmed (95% CI) | Median time (s) | Runs that launched agents |
|---|---|---|---|---|---|---|---|---|---|---|
| curmudgeon | 43 of 43 | 222 of 245 (0.86 to 0.96) | 248 / 6 / 6 | 95% | 6 of 23 (45%) | $61.26 | 470 | $0.130 (0.115 to 0.152) | 273.2 | 100% (43 known) |
| cc-code-review | 43 of 43 | 76 of 245 (0.24 to 0.42) | 215 / 69 / 16 | 72% | 9 of 23 (58%) | $4.23 | 291 | $0.015 (0.012 to 0.018) | 37.5 | 0% (43 known) |
| code-review | 43 of 43 | 33 of 245 (0.06 to 0.22) | 114 / 10 / 7 | 86% | 3 of 23 (30%) | $3.89 | 146 | $0.027 (0.020 to 0.039) | 21.9 | 0% (43 known) |
| code-review-best | 43 of 43 | 64 of 245 (0.17 to 0.34) | 35 / 9 / 0 | 80% | 0 of 23 (13%) | $43.10 | 99 | $0.435 (0.343 to 0.618) | 73.8 | 100% (43 known) |
| curmudgeon-lite | 43 of 43 | 222 of 245 (0.87 to 0.95) | 199 / 9 / 3 | 94% | 1 of 23 (19%) | $32.27 | 421 | $0.077 (0.067 to 0.090) | 235.6 | 100% (43 known) |

Real and actionable findings by severity (share of each arm's assessed findings):

| Arm | Critical | High | Medium | Low |
|---|---|---|---|---|
| curmudgeon | 1 (0%) | 18 (7%) | 131 (50%) | 98 (38%) |
| cc-code-review | 2 (1%) | 25 (8%) | 93 (31%) | 95 (32%) |
| code-review | 3 (2%) | 43 (33%) | 42 (32%) | 25 (19%) |
| code-review-best | 1 (2%) | 8 (18%) | 18 (41%) | 8 (18%) |
| curmudgeon-lite | 1 (0%) | 16 (8%) | 106 (50%) | 76 (36%) |

Paired against curmudgeon (same task and repeat; positive means curmudgeon found more or cost more):

| Arm | Pairs | Confirmed bugs per run, difference (95% CI) | Runs: base better / other better / tied | Cost per run, difference (95% CI) |
|---|---|---|---|---|
| cc-code-review | 43 | +4.16 (2.47 to 6.00) | 34 / 9 / 0 | +1.326 (1.229 to 1.430) |
| code-review | 43 | +7.53 (6.00 to 9.09) | 41 / 2 / 0 | +1.334 (1.239 to 1.436) |
| code-review-best | 43 | +8.63 (7.02 to 10.33) | 41 / 0 / 2 | +0.422 (0.316 to 0.524) |
| curmudgeon-lite | 43 | +1.14 (0.53 to 1.74) | 24 / 9 / 10 | +0.674 (0.621 to 0.727) |
