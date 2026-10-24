# Death match, 24 October 2026

Curmudgeon 5.0.0 (`138f87e`) against plain Claude, Anthropic's code-review plugin, Claude Code's built-in `/code-review`
and Semgrep, on the seven eval tasks (four apps with planted bugs, three clean twins), three runs each: 105 runs, all
on Sonnet 5.5 except Semgrep (no model). Every arm ran with every other installed plugin switched off. One scorer
(`deathmatch.py`) for every arm: a planted bug counts only when a finding points at its lines and says what is wrong.
Every other finding (613 distinct) was labelled real, trivial or wrong by independent models that read the code, saw
no answer keys and were not told which tool wrote it.

| Arm | Planted bugs found | Other real bugs | Trivial | Wrong | Real share of all findings | Cost per run | Time per run |
|---|---|---|---|---|---|---|---|
| Curmudgeon 5.0.0 | **134 of 147 (91%)** | 118 | 68 | **0** | **79%** (252 of 320) | $1.57 | 278 s |
| Plain Claude (Read, Grep, Glob) | 84 of 147 (57%) | 122 | 89 | 3 | 69% (206 of 298) | $0.11 | 32 s |
| Anthropic code-review plugin | 44 of 147 (30%) | 10 | 28 | 1 | 65% (54 of 83) | $0.10 | 21 s |
| Claude Code built-in `/code-review` | 44 of 147 (30%) | 73 | 78 | 4 | 59% (117 of 199) | $0.10 | 31 s |
| Semgrep (its own javascript and html rules) | 6 of 147 (4%) | 18 | 18 | 39 | 30% (24 of 81) | $0 | 28 s |

Counts are per run, summed over three runs. "Trivial" includes the Low findings Curmudgeon rates as Low on purpose.

Notes:
- Cited lines that do not exist in the named file: built-in `/code-review` 27% (53 of 199), plain Claude 10% (34 of 336),
  Curmudgeon, the code-review plugin and Semgrep 0%. A finding at a wrong line gets no credit for a planted bug.
- The code-review plugin reviews GitHub pull requests. Here each task was a branch over an empty base and the prompt
  said to read `git diff main...HEAD` and print the comment. Run headless, it chose not to start its five agents.
- Semgrep ran offline with `--metrics=off` on Semgrep's published rules (semgrep/semgrep-rules, Semgrep Rules License
  v1.0), kept outside this repository.
- Scorer fixes made while scoring, each applied to every arm: GitHub-style `file L8-14` citations, indented sub-bullets
  kept with their item, and a structured finding's claim including its evidence, as a free-form item's does.
