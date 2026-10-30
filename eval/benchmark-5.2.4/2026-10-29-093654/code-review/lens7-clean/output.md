## Code review: `git diff main...HEAD` (commit 5403fc5, four MCP and settings config files)

No `CLAUDE.md` exists in the repo, so I checked for bugs only. I read the diff myself rather than launching the agent pipeline, because it is 44 lines of JSON config. I did not run any of the servers or check the config schemas against vendor docs. The `.cursor/mcp.json` finding below rests on my recollection of Cursor's syntax, so it is lower confidence.

**Issues**

1. **`.mcp.json:15-17`: the `search` server's auth header is never sent.**
   - `search` is a stdio server (`command: uvx`), and `headers` is only read for `http`/`sse` servers. For a stdio server it is ignored.
   - `SEARCH_TOKEN` therefore never reaches the process, and the server starts without credentials.
   - Fix: pass it through `"env": {"SEARCH_TOKEN": "${SEARCH_TOKEN}"}` as `tracker` does, or make it an `http` server with a `url`.

2. **`.cursor/mcp.json:4`: the env interpolation looks like the wrong syntax for Cursor (lower confidence).**
   - `"DOCS_API_KEY": "${DOCS_API_KEY}"` uses the Claude Code `.mcp.json` form. As I recall, Cursor expands `${env:NAME}`, so the server would receive the literal string `${DOCS_API_KEY}`.
   - `.vscode/mcp.json` in this same change uses `${env:LINT_TOKEN}`.
   - Worth checking against Cursor's docs before merging.

**Security notes**

These are judgment calls rather than definite bugs, so I'd treat them as discussion points.

3. **`.claude/settings.json:2` auto-approves repo-defined servers.**
   - `enabledMcpjsonServers: ["tracker", "search"]` skips the approval prompt for these two servers.
   - Anyone who opens the repo in Claude Code then runs `npx -y tracker-mcp@3.2.1` and `uvx search-mcp==2.1.0`, with `TRACKER_API_TOKEN` in the environment, without being asked.
   - The versions are pinned, which helps, but there is no integrity pinning.

4. **`.claude/settings.json:4` has a bare `"Read"` allow.**
   - It permits reading any file, including `.env` and key files, with no prompt.
   - `Bash(npm test:*)` also runs whatever the repo's `test` script does.
   - Narrower patterns such as `Read(./src/**)` would limit this.

**Not flagged**

- `box` is deliberately not in `enabledMcpjsonServers`, so it still prompts.
- The `LOG_LEVEL: debug` setting in the `lint` server's `env` is fine.