#!/usr/bin/env python3
"""The planted (fake) Stripe key in fixture2/api.js. It ships as a placeholder because GitHub's push protection blocks
key-shaped text, even fake keys, and the placeholder's own name (PLANTED) would tell a reviewer where the bug is. So
every harness that copies a fixture (deathmatch.py, golden.py) fills the copy in with fill(), and the key is built
here at run time, never written to the repository in one piece (03 §5.56 item 19).

Run on its own with a copied fixture's folder (python3 plant_keys.py /tmp/run2), it fills that copy in for a review by
hand; safe to run twice. It refuses any folder in this repository, so the repository never holds the key."""
import pathlib, sys

PLACEHOLDER = "__PLANTED_STRIPE_KEY__"
FAKE_KEY = "sk_" + "live_" + "51HxQ2bK7mVt9RwPq3LzN8cYdF2gJ6sA"  # not a real key: an invented one in Stripe's live-key shape

def fill(folder):
    """Put the fake key in place of the placeholder in every text file of a copied fixture; returns how many files."""
    n = 0
    for p in pathlib.Path(folder).rglob("*"):
        if p.is_file() and not p.is_symlink() and p.name != "plant_keys.py" and p.suffix in (".js", ".ts", ".py", ".json", ".html", ".env", ".md"):
            try: t = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError): continue
            if PLACEHOLDER in t: p.write_text(t.replace(PLACEHOLDER, FAKE_KEY), encoding="utf-8"); n += 1
    return n

if __name__ == "__main__":
    repo = pathlib.Path(__file__).resolve().parent.parent
    t = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else None
    inside = t is not None and (str(t).casefold() + "/").startswith(str(repo).casefold() + "/")  # anywhere in the repository, in any case (a case-blind disk)
    if t is None or inside or (t / ".git").exists():
        sys.exit("usage: python3 plant_keys.py <a copy of a fixture, outside this repository>")
    print(f"planted the fake key in {sys.argv[1]}" if fill(sys.argv[1]) else "nothing to plant (already planted, or no placeholder)")
