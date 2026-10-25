#!/usr/bin/env python3
"""The security rule feed (SC-75, 5.2): a local copy of public vulnerability data, so a dependency check needs to send
nothing about your project anywhere. Our own code; the idea of signature updates comes from anti-virus and IPS tools.

It is OFF until you say yes (Ryan's ruling, 03 §5.38). The first security scan asks once; your answer and schedule
are kept in the plugin's data folder (${CLAUDE_PLUGIN_DATA}/feed, or ~/.curmudgeon/feed). Schedules: daily, weekly,
biweekly, monthly or off. Off never downloads anything and never enables the scan's feed check.

Where the data comes from (each download is the same file for every user; no package name, path or code is sent):
  OSV.dev bulk export   https://storage.googleapis.com/osv-vulnerabilities/<ECOSYSTEM>/all.zip
                        the open vulnerability database Google runs; it gathers advisories from GitHub, PyPA, RustSec,
                        Go and others. Licence: per source (GitHub advisories are CC-BY 4.0); see SOURCES below.
  CISA KEV catalogue    https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
                        the US agency's list of vulnerabilities known to be exploited in the wild. Licence: CC0.

What is checked on every download, since neither source signs its files: HTTPS only (certificate checked by Python),
a size limit, the zip's own CRC test, every record parses and has an id, the new copy may not lose more than half the
records of the old one, and the SHA-256 of each download is written to feed-log.jsonl. The data is turned into JSON
tables and is only ever read as data, never run. A failed check keeps the old copy.

usage:
  security_feed.py status [--json]
  security_feed.py set --cadence daily|weekly|biweekly|monthly|off [--ecosystems npm,PyPI]
  security_feed.py due                     exit 0 when an update is due, 1 when not (or off)
  security_feed.py update [--force]        download and check; refuses unless switched on
  security_feed.py match ROOT [--json]     check ROOT's lockfiles against the local copy (no network)"""
import argparse, datetime as dt, hashlib, io, json, os, pathlib, re, sys, tempfile, urllib.request, zipfile

CADENCE_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14, "monthly": 30}
ECOSYSTEMS = ("npm", "PyPI")  # the two the lockfile readers in scan_deps understand today
OSV_BASE = "https://storage.googleapis.com/osv-vulnerabilities"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
SOURCES = [
    {"name": "OSV.dev bulk export", "url": OSV_BASE + "/<ECOSYSTEM>/all.zip", "what": "known vulnerable package versions",
     "licence": "per original source; GitHub Advisory Database records are CC-BY 4.0 (credit: GitHub, Inc.)"},
    {"name": "CISA Known Exploited Vulnerabilities", "url": KEV_URL, "what": "CVEs known to be exploited in the wild",
     "licence": "CC0 1.0 (https://www.cisa.gov/sites/default/files/licenses/kev/license.txt)"},
]
MAX_ZIP = 400 * 1024 * 1024; MAX_JSON = 50 * 1024 * 1024; MAX_RECORD = 2 * 1024 * 1024

def norm(eco, name): return re.sub(r"[-_.]+", "-", name.lower()) if eco == "PyPI" else name  # PEP 503 names for PyPI

def data_dir():
    d = os.environ.get("CURMUDGEON_FEED_DIR") or (os.path.join(os.environ["CLAUDE_PLUGIN_DATA"], "feed") if os.environ.get("CLAUDE_PLUGIN_DATA") else os.path.expanduser("~/.curmudgeon/feed"))
    return pathlib.Path(d)

def load_cfg(d=None):
    p = (d or data_dir()) / "feed.json"
    try: j = json.loads(p.read_text(encoding="utf-8")) if p.is_file() and not p.is_symlink() else {}
    except (OSError, ValueError): j = {}
    return j if isinstance(j, dict) else {}

def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink(): raise OSError(f"refusing to write through a link at {path}")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(text)
    os.replace(tmp, path)

def save_cfg(cfg, d=None): write_atomic((d or data_dir()) / "feed.json", json.dumps(cfg, indent=1, sort_keys=True))

def switched_on(cfg): return cfg.get("consent") == "yes" and cfg.get("cadence") in CADENCE_DAYS

def now(): return dt.datetime.now(dt.timezone.utc)

def is_due(cfg, at=None):
    if not switched_on(cfg): return False, "the feed is off" if cfg.get("asked") else "never switched on (the first security scan asks)"
    last = cfg.get("last_update")
    if not last: return True, "switched on and never downloaded"
    try: age = (at or now()) - dt.datetime.fromisoformat(last)
    except ValueError: return True, "the last-update time is unreadable"
    days = CADENCE_DAYS[cfg["cadence"]]
    return (age >= dt.timedelta(days=days), f"last update {age.days} day(s) ago; schedule {cfg['cadence']}")

