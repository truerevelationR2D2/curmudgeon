**CONCERNS** · Counts: 0 Critical, 0 High, 2 Medium, 1 Low

I read all four config files and traced each finding by reading only. No server was started.

**Medium**
- **`F-0ef9e4d9`, `.mcp.json:17`:** the `search` server is a stdio server, so it ignores the `headers` block that holds its token.
  - If a user exports `SEARCH_TOKEN`, the server starts with no credential. Every call then fails auth, or it runs unauthenticated while the config looks authenticated.
  - Fix: pass the token through `env`, or make it an http server.
- **`F-07b1afa9`, `.cursor/mcp.json:3`:** the file uses `${DOCS_API_KEY}`, but Cursor expects `${env:DOCS_API_KEY}`, as `.vscode/mcp.json:6` already does for `LINT_TOKEN`.
  - Cursor would pass the literal string as the key.
  - This rests on the reviewer's recollection of Cursor's docs, which it couldn't open. Check the docs before changing it.

**Low**
- **`F-2d6589cf`, `.claude/settings.json:4`:** the bare `Read` allow rule approves reads of any file without a prompt.
  - An issue body that tells the agent to read `~/.aws/credentials` would go through silently.
  - Fix: drop it or scope it, and add deny rules for secret paths.

**Nit**
- `.vscode/mcp.json:6`: the committed config turns on debug logging for a server that is handed `LINT_TOKEN`.

**Not checked or not reviewed**
- The scripted scan covered 0 files; it skipped these dotfile configs, so there is no scan evidence.
- The two Mediums were not blind-verified, because the lite tier verifies only Critical and High. That is why their confidence is "possible".
- I didn't confirm which variables the third-party servers read, or whether they log their environment at debug level.

I ran only the tally steps, so I did not run the spot-check or `critic_ledger.py stamp`. I wrote the teardown to `.critic/last-review.md`, which is the review's own output folder. No project files changed.

- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.