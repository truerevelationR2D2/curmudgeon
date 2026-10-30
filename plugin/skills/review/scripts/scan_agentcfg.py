"""The agent and MCP configuration lens (SC-52), our own rules and code. The behaviour it relies on is checked in Claude
Code's MCP documentation (code.claude.com/docs/en/mcp, read 24 Oct 2026): project servers in .mcp.json need approval
in interactive sessions, but `claude -p`, Agent SDK and cloud sessions "load project-scoped servers without asking".

Files: .mcp.json, .claude/settings.json, .claude/settings.local.json, .cursor/mcp.json, .vscode/mcp.json and
claude_desktop_config.json, read as JSON (a file that isn't valid JSON is reported as not checked).

  agent-auto-mcp            WARN  enableAllProjectMcpServers: true committed in the project's settings: every server in
                                  .mcp.json starts without anyone approving it.
  agent-literal-credential  FAIL  a literal credential in a server's env or headers (a key named like token, key, secret,
                                  password or auth, or an Authorization header, holding a value instead of ${VAR},
                                  ${env:X} or ${input:id}, alone or after Bearer). A key ending in _MODE, _TYPE, _FILE,
                                  _PATH and the like (unless its value starts with Bearer, Basic or Token), a file path,
                                  and a URL with no user or password are not.
  agent-download-run        WARN  a server started through a shell that downloads and runs code (curl or wget piped to a
                                  shell, or sh/bash -c with a download).
  agent-privileged-docker   WARN  a server run with docker --privileged, the host network, the Docker socket or the
                                  host's root mounted.
  agent-unpinned-runner     NOTE  npx, uvx, bunx or pipx running a package with no version: the newest release runs.
                                  Pinning fixes only the top-level package, not what it depends on.
  agent-wildcard-allow      WARN  a permissions allow rule that allows a whole server or every command (mcp__x__*,
                                  mcp__x, Bash, Bash(*), *).
  agent-shadowed-server     NOTE  the same server name defined in two config files: which one runs depends on the
                                  client and scope.
  agent-headless-mcp        NOTE  (pedantic: it fires for every committed .mcp.json) a committed .mcp.json with servers: they start without a prompt in claude -p, SDK
                                  and cloud runs (block one with disabledMcpjsonServers, or run with --strict-mcp-config).
  agent-not-checked         NOTE  a config file that isn't valid JSON."""
import json, pathlib, re

FILES = {".mcp.json", ".claude/settings.json", ".claude/settings.local.json", ".cursor/mcp.json", ".vscode/mcp.json", "claude_desktop_config.json"}
CRED_PARTS = {"token", "tokens", "secret", "secrets", "password", "passwd", "passwords", "pwd", "pass", "key", "keys", "apikey", "auth",
              "credential", "credentials", "bearer", "pat", "privatekey", "accesskey", "secretkey", "apitoken", "authtoken"}

def _parts(k):
    """A key name split into whole words: GIT_AUTHOR_EMAIL -> git, author, email; apiKey -> api, key."""
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", re.sub(r"[^A-Za-z0-9]+", " ", k))]

class _SecretKey:
    """A key with a credential word as a whole part (SENDGRID_KEY, AUTH_TOKEN, apiKey), never inside another word
    (AUTHOR, MONKEY, PASSAGE); a public key is not a secret."""
    @staticmethod
    def search(k):
        ps = _parts(str(k))
        return bool(set(ps) & CRED_PARTS) and "public" not in ps
SECRET_KEY = _SecretKey()
RUNNERS = {"npx": re.compile(r"(?<!^)@[\^~=]?\d"), "bunx": re.compile(r"(?<!^)@[\^~=]?\d"), "uvx": re.compile(r"==\d|(?<!^)@\d"), "pipx": re.compile(r"==\d|(?<!^)@\d")}

def wants(rel):
    r = rel.replace("\\", "/")
    return r in FILES or r.endswith("/claude_desktop_config.json")

def _line(raw, needle, start=0):
    for i in range(start, len(raw)):
        if needle in raw[i]: return i + 1
    return 1

REF = r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\$\{(?:env|input|secret|config):[A-Za-z_][\w.-]*\}|\{\{\s*[\w.]+\s*\}\}|<[^>]+>"
NOT_CREDENTIAL_KEY = re.compile(r"(?i)_(mode|type|kind|method|file|path|dir|endpoint|host|port|scope|scopes|provider|name|enabled|timeout|region|version|email|domain|user|username|url|uri|id|header|prefix|length|ttl|expiry|expires)$")

def _is_reference(v):
    """An environment or input reference (${X}, ${env:X}, ${input:id}, {{x}}, <placeholder>), alone or after a scheme
    word (Bearer ${input:pat}, as VS Code's and GitHub's own MCP examples write it)."""
    s = str(v).strip()
    return not s or bool(re.fullmatch(REF, s)) or bool(re.fullmatch(r"(?i)(bearer|token|basic)\s+(?:" + REF + ")", s))

def _not_a_secret_value(v):
    """A file path, or a URL without credentials, names where a secret lives; it isn't the secret."""
    s = str(v).strip()
    if re.match(r"^(/|~[/\\]|\.{1,2}[/\\]|[A-Za-z]:[\\/]|\\\\)", s): return True  # a path
    return bool(re.fullmatch(r"https?://[^\s@:/]+(:\d+)?(/[^\s?#]*)?", s))  # a URL with no user, password or query

