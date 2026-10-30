```json
[
  {
    "file": ".claude/settings.json",
    "line": 2,
    "summary": "enabledMcpjsonServers auto-approves the project's .mcp.json servers (tracker, search), so they launch without the per-server trust prompt.",
    "failure_scenario": "Anyone who clones this repo and opens it in Claude Code starts `npx -y tracker-mcp@3.2.1` and `uvx search-mcp==2.1.0` with no consent. Those are arbitrary third-party packages run from repo-controlled config, and tracker receives TRACKER_API_TOKEN from the user's environment. A compromised or typosquatted package, or a later edit to .mcp.json, gets code execution and token theft. The session start in this review shows `tracker` and `search` being launched this way."
  },
  {
    "file": ".claude/settings.json",
    "line": 4,
    "summary": "The bare `Read` permission allows reading any file without a prompt, with no path restriction.",
    "failure_scenario": "Once an auto-enabled MCP server or prompt injection drives the agent, it can read ~/.ssh/*, .env files and cloud credentials with no prompt. The same command or server can then send them out, so the allowlist is far broader than the 'list issues / run tests' purpose it appears to serve."
  },
  {
    "file": ".claude/settings.json",
    "line": 4,
    "summary": "`Bash(npm test:*)` runs whatever the repo's package.json `test` script contains, so it is an arbitrary-code-execution allowance for the repo.",
    "failure_scenario": "A malicious or modified `scripts.test` (or a pre/post-test hook) runs on the user's machine with no prompt as soon as the agent runs `npm test`. This repo has no package.json yet, so the rule also does nothing today."
  },
  {
    "file": ".mcp.json",
    "line": 9,
    "summary": "The `box` server runs `docker run example/box-mcp:1.0` with a mutable tag, no digest pin and no sandbox flags.",
    "failure_scenario": "A mutable tag can be repointed to a different image at any time, so teammates silently get different code from what was reviewed. The container has default network and no `--network none`, read-only or resource limits, unlike the hardened `local-docker` entry in .vscode/mcp.json. This server also failed with CONNECTION_CLOSED in this session, which suggests the image or docker is unavailable and nothing handles that."
  },
  {
    "file": ".mcp.json",
    "line": 17,
    "summary": "`search` uses a `headers` key, which is only valid for HTTP/SSE servers, on a stdio (`command`/`args`) server.",
    "failure_scenario": "The `Authorization: Bearer ${SEARCH_TOKEN}` header is ignored for a uvx-launched stdio process, so the token is never delivered. The server starts unauthenticated, or fails. It reported CONNECTION_CLOSED in this session. To pass a token it needs an `env` entry, as `tracker` has."
  },
  {
    "file": ".claude/settings.json",
    "line": 2,
    "summary": "`enabledMcpjsonServers` lists only tracker and search, so `box` is neither approved nor declined, and the allowlist does not match .mcp.json.",
    "failure_scenario": "`box` still prompts or silently stays off depending on the client, so behaviour differs per machine. Only `mcp__tracker__list_issues` is allow-listed, while `search` is enabled but has no permission entry. Every `search` tool call prompts, which defeats the point of pre-enabling it."
  },
  {
    "file": ".vscode/mcp.json",
    "line": 6,
    "summary": "The `lint` server is configured with LOG_LEVEL=debug while it holds LINT_TOKEN.",
    "failure_scenario": "Debug logging in an MCP server that has a token in its environment can write request headers or the token itself to stderr or log files, and those logs can end up in CI output or bug reports."
  },
  {
    "file": ".cursor/mcp.json",
    "line": 3,
    "summary": "The `docs` server is a third-party npx package pinned by version only, receives DOCS_API_KEY, and has no integrity pin.",
    "failure_scenario": "`npx -y` auto-installs without confirmation and runs the package's install scripts. If the package is compromised or a maintainer republishes it, the code runs with the user's DOCS_API_KEY in its environment. The same pattern is repeated for tracker and lint."
  },
  {
    "file": ".vscode/mcp.json",
    "line": 2,
    "summary": "The same MCP servers are defined inconsistently across clients: three config files, different schemas, and different server sets.",
    "failure_scenario": "`.mcp.json` has tracker, box and search. `.cursor/mcp.json` has only docs. `.vscode/mcp.json` has lint and local-docker, using the `servers` key and `${env:...}` syntax. Config drift means the security hardening (`--network none`, `:ro`) exists in one place and not another, and nobody can tell which servers a given contributor actually runs. A contributor is easily misled about which tools have access to which secrets."
  }
]
```