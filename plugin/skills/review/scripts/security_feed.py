#!/usr/bin/env python3
"""The security feed (SC-75, 5.2): a local, compressed database of public vulnerability data, built in a folder the
user chooses, so a dependency check sends nothing about the project anywhere. Our own code; the idea of a local
signature database checked against a global list comes from anti-virus and IPS vendors.

Rulings (03 §5.38, §5.40): it is OFF until the user says yes; the user picks the folder in a folder window (or types
it when no window can open); before anything is created the user sees an estimate of the database's size and signs
off on it; the schedule is daily, weekly, biweekly, monthly or off, and off never downloads anything. How the database
is built, what it keeps, how it is checked and how matches are judged are fixed in references/feed-rules.json, so every
install builds the same database. The local database (from OSV.dev) is checked against the global list (CISA's Known
Exploited Vulnerabilities): a match CISA lists as exploited in the wild is a FAIL.

The setup, in order (the review skill's lead runs it, asking the user at each step):
  1. ask: keep a local security database?            (no: `set --cadence off`, and stop)
  2. security_feed.py pick-folder                     a folder window; prints the path, or NO_WINDOW (ask instead)
  3. security_feed.py estimate --folder F             a size-only request per source; prints the estimate
  4. ask the user to sign off on that size, and pick a schedule
  5. security_feed.py set --cadence C --folder F --signed-off BYTES
  6. security_feed.py update                          builds the database

usage:
  security_feed.py status [--json]
  security_feed.py pick-folder
  security_feed.py estimate --folder DIR [--ecosystems npm,PyPI] [--json]
  security_feed.py set --cadence daily|weekly|biweekly|monthly|off [--folder DIR --signed-off BYTES] [--ecosystems npm,PyPI]
  security_feed.py due                     exit 0 when an update is due, 1 when not (or off)
  security_feed.py update [--force]        download, check and build; refuses unless switched on
  security_feed.py match ROOT [--json]     check ROOT's lockfiles against the local database (no network)"""
import argparse, contextlib, datetime as dt, hashlib, io, json, os, pathlib, platform, re, shlex, shutil, sqlite3, subprocess, sys, tempfile, urllib.request, zipfile, zlib

HERE = pathlib.Path(__file__).resolve().parent
RULES_PATH = HERE.parent / "references" / "feed-rules.json"
CADENCE_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14, "monthly": 30}

def rules():
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))

def rules_hash():
    return hashlib.sha256(RULES_PATH.read_bytes()).hexdigest()[:16]

def ecosystems():
    return [s["ecosystem"] for s in rules()["sources"] if s["kind"] == "osv-zip"]

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

def switched_on(cfg):
    return cfg.get("consent") == "yes" and cfg.get("cadence") in CADENCE_DAYS and bool(cfg.get("folder")) and int(cfg.get("signed_off_bytes") or 0) > 0

def db_path(cfg): return pathlib.Path(cfg["folder"]) / rules()["database_file"]

def now(): return dt.datetime.now(dt.timezone.utc)

def is_due(cfg, at=None):
    if not switched_on(cfg): return False, "the feed is off" if cfg.get("asked") else "never switched on (the first security scan asks)"
    last = cfg.get("last_update")
    if not last: return True, "switched on and never built"
    try:
        if not db_path(cfg).is_file(): return True, "the database is missing from its folder"
    except OSError: return True, "the database folder can't be read"
    if not db_readable(db_path(cfg)): return True, "the database can't be read (damaged?)"
    try:
        when = dt.datetime.fromisoformat(last)
        if when.tzinfo is None: when = when.replace(tzinfo=dt.timezone.utc)  # a hand-edited time with no zone counts as UTC
        age = (at or now()) - when
    except (ValueError, TypeError): return True, "the last-update time is unreadable"
    return (age >= dt.timedelta(days=CADENCE_DAYS[cfg["cadence"]]), f"last update {age.days} day(s) ago; schedule {cfg['cadence']}")

def source_url(src):
    """The rules' URL; tests point the two bases at a local mirror with CURMUDGEON_FEED_OSV and CURMUDGEON_FEED_KEV."""
    if src["kind"] == "osv-zip" and os.environ.get("CURMUDGEON_FEED_OSV"): return f"{os.environ['CURMUDGEON_FEED_OSV']}/{src['ecosystem']}/all.zip"
    if src["kind"] == "kev-json" and os.environ.get("CURMUDGEON_FEED_KEV"): return os.environ["CURMUDGEON_FEED_KEV"]
    return src["url"]

