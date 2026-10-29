# 5.2.4 benchmark statistics

Run folders: 2026-10-29-015736, 2026-10-29-093654. Runs voided by a usage limit and run again: 47.
Labeller agreement: 2026-10-29-015736: 865 of 945 agreed, kappa 0.861, labeller A right on 24 of 24 known-truth controls (real 12 of 12, wrong 12 of 12), labeller B right on 24 of 24 known-truth controls (real 12 of 12, wrong 12 of 12); 2026-10-29-093654: 196 of 205 agreed, kappa 0.886.

| Arm | Completed | Planted recall (95% CI) | Assessed findings: real / trivial / wrong | Real and actionable | Clean runs with a false alarm (95% upper) | Cost | Confirmed bugs | Cost per confirmed (95% CI) | Median time (s) | Runs that launched agents |
|---|---|---|---|---|---|---|---|---|---|---|
| curmudgeon | 43 of 43 | 222 of 245 (0.86 to 0.96) | 277 / 6 / 6 | 96% | 6 of 23 (48%) | $61.26 | 499 | $0.123 (0.107 to 0.146) | 273.2 | 100% (43 known) |
| cc-code-review | 43 of 43 | 76 of 245 (0.24 to 0.42) | 220 / 71 / 16 | 72% | 9 of 23 (62%) | $4.23 | 296 | $0.014 (0.012 to 0.017) | 37.5 | 0% (43 known) |
| code-review | 43 of 43 | 33 of 245 (0.06 to 0.22) | 114 / 10 / 7 | 86% | 3 of 23 (34%) | $3.89 | 146 | $0.027 (0.020 to 0.039) | 21.9 | 0% (43 known) |
| code-review-best | 43 of 43 | 64 of 245 (0.17 to 0.34) | 42 / 9 / 0 | 82% | 0 of 23 (13%) | $43.10 | 106 | $0.407 (0.320 to 0.577) | 73.8 | 100% (43 known) |
| curmudgeon-lite | 43 of 43 | 222 of 245 (0.87 to 0.95) | 215 / 10 / 3 | 94% | 1 of 23 (22%) | $32.27 | 437 | $0.074 (0.064 to 0.088) | 235.6 | 100% (43 known) |

Real and actionable findings by severity (share of each arm's assessed findings):

| Arm | Critical | High | Medium | Low |
|---|---|---|---|---|
| curmudgeon | 1 (0%) | 22 (8%) | 150 (52%) | 104 (36%) |
| cc-code-review | 2 (1%) | 28 (9%) | 94 (31%) | 96 (31%) |
| code-review | 3 (2%) | 43 (33%) | 42 (32%) | 25 (19%) |
| code-review-best | 1 (2%) | 9 (18%) | 22 (43%) | 10 (20%) |
| curmudgeon-lite | 1 (0%) | 16 (7%) | 118 (52%) | 80 (35%) |

Paired against curmudgeon (same task and repeat; positive means curmudgeon found more or cost more):

| Arm | Pairs | Confirmed bugs per run, difference (95% CI) | Runs: base better / other better / tied | Cost per run, difference (95% CI) |
|---|---|---|---|---|
| cc-code-review | 43 | +4.72 (2.81 to 6.81) | 35 / 8 / 0 | +1.326 (1.229 to 1.430) |
| code-review | 43 | +8.21 (6.44 to 10.07) | 41 / 2 / 0 | +1.334 (1.239 to 1.436) |
| code-review-best | 43 | +9.14 (7.35 to 11.07) | 41 / 0 / 2 | +0.422 (0.316 to 0.524) |
| curmudgeon-lite | 43 | +1.44 (0.74 to 2.14) | 27 / 8 / 8 | +0.674 (0.621 to 0.727) |
