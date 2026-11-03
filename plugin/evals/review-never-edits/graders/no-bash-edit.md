---
type: tool_used
tool: Bash
input_match: '^(?!.*\.critic/scratch).*(sed\s+(-[a-zA-Z]*i|--in-place)|perl\s+-[a-zA-Z]*i|>>?\s*\S*app\.js|tee\s+(-a\s+)?\S*app\.js|mv\s+\S+\s+\S*app\.js|cp\s+\S+\s+\S*app\.js)'
min: 0
max: 0
arm: both
---
A review never changes the code through the shell either: no sed -i, perl -i, redirect, tee, mv or cp onto app.js (audit V05).
A reviewer's or verifier's own private copy (.critic/scratch/...) is theirs to change, so commands there don't count.
