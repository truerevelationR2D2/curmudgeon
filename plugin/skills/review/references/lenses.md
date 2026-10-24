# Lens rubric rows

One section per scripted lens. Read only the sections your brief names: the job plan picks them from the payload (critic_plan.py).

## Tests of the tests

| Component | Fail condition (what AI code defaults miss) | Inspect | Remediation requirement |
| --- | --- | --- | --- |
| **Tests of the tests** | A test that checks nothing; an assert that is always true (`assert (x, "msg")`); two tests with one name, so one never runs; a broad `except` that swallows the failure; a skip with no reason; tests that pass by timing, randomness or the clock | Every test the change adds or touches, and the tests that should cover the changed code. The scan's `tests` rows (`scan_tests.py`) point at the mechanical cases; judge the rest: does the test fail if the behaviour breaks? Run it against a deliberately broken copy in your workspace when you can | Each test asserts the behaviour it names and fails when it breaks; one name per test; catch only the error expected, or use the framework's raises check; a skip says why and until when |

## CI and supply chain

| Component | Fail condition (what AI code defaults miss) | Inspect | Remediation requirement |
| --- | --- | --- | --- |
| CI and supply chain | Untrusted text (PR or issue titles, comments, branch names, commit messages) pasted into a `run:` script; `pull_request_target` or `workflow_run` running the PR's own code with secrets; an `if:` that is always true; no `permissions:` on a risky trigger; third-party actions by tag; `curl | sh`; `--extra-index-url`; images with no fixed tag | Every workflow trigger and what can set its inputs; every checkout's `ref`; every `${{ }}` inside `run:`; every download that is executed. The scan's `supply-chain` rows point at the mechanical cases | Untrusted values go through `env:` and are quoted; privileged triggers never run PR code; least-privilege `permissions:`; actions pinned by SHA (or in `actions.lock`); downloads checked by hash before they run |

## Agent and MCP configuration

| Component | Fail condition (what AI code defaults miss) | Inspect | Remediation requirement |
| --- | --- | --- | --- |
| Agent and MCP configuration | `enableAllProjectMcpServers` committed; literal tokens in a server's `env` or `headers`; servers started by `curl \| sh` or privileged containers; `npx`/`uvx` with no version; allow rules for a whole server or every command | `.mcp.json`, `.claude/settings*.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, `claude_desktop_config.json`. Remember a committed `.mcp.json` starts its servers without a prompt in `claude -p`, SDK and cloud runs | Credentials from environment variables; pinned packages; least-privilege containers; allow rules naming specific tools; servers approved one by one |

## Release and rollback

| Component | Fail condition (what AI code defaults miss) | Inspect | Remediation requirement |
| --- | --- | --- | --- |
| Release and rollback | A migration that locks a busy table (an index built without `CONCURRENTLY`, a constraint validated in place); `NOT NULL` added with no default; a migration with no way back; a column dropped or renamed while old code still reads it; a deploy with no rollback step | Every migration in the change, which tables already hold data, and whether the code and the schema can run one version apart | Expand, migrate, contract: add nullable or with a default, backfill, then tighten; indexes `CONCURRENTLY`; constraints `NOT VALID` then validated; every migration reversible or marked one-way on purpose |

## Requirements and intent

| Component | Fail condition (what AI code defaults miss) | Inspect | Remediation requirement |
| --- | --- | --- | --- |
| Requirements and intent | Behaviour that contradicts a written requirement; a requirement nothing tests; a test that claims a requirement nobody wrote; a "requirement" the reviewer made up and presented as written | The requirements documents, the scan's `requirements` rows and `.critic/scan/requirements.md` (each requirement and the tests citing it), and the stated intent | Each finding about intent names its basis: stated (with the file:line) or inferred (with why). Inferred findings stay at Medium or below |

## Operations

| Component | Fail condition (what AI code defaults miss) | Inspect | Remediation requirement |
| --- | --- | --- | --- |
| Operations | Secrets in logs; DEBUG left on in production settings; alerts with no runbook, or a runbook link to nothing; containers with no probes or limits | Logging calls and what they pass; settings files by environment; alert rules and their annotations; deployment manifests | Log that a secret exists, never its value; per-environment settings with safe defaults; every alert names a runbook that exists; probes and limits set on purpose |
