#!/usr/bin/env python3
"""The security database's Windows-only paths, run for real on a Windows machine (the CI job `windows`, or by hand):

  1. a build that fails partway leaves no `.building-*.sqlite` file behind and reports the real cause, not a
     PermissionError from deleting a file SQLite still holds open;
  2. a database folder on a network share (a UNC path, here the machine's own administrative share \\\\localhost\\C$)
     builds and is read back through the URI form SQLite accepts;
  3. a folder whose name holds '#', '%' and a space builds and is read back;
  and afterwards every file the checks made can be deleted (no connection left open).

On any other system it says so and exits 0 without testing anything. Exit 0 all passed, 1 a check failed."""
import json, os, pathlib, platform, shutil, sys, tempfile, zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "review" / "scripts"))

def mirror(root, n=6):
    for eco in ("npm", "PyPI"):
        d = root / "mirror" / eco; d.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(d / "all.zip", "w") as z:
            for i in range(n):
                z.writestr(f"GHSA-{eco}-{i}.json", json.dumps({"id": f"GHSA-{eco}-{i}", "aliases": ["CVE-2099-0001"] if i == 0 else [],
                    "affected": [{"package": {"ecosystem": eco, "name": f"pkg{i}"}, "versions": ["1.0.0"]}]}))
    (root / "mirror" / "kev.json").write_text(json.dumps({"vulnerabilities": [{"cveID": "CVE-2099-0001"}]}))
    os.environ["CURMUDGEON_FEED_OSV"] = (root / "mirror").as_uri(); os.environ["CURMUDGEON_FEED_KEV"] = (root / "mirror" / "kev.json").as_uri()

def switch_on(sf, folder):
    total, _ = sf.estimate(sf.ecosystems())
    sf.save_cfg({"consent": "yes", "cadence": "weekly", "folder": str(folder), "signed_off_bytes": total * 4, "asked": "2026-10-28"})

def build_and_read(sf, folder):
    code, msg = sf.update(sf.load_cfg(), force=True)
    assert code == 0, msg
    got = sf.match([("package-lock.json", "npm", "pkg0", "1.0.0", False)])
    assert got and got[3] is None and got[0] and got[0][0][6] is True, got  # found, and CISA says exploited
    return msg

def main():
    if platform.system() != "Windows": print("windows_checks: not Windows; nothing tested"); return 0
    import security_feed as sf
    failures = []
    t = tempfile.mkdtemp()
    if True:
        root = pathlib.Path(t); os.environ["CURMUDGEON_FEED_DIR"] = str(root / "settings"); mirror(root)
        # 1. a failed build cleans up and keeps the real cause
        db = root / "db1"; db.mkdir(); switch_on(sf, db); build_and_read(sf, db)
        with zipfile.ZipFile(root / "mirror" / "npm" / "all.zip", "w") as z: z.writestr("bad.json", json.dumps({"affected": []}))
        code, msg = sf.update(sf.load_cfg(), force=True)
        left = list(db.glob(".building-*"))
        if code != 1 or "has no id" not in msg or left: failures.append(f"1. failed build: exit {code}, message {msg!r}, left behind {left}")
        else: print("ok 1: a failed build left nothing behind and reported:", msg[:90])
        mirror(root)
        # 2. a network share (UNC)
        drive = os.environ.get("SystemDrive", "C:").rstrip(":\\")
        unc = pathlib.Path(rf"\\localhost\{drive}$") / pathlib.Path(t).relative_to(pathlib.Path(t).anchor) / "share db"
        try:
            unc.mkdir(parents=True, exist_ok=True)
            switch_on(sf, unc); print("ok 2: network share:", build_and_read(sf, unc)[:90], "| uri", sf.ro_uri(unc / sf.rules()["database_file"]))
        except Exception as e: failures.append(f"2. network share {unc}: {type(e).__name__}: {e}")
        # 3. '#', '%' and a space in the folder name
        odd = root / "Security #2 50% db"; odd.mkdir()
        try: switch_on(sf, odd); print("ok 3: odd folder name:", build_and_read(sf, odd)[:90])
        except Exception as e: failures.append(f"3. odd folder name: {type(e).__name__}: {e}")
    locked = []  # every file must be deletable afterwards: Windows refuses to delete a file a connection still holds open
    shutil.rmtree(t, onerror=lambda fn, path, exc: locked.append(f"{path}: {exc[1]}"))
    if locked: failures.append("cleanup: still open or locked: " + "; ".join(locked[:5]))
    else: print("ok cleanup: every file the checks made could be deleted")
    for f in failures: print("FAIL", f)
    checks = [x for x in failures if not x.startswith("cleanup:")]  # the cleanup is its own line, not one of the three
    print(f"windows_checks: {3 - len(checks)} of 3 passed" + ("; cleanup FAILED" if len(checks) < len(failures) else "; cleanup ok")); return 1 if failures else 0

if __name__ == "__main__": sys.exit(main())