def check_scheme(url):
    if not re.match(r"^(https://|file://)", url): raise ValueError(f"refusing a non-HTTPS source: {url}")  # file:// is for the offline tests

def fetch(url, limit):
    check_scheme(url)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curmudgeon-feed"}), timeout=120) as r:
        data = r.read(limit + 1)
    if len(data) > limit: raise ValueError(f"{url} is over the {limit // (1024 * 1024)} MB limit")
    return data

def head_size(url):
    """The download's size from a size-only request (HEAD); nothing about the project is sent."""
    check_scheme(url)
    if url.startswith("file://"): return os.path.getsize(urllib.request.url2pathname(url[7:]))
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "curmudgeon-feed"}), timeout=30) as r:
        n = r.headers.get("Content-Length")
    if not n or not n.isdigit(): raise ValueError(f"{url} did not say how big it is")
    return int(n)

def chosen(cfg_or_ecos):
    ecos = cfg_or_ecos if isinstance(cfg_or_ecos, list) else (cfg_or_ecos.get("ecosystems") or ecosystems())
    R = rules(); return [s for s in R["sources"] if s["id"] in R["always"] or s["ecosystem"] in ecos]

def estimate(ecos, measured=None):
    """Bytes the database should take: each download's HEAD size times its ratio (a measured ratio from the last
    build when there is one, else the rules' upper bound), plus the fixed overhead."""
    R = rules(); rows, total = [], R["estimate"]["overhead_bytes"]
    for s in chosen(ecos):
        size = head_size(source_url(s)); ratio = (measured or {}).get(s["kind"]) or R["estimate"]["ratio"][s["kind"]]
        rows.append({"source": s["id"], "download_bytes": size, "ratio": ratio, "estimate_bytes": int(size * ratio)}); total += int(size * ratio)
    return total, rows

