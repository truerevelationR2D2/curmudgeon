## Code review

I reviewed `main...HEAD` ("Add the app") and found one issue. I posted nothing and changed no files.

**Issue: the `search` server's auth token is never sent** (`.mcp.json`, lines 14–18, bug)

The `search` entry launches a local stdio process with `"command": "uvx"` and `"args": ["search-mcp==2.1.0"]`. It then sets `"headers": {"Authorization": "Bearer ${SEARCH_TOKEN}"}`. In Claude Code's MCP config, `headers` applies only to remote `http`/`sse` servers, so a stdio server ignores it. `.claude/settings.json` enables `search` through `enabledMcpjsonServers`, so it starts without `SEARCH_TOKEN`. The fix is `"env": {"SEARCH_TOKEN": "${SEARCH_TOKEN}"}`, as the `tracker` entry does. The variable name `search-mcp` actually reads wasn't checked.

Two agents found this independently and a validator confirmed it. The validator could not open the official docs page, so the claim about `headers` rests on the agents' recall of those docs, not a source I can link.

**Dropped by validation**
- **Cursor key syntax:** the claim that `.cursor/mcp.json` needs `${env:DOCS_API_KEY}` instead of `${DOCS_API_KEY}` was UNVERIFIABLE. The validator could not read Cursor's docs, so I dropped it. It is worth a manual check.
- **Title and description:** the PR adds only four MCP and permission config files, not application code. That mismatch isn't a code defect, so I didn't flag it.

**CLAUDE.md compliance:** both agents found no `CLAUDE.md` file in the repo, so there were no rules to check.