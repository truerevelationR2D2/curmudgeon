---
type: regex
target: { source: file, path: .critic/scan/report.json }
pattern: '"mutation":\s*\{\s*"state":\s*"blocked"'
arm: with-only
---
The scan asked for mutation testing and reported it blocked (the test command came only from the repository's own
rules file), so a run that never reached mutation testing can't pass this case (audit V05).