def human(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB": return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024

def pick_folder():
    """A native folder window: AppleScript on macOS, PowerShell on Windows, zenity or kdialog on Linux when one is already
    installed and a display is present. Nothing is installed. Returns (path, how), or (None, why)."""
    title = "Choose a folder for Curmudgeon's local security database"
    sysname = platform.system()
    try:
        if sysname == "Darwin" and shutil.which("osascript"):
            r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{title}")'], capture_output=True, text=True, timeout=600)
        elif sysname == "Windows" and shutil.which("powershell"):
            r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", windows_dialog_script(title)], capture_output=True, text=True, timeout=600)
        elif sysname == "Linux" and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and (shutil.which("zenity") or shutil.which("kdialog")):
            cmd = ["zenity", "--file-selection", "--directory", f"--title={title}"] if shutil.which("zenity") else ["kdialog", "--getexistingdirectory", os.path.expanduser("~"), "--title", title]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        else: return None, "no folder window can open here (no display, or no dialog tool already installed)"
    except (OSError, subprocess.TimeoutExpired) as e: return None, f"the folder window failed ({type(e).__name__})"
    path = r.stdout.strip().splitlines()[-1].strip() if r.stdout.strip() else ""
    err = (r.stderr or "").strip()
    if not path and (r.returncode == 0 or (r.returncode == 1 and (not err or re.search(r"(?i)cancel", err)))): return None, "cancelled"  # zenity, kdialog and osascript exit 1 on Cancel
    if r.returncode != 0: return None, f"the folder window failed: {err[:160] or 'exit ' + str(r.returncode)}"  # an error is not a cancel: the caller asks for the path instead
    if re.fullmatch(r"[A-Za-z]:[\\/]?", path): return path[:2] + "\\", "window"  # a drive root keeps its backslash: "D:" alone is not a full path
    return path.rstrip("/\\") or path, "window"

def windows_dialog_script(title):
    """The PowerShell for the folder window. The title goes in a single-quoted string, where a quote is written twice
    (Curmudgeon's would otherwise end the string and the script would not run)."""
    t = title.replace("'", "''")
    return ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.Description = '{t}'; $d.ShowNewFolderButton = $true; if ($d.ShowDialog() -eq 'OK') {{ $d.SelectedPath }}")

def check_folder(folder):
    p = pathlib.Path(os.path.expanduser(folder))
    if not p.is_absolute(): return None, "give the full path of the folder"
    if p.is_symlink(): return None, "the folder is a link; choose the real folder"
    if not p.is_dir(): return None, "the folder doesn't exist; create it first (the folder window can make one)"
    if not os.access(p, os.W_OK): return None, "the folder can't be written to"
    return p.resolve(), None

def compile_osv(blob, eco, R, too_big=None):
    """A zip of OSV records to rows per the rules: (id, modified, [cves], summary, [(name, versions, ranges)]). A record
    over the size limit is skipped and its file name added to too_big, so the build can count it."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    bad = z.testzip()
    if bad: raise ValueError(f"the {eco} zip is damaged at {bad}")
    out = []
    for info in z.infolist():
        if not info.filename.endswith(".json"): continue
        if info.file_size > R["limits"]["record"]:
            if too_big is not None: too_big.append(info.filename)
            continue
        rec = json.loads(z.read(info))
        if not isinstance(rec, dict) or not rec.get("id"): raise ValueError(f"{info.filename} has no id")
        if rec.get("withdrawn"): continue
        cves = sorted({a for a in rec.get("aliases") or [] if isinstance(a, str) and a.startswith("CVE-")} | ({rec["id"]} if rec["id"].startswith("CVE-") else set()))
        pkgs = []
        for aff in rec.get("affected") or []:
            pkg = aff.get("package") or {}
            if pkg.get("ecosystem") != eco or not pkg.get("name"): continue
            ranges = [[r.get("type"), [[k, v] for e in r.get("events") or [] for k, v in e.items()]] for r in aff.get("ranges") or [] if r.get("type") in ("SEMVER", "ECOSYSTEM")]
            pkgs.append((norm(eco, pkg["name"]), sorted(set(aff.get("versions") or [])), ranges))
        out.append((rec["id"], str(rec.get("modified") or ""), cves, (rec.get("summary") or "")[:160], pkgs))
    return out

def compile_kev(blob):
    j = json.loads(blob)
    rows = j.get("vulnerabilities") if isinstance(j, dict) else None
    if not isinstance(rows, list): raise ValueError("the CISA file has no vulnerabilities list")
    return sorted({(r["cveID"], str(r.get("dateAdded") or "")) for r in rows if isinstance(r, dict) and re.match(r"^CVE-\d{4}-\d+$", str(r.get("cveID", "")))})

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE advisory(id TEXT, ecosystem TEXT, modified TEXT, blob BLOB, PRIMARY KEY(id, ecosystem));
CREATE TABLE package(ecosystem TEXT, name TEXT, advisory_id TEXT);
CREATE INDEX package_name ON package(ecosystem, name);
CREATE TABLE alias(advisory_id TEXT, cve TEXT);
CREATE INDEX alias_cve ON alias(cve);
CREATE TABLE kev(cve TEXT PRIMARY KEY, date_added TEXT);
CREATE TABLE download(time TEXT, source TEXT, url TEXT, bytes INTEGER, sha256 TEXT);
"""

def ro_uri(path):
    """A read-only SQLite URI; the path is percent-encoded, so '#', '?' or '%' in a folder name can't cut it short."""
    return sqlite_uri(pathlib.Path(path).resolve().as_uri())

def sqlite_uri(file_uri):
    """SQLite takes no host in a file: URI, so a Windows network share (file://server/share/...) is written with the
    host in the path (file:////server/share/...), which SQLite passes on as \\\\server\\share."""
    m = re.match(r"^file://([^/]+)(/.*)$", file_uri)
    return (f"file:////{m.group(1)}{m.group(2)}" if m else file_uri) + "?mode=ro"

def db_readable(path):
    try:
        with contextlib.closing(sqlite3.connect(ro_uri(path), uri=True)) as c: c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        return True
    except (sqlite3.Error, OSError): return False

def old_counts(path):
    if not pathlib.Path(path).is_file(): return {}
    try:
        with contextlib.closing(sqlite3.connect(ro_uri(path), uri=True)) as c:
            n = {e: k for e, k in c.execute("SELECT ecosystem, COUNT(*) FROM advisory GROUP BY ecosystem")}
            n["kev"] = c.execute("SELECT COUNT(*) FROM kev").fetchone()[0]
            return n
    except sqlite3.Error: return {}

def update(cfg, d=None, force=False):
    d = d or data_dir()
    if not switched_on(cfg): return 3, "the feed is off: nothing downloaded (switch it on with `set` after the user picks a folder and signs off on the size)"
    due, why = is_due(cfg)
    if not due and not force: return 0, f"not due ({why})"
    folder, bad = check_folder(cfg["folder"])
    if bad: return 1, f"the database folder is not usable: {bad}"
    R = rules(); dst = folder / R["database_file"]; log = []
    if dst.is_symlink(): return 1, f"refusing to write through a link at {dst}"
    try:
        srcs = chosen(cfg)
        sizes = {s["id"]: head_size(source_url(s)) for s in srcs}  # stop before downloading anything too big
        est = R["estimate"]["overhead_bytes"] + sum(int(sizes[s["id"]] * ((cfg.get("measured_ratio") or {}).get(s["kind"]) or R["estimate"]["ratio"][s["kind"]])) for s in srcs)
        cap = int(cfg["signed_off_bytes"]) * R["estimate"]["stop_over_signed_off"]
        if est > cap: return 5, f"the database would be about {human(est)}, over the {human(int(cfg['signed_off_bytes']))} you signed off on by more than {int((R['estimate']['stop_over_signed_off'] - 1) * 100)}%: nothing downloaded. Ask the user to sign off on the new size (`estimate`, then `set ... --signed-off`)"
        was = old_counts(dst); blobs = {}
        for s in srcs:
            url = source_url(s); blob = fetch(url, R["limits"][s["kind"]])
            log.append({"source": s["id"], "url": url, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}); blobs[s["id"]] = blob
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".building-", suffix=".sqlite"); os.close(fd); tmp = pathlib.Path(tmp); c = None
        try:
            c = sqlite3.connect(tmp); c.executescript(SCHEMA); counts = {}
            for s in srcs:
                if s["kind"] == "osv-zip":
                    big = []; rows = compile_osv(blobs[s["id"]], s["ecosystem"], R, big); eco = s["ecosystem"]
                    if big: counts[f"{eco}_skipped_over_limit"] = len(big)  # in the log, status and meta: never a silent drop
                    if was.get(eco) and len(rows) < was[eco] // 2: raise ValueError(f"{eco}: {len(rows)} records against {was[eco]} last time; refusing a copy that lost over half")
                    for aid, mod, cves, summ, pkgs in rows:
                        c.execute("INSERT OR REPLACE INTO advisory VALUES (?,?,?,?)", (aid, eco, mod, zlib.compress(json.dumps({"summary": summ, "packages": pkgs}, separators=(",", ":")).encode(), 9)))
                        c.executemany("INSERT INTO package VALUES (?,?,?)", [(eco, n, aid) for n in sorted({p[0] for p in pkgs})])
                        c.executemany("INSERT INTO alias VALUES (?,?)", [(aid, cv) for cv in cves])
                    counts[eco] = len(rows)
                else:
                    kev = compile_kev(blobs[s["id"]])
                    if was.get("kev") and len(kev) < was["kev"] // 2: raise ValueError(f"CISA: {len(kev)} entries against {was['kev']} last time; refusing")
                    c.executemany("INSERT INTO kev VALUES (?,?)", kev); counts["kev"] = len(kev)
            t = now().isoformat()
            c.executemany("INSERT INTO download VALUES (?,?,?,?,?)", [(t, x["source"], x["url"], x["bytes"], x["sha256"]) for x in log])
            c.executemany("INSERT INTO meta VALUES (?,?)", [("schema", str(R["schema"])), ("rules_hash", rules_hash()), ("built", t), ("counts", json.dumps(counts))])
            c.commit(); c.execute("VACUUM"); c.close(); c = None
            got = tmp.stat().st_size
            if got > cap: raise ValueError(f"the built database is {human(got)}, over 1.25 times the {human(int(cfg['signed_off_bytes']))} signed off on")
            os.replace(tmp, dst)
        finally:
            if c is not None: c.close()  # Windows can't delete a file SQLite still holds open
            if tmp.exists(): tmp.unlink()
    except Exception as e:
        _log(d, {"at": now().isoformat(), "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "downloads": log})
        return 1, f"update failed, the old copy is kept: {type(e).__name__}: {str(e)[:200]}"
    dl = {s["kind"]: 0 for s in srcs}
    for x, s in zip(log, srcs): dl[s["kind"]] += x["bytes"]
    if dl.get("osv-zip"): cfg.setdefault("measured_ratio", {})["osv-zip"] = round(max(0.01, (got - R["estimate"]["overhead_bytes"]) / dl["osv-zip"]), 3)
    cfg.update(last_update=t, counts=counts, database_bytes=got); save_cfg(cfg, d)
    _log(d, {"at": t, "ok": True, "counts": counts, "database_bytes": got, "downloads": log})
    return 0, f"built {dst} ({human(got)}): " + ", ".join(f"{k} {v}" for k, v in counts.items())

def _log(d, row):
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "feed-log.jsonl", "a", encoding="utf-8") as fh: fh.write(json.dumps(row) + "\n")

def vkey(v, eco=None):
    """A sortable version key for semver and PEP 440: numbers compare as numbers; an epoch (1!2.0) outranks everything;
    a dev release sorts before a pre-release, a pre-release (1.0.0-rc1, 1.0rc1) before its release, and a post-release
    (1.0.post1, 1.0-1, 1.0.r1) after it. Local labels (+abc) are ignored."""
    v = str(v).strip().lstrip("vV").split("+", 1)[0].lower()
    epoch = 0
    if "!" in v:
        e, _, v = v.partition("!"); epoch = int(e) if e.isdigit() else 0
    m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", v)
    if not m: return (epoch, (0,), 1, ())
    nums = [int(x) for x in m.group(1).split(".")]
    while len(nums) > 1 and nums[-1] == 0: nums.pop()
    raw = m.group(2); rest = raw.lstrip(".-_")
    if not rest: return (epoch, tuple(nums), 2, ())
    if eco == "npm":  # semver 2.0.0 §11: anything after '-' is a pre-release (2.0.0-0 < 2.0.0); its dot-separated identifiers
        # compare one by one, numbers as numbers, other identifiers as text (so beta11 < beta2), numbers before text,
        # and a shorter list first when the rest is equal
        if not raw.startswith("-"): return (epoch, tuple(nums), 2, ())
        return (epoch, tuple(nums), 1, tuple((0, int(t)) if t.isdigit() else (1, t) for t in raw[1:].split(".")))
    toks = re.findall(r"\d+|[a-z]+", rest)
    words = [t for t in toks if not t.isdigit()]
    parts = tuple((0, int(t)) if t.isdigit() else (1, t) for t in toks)
    if not words or words[0] in ("post", "r", "rev"): phase = 3  # 1.0-1 (PEP 440 implicit post) and 1.0.post1
    elif words[0] == "dev": phase = 0
    else: phase = 1  # a pre-release word, or a semver pre-release label of any name
    return (epoch, tuple(nums), phase, parts)

def affected(version, entry, eco=None):
    """entry: (versions, ranges) for one package in one advisory; eco picks the version rules (npm: semver)."""
    versions, ranges = entry
    if version in versions: return True
    k = lambda x: vkey(x, eco)
    v = k(version)
    for _, events in ranges:
        lo = None
        for kind, val in events:
            if kind == "introduced": lo = k(val)
            elif kind in ("fixed", "limit") and lo is not None:
                if lo <= v < k(val): return True
                lo = None
            elif kind == "last_affected" and lo is not None:
                if lo <= v <= k(val): return True
                lo = None
        if lo is not None and v >= lo: return True  # introduced with no fix yet
    return False

def match(pkgs, d=None):
    """pkgs: (lockfile, ecosystem, name, version, dev) rows from scan_deps. Returns None only when the feed is off or has
    never built. Otherwise (rows, checked, unchecked, problem): one row per vulnerable package, (lockfile, eco, name,
    version, dev, [ids], exploited); how many packages were checked and how many could not be (their ecosystem isn't
    in the database); and why the database couldn't be read at all (missing, moved, a link, damaged), else None. A
    package is never counted as checked against data that isn't there."""
    cfg = load_cfg(d)
    if not switched_on(cfg): return None
    if not cfg.get("last_update"): return [], 0, len(pkgs), "the feed is on but its database has never been built; run security_feed.py update"
    p = db_path(cfg)
    try:
        if p.is_symlink(): return [], 0, len(pkgs), f"the database at {p} is a link, which is never followed; rebuild it with security_feed.py update --force"
        if not p.is_file(): return [], 0, len(pkgs), f"the database is missing from {p.parent} (moved or deleted?); run security_feed.py update"
    except OSError as e: return [], 0, len(pkgs), f"the database folder {p.parent} can't be read ({type(e).__name__})"
    try:
        c = sqlite3.connect(ro_uri(p), uri=True)
        try:
            have = {e for (e,) in c.execute("SELECT DISTINCT ecosystem FROM advisory")} | set((json.loads((c.execute("SELECT value FROM meta WHERE key='counts'").fetchone() or ["{}"])[0])).keys())
            out, checked, unchecked = [], 0, 0
            for lf, eco, name, version, dev in pkgs:
                if eco not in have: unchecked += 1; continue
                checked += 1; ids, exploited = [], False
                for aid, blob in c.execute("SELECT a.id, a.blob FROM package p JOIN advisory a ON a.id = p.advisory_id AND a.ecosystem = p.ecosystem WHERE p.ecosystem=? AND p.name=?", (eco, norm(eco, name))):
                    data = json.loads(zlib.decompress(blob))
                    if any(affected(version, (vs, rg), eco) for n, vs, rg in data["packages"] if n == norm(eco, name)):
                        ids.append(aid)
                        exploited = exploited or c.execute("SELECT 1 FROM alias JOIN kev ON kev.cve = alias.cve WHERE alias.advisory_id=? LIMIT 1", (aid,)).fetchone() is not None
                if ids: out.append((lf, eco, name, version, dev, sorted(set(ids)), exploited))
        finally: c.close()
    except (sqlite3.Error, zlib.error, ValueError, OSError) as e: return [], 0, len(pkgs), f"the database at {p} can't be read ({type(e).__name__}); rebuild it with security_feed.py update"
    return out, checked, unchecked, None

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    sub.add_parser("pick-folder")
    s = sub.add_parser("estimate"); s.add_argument("--folder", required=True); s.add_argument("--ecosystems"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("set"); s.add_argument("--cadence", required=True, choices=list(CADENCE_DAYS) + ["off"]); s.add_argument("--folder"); s.add_argument("--signed-off", type=int); s.add_argument("--ecosystems")
    sub.add_parser("due")
    s = sub.add_parser("update"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("match"); s.add_argument("root"); s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv); cfg = load_cfg()
    def parse_ecos(text):
        if not text: return None, None
        names = {e.lower(): e for e in ecosystems()}; asked = [x.strip() for x in text.split(",") if x.strip()]
        bad = [x for x in asked if x.lower() not in names]
        if bad or not asked: return None, f"unknown ecosystem(s) {', '.join(bad) or '(none given)'}; choose from {', '.join(ecosystems())}"
        return sorted({names[x.lower()] for x in asked}), None
    if a.cmd == "pick-folder":
        path, how = pick_folder()
        if path: print(path); return 0
        print("NO_WINDOW: " + how if how != "cancelled" else "CANCELLED"); return 4 if how != "cancelled" else 1
    if a.cmd == "estimate":
        folder, bad = check_folder(a.folder)
        if bad: print(f"security_feed: {bad}", file=sys.stderr); return 2
        ecos, err = parse_ecos(a.ecosystems)
        if err: print(f"security_feed: {err}", file=sys.stderr); return 2
        try: total, rows = estimate(ecos or cfg.get("ecosystems") or ecosystems(), cfg.get("measured_ratio"))
        except Exception as e: print(f"security_feed: couldn't get the sizes ({type(e).__name__}: {str(e)[:160]}); nothing was downloaded", file=sys.stderr); return 1
        free = shutil.disk_usage(folder).free
        if a.json: print(json.dumps({"folder": str(folder), "estimate_bytes": total, "free_bytes": free, "sources": rows}, indent=1))
        else:
            measured = bool(cfg.get("measured_ratio"))  # before the first build the ratios are upper bounds (feed-rules.json)
            print(f"estimated database size: {'about' if measured else 'up to about'} {human(total)} in {folder} ({human(free)} free)"
                  + ("" if measured else "; the first build is usually smaller, and later estimates use its measured size") + "; downloads: " + ", ".join(f"{r['source']} {human(r['download_bytes'])}" for r in rows))
            print(f"sign off with: set --cadence <schedule> --folder {shlex.quote(str(folder))} --signed-off {total}" + (f" --ecosystems {','.join(ecos)}" if ecos else ""))
        return 0
    if a.cmd == "set":
        if a.cadence == "off":
            cfg.update(asked=now().date().isoformat(), cadence="off", consent="no"); save_cfg(cfg)
            print("feed off: nothing will be downloaded, and the database (if any) is not read"); return 0
        if not a.folder or not a.signed_off: print("security_feed: switching it on needs --folder and --signed-off (the estimate the user signed off on)", file=sys.stderr); return 2
        if a.signed_off < 1: print("security_feed: --signed-off is the size in bytes the user signed off on, and must be 1 or more", file=sys.stderr); return 2
        folder, bad = check_folder(a.folder)
        if bad: print(f"security_feed: {bad}", file=sys.stderr); return 2
        ecos, err = parse_ecos(a.ecosystems)
        if err: print(f"security_feed: {err}", file=sys.stderr); return 2
        if cfg.get("folder") and pathlib.Path(cfg["folder"]) != folder:
            for k in ("last_update", "counts", "database_bytes"): cfg.pop(k, None)  # a new folder has no database yet: build it on the next update
        cfg.update(asked=now().date().isoformat(), cadence=a.cadence, consent="yes", folder=str(folder), signed_off_bytes=int(a.signed_off))
        if ecos and sorted(ecos) != sorted(cfg.get("ecosystems") or ecosystems()):
            cfg.pop("last_update", None)  # a new ecosystem has no table yet: the next update builds, whatever the schedule says
        if ecos: cfg["ecosystems"] = ecos
        save_cfg(cfg); print(f"feed on, schedule {a.cadence}, database in {folder}, signed off at {human(int(a.signed_off))}"); return 0
    if a.cmd == "due":
        due, why = is_due(cfg); print(("due: " if due else "not due: ") + why); return 0 if due else 1
    if a.cmd == "update":
        code, msg = update(cfg, force=a.force); print(msg); return code
    if a.cmd == "match":
        sys.path.insert(0, str(HERE)); import scan_deps
        root = pathlib.Path(a.root).resolve(); pkgs = []
        unread = []
        for lf in root.rglob("package-lock.json"):
            if scan_deps._skip(lf, root): continue
            try: pkgs += [(str(lf.relative_to(root)), *x) for x in scan_deps._lock_npm(lf)]
            except ValueError as e: unread.append(f"{lf.relative_to(root)} ({e})")
        for rf in root.rglob("requirements*.txt"):
            if not scan_deps._skip(rf, root): pkgs += [(str(rf.relative_to(root)), *x) for x in scan_deps._reqs(rf)]
        unread += [f"{x.relative_to(root)} (this lockfile format is not read)" for n in scan_deps.UNREAD_LOCKS for x in root.rglob(n) if not scan_deps._skip(x, root) and not (x.parent / "package-lock.json").exists()]
        for x in unread: print(f"not checked: {x}")
        got = match(pkgs)
        if got is None: print("no local security database (the feed is off or has never built)"); return 1
        rows, checked, unchecked, problem = got
        if problem: print(f"security_feed: {problem}", file=sys.stderr); return 3
        if a.json: print(json.dumps([dict(zip(("lockfile", "ecosystem", "name", "version", "dev", "ids", "exploited"), r)) for r in rows], indent=1))
        else:
            print(f"{checked} packages checked, {len(rows)} vulnerable" + (f"; {unchecked} not checked (their ecosystem isn't in the database)" if unchecked else ""))
            for r in rows: print(f"  {r[2]} {r[3]} ({r[0]}): {', '.join(r[5][:5])}{' EXPLOITED IN THE WILD (CISA KEV)' if r[6] else ''}{' (dev only)' if r[4] else ''}")
        return 0
    due, why = is_due(cfg); R = rules()
    st = {"settings": str(data_dir()), "folder": cfg.get("folder"), "asked": cfg.get("asked"), "cadence": cfg.get("cadence", "never asked"), "on": switched_on(cfg),
          "signed_off_bytes": cfg.get("signed_off_bytes"), "database_bytes": cfg.get("database_bytes"), "last_update": cfg.get("last_update"), "due": due, "why": why,
          "counts": cfg.get("counts", {}), "rules": str(RULES_PATH), "sources": [{k: s[k] for k in ("id", "url", "what", "licence")} for s in R["sources"]]}
    if a.json: print(json.dumps(st, indent=1))
    else:
        print(f"security feed: {'on' if st['on'] else 'off'} · schedule {st['cadence']} · database {st['folder'] or 'not set up'}"
              f"{' (' + human(st['database_bytes']) + ')' if st['database_bytes'] else ''} · last update {st['last_update'] or 'never'} · {why}")
        for x in st["sources"]: print(f"  {x['id']}: {x['url']} ({x['licence']})")
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
