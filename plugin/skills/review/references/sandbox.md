# Sandbox simulation

Run the scenarios that apply to the payload type, and only those:
| Payload | Scenarios |
| --- | --- |
| UI (a page or app) | all, 0–10 |
| Code with no interface (library, script, hook, CLI) | 1–7 and 10, plus bad arguments, missing files, paths with spaces |
| Document or plan | none: check claims, arithmetic, contradictions and decisions instead |

Run each against the payload. Drive the real app where you can start it: a local HTTP server and Python Playwright, or the Playwright MCP tools when they are connected. Otherwise trace the code, and say "traced" in the ledger line. Record each as one line: scenario → what happens → finding id or "holds".

0. **Interactive state check (always first for UI):** every control: does focus look different from rest, does hover, does clicking change anything visible (no dead controls), is there layout shift on load? The scripted pass measures these; you look at the screenshots for what it can't.
1. **First run, empty:** no data, no settings. What does the user see, and can they act?
2. **Corrupted or old saved data:** bad JSON, a missing field, a previous version's shape.
3. **Fast hands:** double-click, two creates in one millisecond, typing during a save.
4. **Context switch mid-flight:** change the selected item, view or project while a timer, save or request is pending.
5. **Slow, failing or offline network:** responses late, out of order, 4xx/5xx, or never. Does a failure ever show as success?
6. **Close or refresh mid-action:** is the last change kept?
7. **Scale ×10 and ×100:** 500 items, a 50,000-word document. Count the work per keystroke and per render.
8. **Keyboard only and screen reader:** reach every control, see focus, escape every widget, every control has a name, status changes are announced.
9. **Phone width (390 px) and 200% zoom:** sideways scroll, tap targets, hover-only controls, clipped text.
10. **Hostile input:** `<img src=x onerror=alert(1)>` and `"&q=1#` in every field that is rendered or sent anywhere.
