# Sandbox simulation

Run the scenarios that apply to the payload type, and only those:
| Payload | Scenarios |
| --- | --- |
| UI (a page or app) | all, 0–10 |
| Code with no interface (library, script, hook, CLI) | 1–7 and 10, plus bad arguments, missing files, paths with spaces |
| Document or plan | none: check claims, arithmetic, contradictions and decisions instead |
| Tests (the change adds or touches tests) | 11, on top of the scenarios for the code they test |

To drive a page step by step, use `python3 <scripts>/browse.py start PAGE --session <your notes>/browse.json`, then `browse.py step click e3 --session ...` and so on: each step returns the controls (e1, e2 ...), console errors, the network log and a screenshot. Clicks run on a simulated page: a running app or live site is recorded once and replayed offline, and anything the page tries to send is answered by the simulation and never sent, so you may click Delete or Pay to see what they do. Before a click that matters, say what should happen with `--expect "..."`; the step returns before-and-after screenshots, the text that changed and what the page tried to send, and a mismatch is your finding. `browse.py record /PATH` adds a page the recording doesn't hold. Sending data to a real local server needs the lead to ask the user before `--allow-writes`. Run each against the payload. Drive the real app where you can start it: a local HTTP server and Python Playwright (only if it is already installed; never install it). Otherwise trace the code, and say "traced" in the ledger line. Record each as one line: scenario → what happens → finding id or "holds".

0. **Interactive state check (always first for UI):** every control: does focus look different from rest, does hover, does clicking change anything visible (no dead controls), is there layout shift on load? The scripted checks measure these; you look at the screenshots for what they can't.
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
11. **Break it and rerun (tests of the tests):** in your private copy, break the behaviour a test names (flip a comparison, return early, drop the call it checks) and run that test. A test that still passes can't catch the bug it is named for: that is a finding, verified as executed. Change only your copy, never the project.
