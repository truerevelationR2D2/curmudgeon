**BLOCK** · Counts: 1 Critical, 0 High, 1 Medium, 4 Low

Three blind reviewers read all 9 files (74 lines). The scripted scan found nothing. One verifier ran `login('alice', 'wrong-password', None)` and got `True`. Every other finding is traced or inferred, because the reviewers had no shell. I changed no files; the full teardown is in `.critic/last-review.md`.

**Findings**
- **C1, Critical, confirmed (3/3):** `app/auth.py:11`. `login()` returns `True` for every caller and never reads the password. A missing API key only logs a warning. Check the password against a salted hash, reject a missing key, and add a wrong-password test.
- **C2, Medium, confirmed (3/3):** `monitoring/alerts.yml:8`. The CheckoutErrors alert links to `docs/runbooks/disk-full.md`, which says only "1. Check the largest folders." No checkout runbook exists, so write one and relink the alert.
- **C3, Low (2/3):** `app/auth.py:15`. `rotate()` prints the last 4 characters of a live token with `print`. A token of 4 characters or fewer prints whole.
- **C4, Low (2/3):** `deploy/web.yaml:11`. There is no livenessProbe and no explicit resource requests. This one is inferred, not driven.
- **C5 and C6, Low (2/3 each):** `docs/runbooks/disk-full.md:3` and `docs/runbooks/queue-backlog.md:3`. Each runbook is a single step with no command, limit, recovery check or escalation.

**Not counted:** five findings that only one reviewer raised and nobody executed. They are listed in the teardown in case you want to look:
- The PaymentsDown runbook link is an `example.com` placeholder.
- `runbook_url` values are repo paths, not URLs.
- A missing `apiKey` in `web/client.js` is sent as the string "undefined".
- `web/client.js` logs the request URL and user name to the console.
- `app/report.py` logs a hard-coded password policy.

**Not checked:** whether the PaymentsDown URL exists, and how Alertmanager renders `runbook_url`, because the receiver config isn't in the repo. The variant hunt found no further instances of the Critical.

**Next steps:** `/curmudgeon:review fix` fixes everything. `/curmudgeon:fix patch [id]` fixes one finding.