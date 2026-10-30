# Death match, 27 October 2026

Curmudgeon 5.2 (`1727526`, the review code of the 5.2 build) against two orchestration plugins Ryan named, on the
same seven eval tasks as the 24 October match (four apps with planted bugs, three clean twins), three runs each,
Sonnet 5.5, every other installed plugin switched off. One scorer (`deathmatch.py`) for every arm: a planted bug counts
only when a finding points at its lines and says what is wrong. Every other finding (816 distinct) was labelled real,
trivial or wrong by independent models that read the code, saw no answer keys and were not told which tool wrote it.

| Arm | Planted bugs found | Other real bugs | Trivial | Wrong | Real share of all findings | Cost per run | Time per run |
|---|---|---|---|---|---|---|---|
| Curmudgeon 5.2 | **130 of 147 (88%)** | 114 | 36 | **1** | **87%** (244 of 281) | $1.52 | 311 s |
| BVarvill orchestrator-agent-plugin (its `reviewer` agent) | 84 of 147 (57%) | 65 | 59 | 8 | 69% (149 of 216) | $0.13 | 32 s |
| rbenzing Orchestrator (its `code-reviewer` agent) | 83 of 147 (56%) | 159 | 46 | 51 | 71% (242 of 339) | $0.21 | 56 s |
| rbenzing Orchestrator, with PowerShell | 59 of 147 (40%) | 186 | 41 | 50 | 73% (245 of 336) | $0.21 | 61 s |

Counts are per run, summed over three runs. "Trivial" includes the Low findings Curmudgeon rates as Low on purpose.

Notes:
- Neither orchestrator is mainly a reviewer: both build software through several agents, and each ships one review
  agent, which is what each arm called. BVarvill's reviewer reviews a pull request against an order file, so its task
  was committed as a branch over an empty base and the prompt gave the intent; rbenzing's code reviewer was called on
  the folder.
- rbenzing's scripts are PowerShell. The first arm ran with no PowerShell in the workspace (its script calls failed);
  the second had PowerShell 7.5.4 installed and allowed for its scripts. With it, the agent spent its effort on its own
  workflow scripts and found fewer planted bugs. Its agents also ask for a `launch-process` tool the plugin does not
  define, and its settings ask for an "allow all" permission mode.
- Curmudgeon found 134 of 147 in the 24 October match (5.0.0) and 130 here (5.2): within run-to-run variation on the
  same tasks; its wrong findings went from 0 to 1 and its real share from 79% to 87%.
- Both orchestrators were cloned at `rbenzing/Orchestrator@ac9ed8b` (Apache-2.0) and
  `BVarvill/orchestrator-agent-plugin@582dc1f` (MIT), kept outside this repository, and loaded with `--plugin-dir`
  (`DM_ORCH_RBENZING`, `DM_ORCH_BVARVILL`).
