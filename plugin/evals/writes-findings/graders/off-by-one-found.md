---
type: regex
target: { source: file, path: .critic/findings.jsonl }
pattern: '<=\s*items\.length|off.by.one|out of (bounds|range)|undefined\.price'
flags: i
---
