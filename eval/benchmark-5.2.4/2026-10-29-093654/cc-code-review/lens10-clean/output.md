```json
[
  {
    "file": "app/auth.py",
    "line": 9,
    "summary": "login() ignores the password and always returns True, so authentication is bypassed.",
    "failure_scenario": "login('anyone', 'wrong-password', None) returns True. Any caller that gates access on this function lets every user in with any password."
  },
  {
    "file": "monitoring/alerts.yml",
    "line": 8,
    "summary": "The CheckoutErrors alert points its runbook_url at the disk-full runbook, which is the wrong runbook.",
    "failure_scenario": "A checkout-error page sends the on-call engineer to 'Disk full: check the largest folders'. That has nothing to do with checkout failures, so mitigation is delayed. No checkout runbook exists in docs/runbooks."
  },
  {
    "file": "docs/runbooks/disk-full.md",
    "line": 3,
    "summary": "The runbooks are single-step stubs with no diagnosis, mitigation, verification or escalation steps.",
    "failure_scenario": "During a disk-full or queue-backlog incident, 'Check the largest folders' and 'Scale the workers' give no commands, no safe-to-delete guidance, no worker limits, no success check and no escalation path. The on-call engineer has to improvise."
  },
  {
    "file": "monitoring/alerts.yml",
    "line": 4,
    "summary": "Alerts have no `for:` duration or severity label, and QueueBacklog and PaymentsDown have no summary annotation.",
    "failure_scenario": "A single 5-minute spike pages immediately, because there is no `for:` clause to absorb it. Without a severity label, Alertmanager cannot route or prioritize. The QueueBacklog and PaymentsDown pages arrive with no human-readable summary."
  },
  {
    "file": "monitoring/alerts.yml",
    "line": 19,
    "summary": "PaymentsDown alerts on `up == 0`, which is silent when the payments job disappears from scraping.",
    "failure_scenario": "If the payments target is removed from service discovery, or Prometheus stops scraping it, no `up` series exists and the expression returns nothing. The alert never fires while payments are down. It needs `absent(up{job=\"payments\"})` or an `or` clause."
  },
  {
    "file": "deploy/web.yaml",
    "line": 13,
    "summary": "The Deployment has no replicas, rollout strategy, liveness probe, resource requests or securityContext, and the template has no labels or selector.",
    "failure_scenario": "A Deployment without spec.selector and matching template labels is rejected by the API server (apps/v1). Even with those fixed, defaulting to a single replica with no requests gives no availability, bad scheduling and no restart on a hung process. The rollback and rollout behaviour is unspecified."
  },
  {
    "file": "app/settings/production.py",
    "line": 2,
    "summary": "Production settings define no SECRET_KEY, security cookie flags, HTTPS redirect or HSTS.",
    "failure_scenario": "Only DEBUG and ALLOWED_HOSTS are set. If the settings are Django-style, SECRET_KEY comes from an unspecified source and SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE and SECURE_SSL_REDIRECT stay at their insecure defaults. Cookies can then travel over plain HTTP."
  },
  {
    "file": "app/auth.py",
    "line": 12,
    "summary": "rotate() does not rotate anything and uses print() instead of logging.",
    "failure_scenario": "rotate(token) only prints the last 4 characters of the token to stdout. No new token is issued and the old one is not revoked, yet callers believe the rotation happened. The print also writes token material to stdout and bypasses the logging config."
  },
  {
    "file": "app/auth.py",
    "line": 7,
    "summary": "The username is logged on every login attempt at INFO and again at DEBUG, with no sanitization.",
    "failure_scenario": "A user who types their password into the username field has it written to the logs. A username containing newlines can forge log lines. The DEBUG line duplicates the INFO line, so it adds nothing. The log also has no outcome and no source IP."
  },
  {
    "file": "web/client.js",
    "line": 2,
    "summary": "call() logs userName to the console on every request and does not check the fetch response status or handle errors.",
    "failure_scenario": "The user name appears in browser console output on every call. A 401 or 500 response is returned as if it succeeded, so callers must remember to check `.ok`. A missing apiKey sends an `x-api-key: undefined` header."
  }
]
```