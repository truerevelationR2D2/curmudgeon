# 5.2.4 benchmark statistics

Run folders: 2026-10-29-015736, 2026-10-29-093654. Runs voided by a usage limit and run again: 47. Findings left out as second reports of a planted bug already counted: 60.
Labeller agreement: 2026-10-29-015736: 865 of 945 agreed, kappa 0.861, labeller A right on 24 of 24 known-truth controls (real 12 of 12, wrong 12 of 12), labeller B right on 24 of 24 known-truth controls (real 12 of 12, wrong 12 of 12); 2026-10-29-093654: 196 of 205 agreed, kappa 0.886.

| Arm | Completed | Planted recall (95% CI) | Assessed findings: real / trivial / wrong | Real and actionable | Clean runs with a false alarm (95% upper) | Cost | Confirmed bugs | Cost per confirmed (95% CI) | Median time (s) | Runs that launched agents |
|---|---|---|---|---|---|---|---|---|---|---|
| curmudgeon | 43 of 43 | 225 of 245 (0.86 to 1.00) | 245 / 6 / 6 | 95% | 6 of 23 (45%) | $61.26 | 470 | $0.130 (0.103 to 0.194) | 273.2 | 100% (43 known) |
| cc-code-review | 43 of 43 | 76 of 245 (0.20 to 0.68) | 215 / 69 / 16 | 72% | 9 of 23 (58%) | $4.23 | 291 | $0.015 (0.011 to 0.022) | 37.5 | 0% (43 known) |
| code-review | 43 of 43 | 34 of 245 (0.06 to 0.27) | 113 / 10 / 7 | 86% | 3 of 23 (30%) | $3.89 | 146 | $0.027 (0.015 to 0.077) | 21.9 | 0% (43 known) |
| code-review-best | 43 of 43 | 64 of 245 (0.14 to 0.48) | 35 / 9 / 0 | 80% | 0 of 23 (13%) | $43.10 | 99 | $0.435 (0.307 to 0.915) | 73.8 | 100% (43 known) |
| curmudgeon-lite | 43 of 43 | 222 of 245 (0.85 to 1.00) | 199 / 9 / 3 | 94% | 1 of 23 (19%) | $32.27 | 421 | $0.077 (0.060 to 0.117) | 235.6 | 100% (43 known) |

Real and actionable findings by severity (share of each arm's assessed findings):

| Arm | Critical | High | Medium | Low |
|---|---|---|---|---|
| curmudgeon | 1 (0%) | 18 (7%) | 128 (50%) | 98 (38%) |
| cc-code-review | 2 (1%) | 25 (8%) | 93 (31%) | 95 (32%) |
| code-review | 3 (2%) | 43 (33%) | 41 (32%) | 25 (19%) |
| code-review-best | 1 (2%) | 8 (18%) | 18 (41%) | 8 (18%) |
| curmudgeon-lite | 1 (0%) | 16 (8%) | 106 (50%) | 76 (36%) |

Planted recall by app (the interval above resamples these apps, then the runs within each):

| Arm | suite1 | suite2 | suite3 | suite4 |
|---|---|---|---|---|
| curmudgeon | 79 of 80 | 116 of 135 | 10 of 10 | 20 of 20 |
| cc-code-review | 29 of 80 | 27 of 135 | 4 of 10 | 16 of 20 |
| code-review | 10 of 80 | 17 of 135 | 0 of 10 | 7 of 20 |
| code-review-best | 12 of 80 | 38 of 135 | 1 of 10 | 13 of 20 |
| curmudgeon-lite | 77 of 80 | 115 of 135 | 10 of 10 | 20 of 20 |

Paired against curmudgeon (same task and repeat; positive means curmudgeon found more or cost more):

| Arm | Pairs | Confirmed bugs per run, difference (95% CI) | Runs: base better / other better / tied | Cost per run, difference (95% CI) |
|---|---|---|---|---|
| cc-code-review | 43 | +4.16 (0.67 to 7.67) | 34 / 9 / 0 | +1.326 (1.132 to 1.515) |
| code-review | 43 | +7.53 (4.31 to 10.44) | 41 / 2 / 0 | +1.334 (1.147 to 1.516) |
| code-review-best | 43 | +8.63 (5.26 to 11.79) | 41 / 0 / 2 | +0.422 (0.200 to 0.597) |
| curmudgeon-lite | 43 | +1.14 (0.45 to 1.80) | 24 / 9 / 10 | +0.674 (0.590 to 0.751) |
