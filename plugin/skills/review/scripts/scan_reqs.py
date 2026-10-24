"""The requirements and intent lens (SC-55), our own rules and code.

Requirement ids look like REQ-12, FR-3, NFR-7, US-4, AC-2 or SPEC-9. A requirement is DEFINED where a document
(.md, .rst, .txt, .adoc, .feature) starts a line, a list item, a heading or a table cell with its id. It is CITED where
a test file mentions the id. From those the scan builds a requirement-to-test table (.critic/scan/requirements.md) and:

  req-undefined   WARN  a test cites a requirement id no document defines: the test claims to cover something nobody
                        wrote down (a typo, or a deleted requirement).
  req-untested    NOTE  a defined requirement no test cites.

The evidence rule that goes with this lens lives in the merge script: a finding may say what requirement it rests on,
`"requirement": {"basis": "stated", "where": "docs/req.md:12"}` or `{"basis": "inferred", "why": "..."}`. A stated one
must cite a real line (otherwise it counts as inferred), and a finding that rests on an inferred requirement can never
be Critical or High on its own: the script caps it at Medium and says so."""
import pathlib, re

ID = re.compile(r"\b(?:REQ|FR|NFR|US|AC|SPEC)-\d+\b")
DEFINE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+|\|\s*)?(?:\*\*|__|`)?((?:REQ|FR|NFR|US|AC|SPEC)-\d+)(?:\*\*|__|`)?\s*(?:[:.)|\-–—]|\s)")
DOC_EXT = {".md", ".rst", ".txt", ".adoc", ".feature"}

def is_doc(rel): return pathlib.PurePosixPath(rel.replace("\\", "/")).suffix.lower() in DOC_EXT

def is_test(rel):
    p = pathlib.PurePosixPath(rel.replace("\\", "/"))
    n = p.name
    return (p.suffix in (".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".go", ".rb", ".java", ".kt", ".cs") and
            (n.startswith("test_") or n.endswith(("_test.py", "_test.go", "_spec.rb", "Test.java", "Tests.cs", "Test.kt")) or re.search(r"\.(test|spec)\.[jt]sx?$|\.(test|spec)\.[mc]js$", n) is not None
             or any(x in ("test", "tests", "__tests__", "spec") for x in p.parts[:-1])))

def check(docs, tests, emit):
    """docs and tests: {rel: text}. Returns the table rows [(id, where_defined, text, [citing places])]."""
    defs = {}
    for rel, text in sorted(docs.items()):
        for i, l in enumerate(text.split("\n"), 1):
            m = DEFINE.match(l)
            if m and m.group(1) not in defs: defs[m.group(1)] = (f"{rel}:{i}", l.strip()[:160])
    cites = {}
    for rel, text in sorted(tests.items()):
        for i, l in enumerate(text.split("\n"), 1):
            for rid in sorted(set(ID.findall(l))):
                cites.setdefault(rid, []).append((f"{rel}:{i}", l.strip()[:160]))
    for rid, places in sorted(cites.items()):
        if rid not in defs:
            where, line = places[0]
            emit("WARN", "req-undefined", "requirements", where, f"this test cites {rid}, which no requirements document defines (a typo, or a requirement that was removed)", line)
    for rid, (where, line) in sorted(defs.items()):
        if rid not in cites and tests:
            emit("NOTE", "req-untested", "requirements", where, f"{rid} is defined here but no test cites it", line)
    return [(rid, where, line, [p for p, _ in cites.get(rid, [])]) for rid, (where, line) in sorted(defs.items())]

def table(rows):
    out = ["# Requirements and the tests that cite them", "", "| Requirement | Defined at | Cited by tests |", "| --- | --- | --- |"]
    for rid, where, _, cites in rows:
        out.append(f"| {rid} | {where} | {', '.join(cites[:6]) + (' …' if len(cites) > 6 else '') if cites else 'none'} |")
    if not rows: out.append("| (none found) | | |")
    return "\n".join(out) + "\n"