def _servers(j):
    if not isinstance(j, dict): return {}
    s = j.get("mcpServers", j.get("servers"))
    return s if isinstance(s, dict) else {}

def scan(rel, text, emit, seen_names):
    """seen_names: {server name: rel} across the files of one scan, for agent-shadowed-server."""
    raw = text.split("\n")
    try: j = json.loads(text)
    except ValueError as e:
        emit("NOTE", "agent-not-checked", "agent-config", rel, f"not checked: not valid JSON ({str(e)[:80]})", ""); return
    r = rel.replace("\\", "/")
    if isinstance(j, dict) and j.get("enableAllProjectMcpServers") is True and r.startswith(".claude/settings"):
        ln = _line(raw, "enableAllProjectMcpServers")
        emit("WARN", "agent-auto-mcp", "agent-config", f"{rel}:{ln}", "enableAllProjectMcpServers is committed: every server in .mcp.json starts without anyone approving it", raw[ln - 1])
    perms = j.get("permissions") if isinstance(j, dict) else None
    for rule in (perms.get("allow") or []) if isinstance(perms, dict) and isinstance(perms.get("allow"), list) else []:
        s = str(rule).strip()
        if s in ("*", "Bash", "Bash(*)", "Bash(:*)") or s.startswith("mcp__") and (s.endswith("__*") or s.count("__") == 1):
            ln = _line(raw, json.dumps(s))
            emit("WARN", "agent-wildcard-allow", "agent-config", f"{rel}:{ln}", f"the allow rule {s} lets every {'tool of that server' if s.startswith('mcp__') else 'command'} run without asking: allow the specific ones", raw[ln - 1])
    servers = _servers(j)
    if servers and r == ".mcp.json":
        ln = _line(raw, '"mcpServers"') if '"mcpServers"' in text else 1
        emit("NOTE", "agent-headless-mcp", "agent-config", f"{rel}:{ln}", f"{len(servers)} project MCP server(s): they start without a prompt in claude -p, Agent SDK and cloud runs (block one with disabledMcpjsonServers, or run with --strict-mcp-config)", raw[ln - 1] if ln <= len(raw) else "")
    for name, cfg in servers.items():
        if not isinstance(cfg, dict): continue
        at = _line(raw, json.dumps(name)); start = at - 1
        if name in seen_names and seen_names[name] != rel:
            emit("NOTE", "agent-shadowed-server", "agent-config", f"{rel}:{at}", f"the server {name} is also defined in {seen_names[name]}: which one runs depends on the client and scope", raw[at - 1])
        seen_names.setdefault(name, rel)
        for field in ("env", "headers"):
            d = cfg.get(field)
            if not isinstance(d, dict): continue
            for k, v in d.items():
                if (SECRET_KEY.search(k) and (not NOT_CREDENTIAL_KEY.search(k) or re.match(r"(?i)\s*(bearer|basic|token)\s+\S", str(v))) or k.lower() == "authorization") and isinstance(v, str) and not _is_reference(v) and not _not_a_secret_value(v) and len(v.strip()) >= 8:
                    ln = _line(raw, json.dumps(k), start)
                    emit("FAIL", "agent-literal-credential", "agent-config", f"{rel}:{ln}", f"{name}: {field}.{k} holds a literal credential: reference an environment variable (${{{k.upper()}}}) and rotate this one", "(value redacted)")
        cmd = str(cfg.get("command") or ""); args = [str(a) for a in cfg.get("args") or []] if isinstance(cfg.get("args"), list) else []
        line_all = " ".join([cmd] + args)
        base = pathlib.PurePath(cmd).name
        if base in ("sh", "bash", "zsh", "dash", "cmd", "powershell", "pwsh") and re.search(r"\b(curl|wget|iwr|Invoke-WebRequest)\b", line_all):
            ln = _line(raw, '"command"', start)
            emit("WARN", "agent-download-run", "agent-config", f"{rel}:{ln}", f"{name} starts through a shell that downloads and runs code: whatever the server sends runs on every start", raw[ln - 1])
        if base in ("docker", "podman") and re.search(r"--privileged\b|--network[= ]host\b|--net[= ]host\b|docker\.sock|(?:-v|--volume)[= ]/:", line_all):
            ln = _line(raw, '"command"', start)
            emit("WARN", "agent-privileged-docker", "agent-config", f"{rel}:{ln}", f"{name} runs a container with host-level access (privileged, host network, the Docker socket or / mounted): the container can take over the machine", raw[ln - 1])
        if base in RUNNERS:
            pkgs, skip = [], False
            for i, a in enumerate(args):  # pipx run PKG, uvx --python 3.12 PKG: skip the subcommand and option values
                if skip: skip = False; continue
                if a.startswith("-"):
                    skip = "=" not in a and a in ("--python", "-p", "--from", "--with", "--spec", "--index-url", "--index", "-i", "--pip-args", "--package")
                    continue
                if base == "pipx" and not pkgs and a == "run": continue
                pkgs.append(a)
            if pkgs and not RUNNERS[base].search(pkgs[0]):
                ln = _line(raw, json.dumps(pkgs[0]), start)
                emit("NOTE", "agent-unpinned-runner", "agent-config", f"{rel}:{ln}", f"{name}: {base} {pkgs[0]} has no version, so the newest release runs on every start (pin it; that fixes only the top-level package)", raw[ln - 1])
