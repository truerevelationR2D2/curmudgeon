# Optional module: browser checks

Read this when a run gives `critic_scan.py` a `--page`. The browser checks need Playwright with Chromium already
installed; without it they are reported as unavailable, never as passed, and Curmudgeon never installs it.

With a page, the scan adds: axe-core (WCAG 2.0–2.2, plus undecided results), keyboard reach, focus visibility, focus
hidden behind other content, a screen-reader view, dead controls, layout shift, reflow at 320 and 390 px, speed (median
of three loads) and visual baselines. The dead-control check never sends data: anything but a same-site read is aborted,
and controls that look destructive (by name, id, link, form action or title: Delete, Pay, Send) are clicked only in the
simulation, where writes are answered locally and a running app is replayed from a one-time read-only recording.
Other controls are clicked on the page as it is served, so point the scan at a test copy, never at real data.

A page that isn't on this computer is a live site: see `live-sites.md`. Reviewers and verifiers drive pages step by
step with `browse.py`; their agent files say how.
