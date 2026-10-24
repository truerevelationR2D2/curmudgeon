# Rule files

Add a check here without touching the plugin's code. Each `*.json` file in this folder (built-in rules), or in a
project's `.critic/rules/` folder (that project's own rules), holds a list of rules:

```json
[
  {
    "id": "debugger-left",
    "severity": "WARN",
    "area": "errors",
    "pattern": "^\\s*debugger\\s*;?\\s*$",
    "message": "debugger statement left in shipped code",
    "files": ["*.js", "*.ts"]
  }
]
```

- **id:** lowercase letters, digits and dashes, used once. Its rows are reported as `rule-<id>`, so a rule file can never pose as one of the built-in checks.
- **severity:** `FAIL`, `WARN` or `NOTE`.
- **area:** one of safety, errors, state, async, perf, a11y, layout, domain, html, theming, ux, structure, deps.
- **pattern:** a Python regular expression, matched one line at a time, at most 300 characters.
- **message:** what's wrong and why it matters, in plain words.
- **files:** optional list of filename patterns. Leave it out to match every source file. Config files (`.yml`, `.yaml`, `.sql`, `.toml`, Dockerfiles and anything under `.github/`) are read only by a rule whose patterns name them, for example `["*.yml", "*.yaml"]` or `[".github/*"]`, so a rule written for code never fires on configuration.

Rules are data, never code: nothing in a rule file runs. A broken rule or file is reported, not run, and never stops
the scan. A project's rule files are read only when they are plain files of at most 256 KB (up to 200 rules each,
and at most 50 files, 2 MB and 2,000 rules in all), run in a separate process with a 20-second limit, and report at
most 50 matches per rule and 2,000 in all. A project's rules can warn but never fail: a `FAIL` there is reported as
`WARN`, so only the plugin's own checks become automatic findings. Lines
longer than 2,000 characters are skipped. Add a test for every rule you contribute.
