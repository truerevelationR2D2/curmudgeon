**CONCERNS** · Counts: 0 Critical, 0 High, 2 Medium, 0 Low

I reviewed the four MCP and settings config files with three blind reviewers and one blind verifier. Both findings were confirmed by all three reviewers and by the verifier. Nothing was run: the findings are traced from the config files and from the clients' documented syntax, and I did not start Claude Code, Cursor, VS Code or Docker.

1. **`.mcp.json:17`, `F-c1cf0d1c`, Medium.** The `search` server is started with `uvx` as a local stdio process, but its token sits under `headers`. Only HTTP and SSE servers read `headers`, and there is no `env` block, so `SEARCH_TOKEN` never reaches the process. `.claude/settings.json` pre-approves `search`, so it does start, and search calls fail or run unauthenticated with no error saying why. The `tracker` server in the same file passes its token through `env` correctly.
2. **`.cursor/mcp.json:3`, `F-644d89e1`, Medium.** The file uses `${DOCS_API_KEY}`, which is Claude Code's syntax. Cursor expects `${env:DOCS_API_KEY}`, so the docs server receives the literal text as its key. `.vscode/mcp.json:6` already uses the `${env:...}` form. The scan's tally marks a patch for this one as "not offerable", so `/curmudgeon:fix patch` will not apply it.

**Nits** (true but not counted):
- The `box` container in `.mcp.json` has default network access, no read-only root, no resource limits and a mutable tag.
- The bare `Read` allow rule in `.claude/settings.json` has no path scope.
- `LOG_LEVEL=debug` is committed next to a credential in `.vscode/mcp.json`.

The scripted scan found 0 failures and one pedantic note: the three project MCP servers start without a prompt in headless runs. Reviewers also raised a relative `-v ./docs` bind mount in `.vscode/mcp.json`. Only one reviewer raised it, and it was not executed, so the tally dropped it.

I did not run the spot-check or the variant hunt (no Critical or High findings). I changed no project files; the teardown is saved at `.critic/last-review.md`.

To fix: `/curmudgeon:review fix` for every finding, or `/curmudgeon:fix patch [id]` for one.