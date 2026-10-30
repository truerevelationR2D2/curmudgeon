"""The scope file (SC-49, roadmap 11): what Curmudgeon may actively test beyond this computer, written by the owner as
data, never prose. `.critic/scope.json`, deny by default:

  {
    "version": 1,
    "targets": [
      {"origin": "https://staging.example.com", "max_requests": 300, "note": "our staging copy, reset nightly"}
    ]
  }

Rules (each enforced here, each with a test):
- No file: nothing beyond this computer is loaded. Pages on localhost or a loopback address, and local files, never need it.
- The file must be a plain file (not a link), at most 64 KB, a JSON object with only the keys above. Anything else is
  refused whole, with the reason, rather than half-read.
- Each target is an http(s) origin with no user name or password and no path. A page outside every listed origin is
  refused, and every request to another origin is blocked and logged.
- Only GET, HEAD and OPTIONS are ever sent to a target. There is no key to allow more (the step-by-step driver, SC-66,
  asks the user for anything that changes state).
- A target that isn't loopback needs a typed confirmation on every run: `critic_scan.py --allow-live HOST`, where HOST is
  that target's host name, typed by the user. The skill asks for it; it never fills it in on its own.
- At most max_requests requests per run (default 200, at most 5000); past that every request is aborted and logged."""
import json, pathlib
from urllib.parse import urlsplit

MAX_BYTES = 64 * 1024
KEYS = {"version", "targets"}
TARGET_KEYS = {"origin", "max_requests", "note"}
DEFAULT_CAP, MAX_CAP = 200, 5000

def origin_of(url):
    u = urlsplit(url)
    port = u.port or (443 if u.scheme == "https" else 80)
    return (u.scheme, (u.hostname or "").lower(), port)

def load(root):
    """(targets, problem): targets is a list of {"origin": (scheme, host, port), "host", "max_requests"}; problem is None
    or the reason the file was refused. No file gives ([], None)."""
    p = pathlib.Path(root) / ".critic" / "scope.json"
    if not p.exists() and not p.is_symlink(): return [], None
    from critic_findings import state_trusted
    if p.is_file() and not p.is_symlink() and not state_trusted(root, "scope.json"):
        return [], "scope.json is tracked by git, so it may have come with a clone: the owner approves it with critic_ledger.py approve scope.json (03 §5.56 item 9)"
    if p.is_symlink() or not p.is_file(): return [], "scope.json is a link or not a plain file; it is never read through a link"
    if p.stat().st_size > MAX_BYTES: return [], f"scope.json is over {MAX_BYTES // 1024} KB; a scope file is a short list"
    try: j = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e: return [], f"scope.json is not valid JSON ({str(e)[:80]})"
    if not isinstance(j, dict): return [], "scope.json must be a JSON object"
    extra = set(j) - KEYS
    if extra: return [], f"scope.json has keys it may not have: {', '.join(sorted(extra))} (only version and targets)"
    if j.get("version") != 1: return [], "scope.json needs \"version\": 1"
    if not isinstance(j.get("targets"), list) or not j["targets"]: return [], "scope.json needs a non-empty \"targets\" list"
    out = []
    for i, t in enumerate(j["targets"], 1):
        if not isinstance(t, dict): return [], f"target {i} must be an object"
        extra = set(t) - TARGET_KEYS
        if extra: return [], f"target {i} has keys it may not have: {', '.join(sorted(extra))} (only origin, max_requests and note)"
        o = t.get("origin")
        if not isinstance(o, str): return [], f"target {i} needs an origin"
        try: u = urlsplit(o)
        except ValueError: return [], f"target {i}: {o!r} is not a URL"
        if u.scheme not in ("http", "https") or not u.hostname: return [], f"target {i}: the origin must be http(s)://host[:port]"
        if "@" in u.netloc: return [], f"target {i}: an origin with a user name or password is never allowed"
        if u.path not in ("", "/") or u.query or u.fragment: return [], f"target {i}: an origin has no path, query or fragment ({o})"
        cap = t.get("max_requests", DEFAULT_CAP)
        if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= MAX_CAP: return [], f"target {i}: max_requests must be a whole number from 1 to {MAX_CAP}"
        out.append({"origin": origin_of(o), "host": u.hostname.lower(), "max_requests": cap})
    return out, None

def decide(url, root, confirmed_host, is_local):
    """(allowed, target_or_None, reason) for loading url. Local pages are always allowed with no target."""
    if is_local: return True, None, ""
    targets, problem = load(root)
    if problem: return False, None, f"live URL refused: {problem}"
    if not targets: return False, None, "live URL refused: no .critic/scope.json lists it (the owner writes one to allow a test copy)"
    try: o = origin_of(url)
    except ValueError: return False, None, "live URL refused: not a URL"
    t = next((x for x in targets if x["origin"] == o), None)
    if not t: return False, None, f"live URL refused: {o[1]} is not a target in .critic/scope.json"
    if (confirmed_host or "").strip().lower() != t["host"]:
        return False, None, f"live URL refused: this run needs the owner's typed confirmation, --allow-live {t['host']}"
    from critic_findings import consent_given
    if not consent_given(root, "live", t["host"]):  # 03 §5.56 item 12: the flag alone could be passed by any agent
        return False, None, f"live URL refused: the owner's consent isn't on file for this run: after they type the host, run critic_ledger.py consent live {t['host']}"
    return True, t, ""
