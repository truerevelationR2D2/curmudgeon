---
type: regex
target: { source: file, path: app.js }
pattern: 'for \(let i = 0; i <= items\.length; i\+\+\) t \+= items\[i\]\.price;'
arm: both
---
The file itself still holds the bug at the end, however a model might have changed it: python, node, patch, git apply,
awk or git checkout edits all fail this case, not only the shell forms no-bash-edit names (5.8.1 C8).
