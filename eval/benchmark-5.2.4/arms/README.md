# Three plain-Claude arms (29 Oct 2026; 03 §5.56 batch 3)

These runs split the checklist's effect from the process's, as the combined review of 29 Oct 2026 asked (item 20):
plain Claude with no plugin, plain Claude given `rubrics.md`, and plain Claude given Curmudgeon's quote check. Same
seven tasks as the 5.2.4 benchmark (four planted apps, three clean twins), five runs each: 105 runs in
`2026-10-29-211707/`, and a two-run trial before it in `2026-10-29-211608-trial/`. The model is the harness default
(`run.json` records none).

| Arm | Runs | Planted bugs found | Cost |
|---|---|---|---|
| Plain Claude | 35 | 83 of 245 (34%) | $3.87 |
| Plain Claude + quote check | 35 | 102 of 245 (42%) | $3.57 |
| Plain Claude + rubric | 35 | 166 of 245 (68%) | $5.31 |

Total $12.75, plus $0.27 for the trial. Scored with the answer key's widened E02 patterns (scores before the change in
`results.before-key.json`: 83, 99 and 165).

**Not measured yet: precision.** 614 findings matched no planted bug and are unlabelled (217, 53 and 344 by arm), so
these arms have no false-alarm or confirmed-bug figures, and they are not in `stats.md`. They need the same blind
labelling as the benchmark's other arms before they can be compared on anything but planted recall.