def fetch(url, limit):
    if not re.match(r"^(https://|file://)", url): raise ValueError(f"refusing a non-HTTPS source: {url}")  # file:// is for the offline tests
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curmudgeon-feed"}), timeout=60) as r:
        data = r.read(limit + 1)
    if len(data) > limit: raise ValueError(f"{url} is over the {limit // (1024 * 1024)} MB limit")
    return data

def compile_osv(blob, eco):
    """A zip of OSV records to {package name: [[id, versions, ranges, cves, summary], ...]}."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    bad = z.testzip()
    if bad: raise ValueError(f"the {eco} zip is damaged at {bad}")
    table, n = {}, 0
    for info in z.infolist():
        if not info.filename.endswith(".json") or info.file_size > MAX_RECORD: continue
        rec = json.loads(z.read(info))
        if not isinstance(rec, dict) or not rec.get("id"): raise ValueError(f"{info.filename} has no id")
        if rec.get("withdrawn"): continue
        n += 1
        cves = sorted({a for a in rec.get("aliases") or [] if isinstance(a, str) and a.startswith("CVE-")} | ({rec["id"]} if rec["id"].startswith("CVE-") else set()))
        for aff in rec.get("affected") or []:
            pkg = aff.get("package") or {}
            if pkg.get("ecosystem") != eco or not pkg.get("name"): continue
            ranges = [[r.get("type"), [[k, v] for e in r.get("events") or [] for k, v in e.items()]] for r in aff.get("ranges") or [] if r.get("type") in ("SEMVER", "ECOSYSTEM")]
            name = norm(eco, pkg["name"])
            table.setdefault(name, []).append([rec["id"], sorted(set(aff.get("versions") or [])), ranges, cves, (rec.get("summary") or "")[:160]])
    return table, n

def compile_kev(blob):
    j = json.loads(blob)
    rows = j.get("vulnerabilities") if isinstance(j, dict) else None
    if not isinstance(rows, list): raise ValueError("the KEV file has no vulnerabilities list")
    return sorted({r["cveID"] for r in rows if isinstance(r, dict) and re.match(r"^CVE-\d{4}-\d+$", str(r.get("cveID", "")))})

def update(cfg, d=None, force=False, osv_base=None, kev_url=None):
    d = d or data_dir()
    if not switched_on(cfg): return 3, "the feed is off: nothing downloaded (switch it on with `set --cadence ...` after the user says yes)"
    due, why = is_due(cfg)
    if not due and not force: return 0, f"not due ({why})"
    osv_base = osv_base or os.environ.get("CURMUDGEON_FEED_OSV") or OSV_BASE; kev_url = kev_url or os.environ.get("CURMUDGEON_FEED_KEV") or KEV_URL
    log, out, counts = [], {}, {}
    try:
        for eco in cfg.get("ecosystems") or ECOSYSTEMS:
            if eco not in ECOSYSTEMS: continue
            url = f"{osv_base}/{eco}/all.zip"; blob = fetch(url, MAX_ZIP)
            log.append({"url": url, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
            table, n = compile_osv(blob, eco)
            old = (cfg.get("counts") or {}).get(eco, 0)
            if old and n < old // 2: raise ValueError(f"{eco}: {n} records against {old} last time; refusing a copy that lost over half")
            out[f"osv-{eco}.json"] = table; counts[eco] = n
        blob = fetch(kev_url, MAX_JSON)
        log.append({"url": kev_url, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
        kev = compile_kev(blob); old = (cfg.get("counts") or {}).get("kev", 0)
        if old and len(kev) < old // 2: raise ValueError(f"KEV: {len(kev)} entries against {old} last time; refusing")
        out["kev.json"] = kev; counts["kev"] = len(kev)
    except Exception as e:
        _log(d, {"at": now().isoformat(), "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "downloads": log})
        return 1, f"update failed, the old copy is kept: {type(e).__name__}: {str(e)[:200]}"
    for name, table in out.items(): write_atomic(d / name, json.dumps(table, separators=(",", ":")))
    cfg.update(last_update=now().isoformat(), counts=counts); save_cfg(cfg, d)
    _log(d, {"at": cfg["last_update"], "ok": True, "counts": counts, "downloads": log})
    return 0, "updated: " + ", ".join(f"{k} {v}" for k, v in counts.items())

def _log(d, row):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "feed-log.jsonl", "a", encoding="utf-8") as fh: fh.write(json.dumps(row) + "\n")

def vkey(v):
    """A sortable version key: numbers compare as numbers; a pre-release (1.0.0-rc1, 1.0rc1) sorts before its release."""
    v = str(v).strip().lstrip("vV").split("+", 1)[0]
    main, _, pre = v.partition("-")
    m = re.match(r"^([\d.]+)(.*)$", main)
    if m and m.group(2) and not pre: main, pre = m.group(1), m.group(2)
    nums = [int(x) for x in main.split(".") if x.isdigit()] if main else [0]
    while len(nums) > 1 and nums[-1] == 0: nums.pop()
    preparts = tuple((0, int(x)) if x.isdigit() else (1, x) for x in re.findall(r"\d+|[A-Za-z]+", pre))
    return (tuple(nums), 0 if pre else 1, preparts)

def affected(version, entry):
    _, versions, ranges, _, _ = entry
    if version in versions: return True
    v = vkey(version)
    for _, events in ranges:
        lo = None
        for k, val in events:
            if k == "introduced": lo = vkey("0") if val == "0" else vkey(val)
            elif k == "fixed" and lo is not None:
                if lo <= v < vkey(val): return True
                lo = None
            elif k == "last_affected" and lo is not None:
                if lo <= v <= vkey(val): return True
                lo = None
            elif k == "limit" and lo is not None:
                if lo <= v < vkey(val): return True
                lo = None
        if lo is not None and v >= lo: return True  # introduced with no fix yet
    return False

def load_tables(d=None):
    d = d or data_dir(); tabs = {}
    for eco in ECOSYSTEMS:
        p = d / f"osv-{eco}.json"
        if p.is_file() and not p.is_symlink():
            try: tabs[eco] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError): pass
    try: kev = set(json.loads((d / "kev.json").read_text(encoding="utf-8")))
    except (OSError, ValueError): kev = set()
    return tabs, kev

def match(pkgs, d=None):
    """pkgs: (lockfile, ecosystem, name, version, dev) rows from scan_deps. Returns None when there is no local copy or
    the feed is off; otherwise one row per vulnerable package: (lockfile, eco, name, version, dev, [ids], exploited)."""
    cfg = load_cfg(d)
    if not switched_on(cfg) or not cfg.get("last_update"): return None
    tabs, kev = load_tables(d)
    if not tabs: return None
    out = []
    for lf, eco, name, version, dev in pkgs:
        key = norm(eco, name)
        hits = [e for e in tabs.get(eco, {}).get(key, []) if affected(version, e)]
        if hits: out.append((lf, eco, name, version, dev, sorted({e[0] for e in hits}), any(c in kev for e in hits for c in e[3])))
    return out

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("set"); s.add_argument("--cadence", required=True, choices=list(CADENCE_DAYS) + ["off"]); s.add_argument("--ecosystems")
    sub.add_parser("due")
    s = sub.add_parser("update"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("match"); s.add_argument("root"); s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv); cfg = load_cfg()
    if a.cmd == "set":
        cfg.update(asked=now().date().isoformat(), cadence=a.cadence, consent="no" if a.cadence == "off" else "yes")
        if a.ecosystems: cfg["ecosystems"] = [e for e in a.ecosystems.split(",") if e in ECOSYSTEMS]
        save_cfg(cfg); print(f"feed {'off: nothing will be downloaded' if a.cadence == 'off' else 'on, schedule ' + a.cadence} (saved in {data_dir()})"); return 0
    if a.cmd == "due":
        due, why = is_due(cfg); print(("due: " if due else "not due: ") + why); return 0 if due else 1
    if a.cmd == "update":
        code, msg = update(cfg, force=a.force); print(msg); return code
    if a.cmd == "match":
        sys.path.insert(0, str(pathlib.Path(__file__).parent)); import scan_deps
        root = pathlib.Path(a.root).resolve(); pkgs = []
        for lf in root.rglob("package-lock.json"):
            if not scan_deps._skip(lf, root): pkgs += [(str(lf.relative_to(root)), *x) for x in scan_deps._lock_npm(lf)]
        for rf in root.rglob("requirements*.txt"):
            if not scan_deps._skip(rf, root): pkgs += [(str(rf.relative_to(root)), *x) for x in scan_deps._reqs(rf)]
        rows = match(pkgs)
        if rows is None: print("no local feed copy (the feed is off or has never downloaded)"); return 1
        if a.json: print(json.dumps([dict(zip(("lockfile", "ecosystem", "name", "version", "dev", "ids", "exploited"), r)) for r in rows], indent=1))
        else:
            print(f"{len(pkgs)} packages checked, {len(rows)} vulnerable")
            for r in rows: print(f"  {r[2]} {r[3]} ({r[0]}): {', '.join(r[5][:5])}{' EXPLOITED IN THE WILD (CISA KEV)' if r[6] else ''}{' (dev only)' if r[4] else ''}")
        return 0
    due, why = is_due(cfg)
    st = {"folder": str(data_dir()), "asked": cfg.get("asked"), "cadence": cfg.get("cadence", "never asked"), "on": switched_on(cfg),
          "last_update": cfg.get("last_update"), "due": due, "why": why, "counts": cfg.get("counts", {}), "sources": SOURCES}
    if a.json: print(json.dumps(st, indent=1))
    else:
        print(f"security feed: {'on' if st['on'] else 'off'} · schedule {st['cadence']} · last update {st['last_update'] or 'never'} · {why}")
        for x in SOURCES: print(f"  {x['name']}: {x['url']} ({x['licence']})")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
