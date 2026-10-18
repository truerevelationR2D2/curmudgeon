"""Secret detection for Curmudgeon scan. Our own rules, written from the providers' published key formats (the idea of
provider rules plus an entropy check comes from gitleaks, MIT; no rule text was copied). Every text file is checked,
dotfiles and configs included. Matches are shown redacted."""
import math, re

# (rule id, severity, regex, label). Formats are the providers' documented key shapes.
PROVIDERS = [
    ("stripe-key", "FAIL", r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}", "Stripe live secret key"),
    ("stripe-test-key", "WARN", r"\b(?:sk|rk)_test_[0-9A-Za-z]{16,}", "Stripe test secret key"),
    ("aws-access-key", "FAIL", r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b", "AWS access key id"),
    ("aws-secret", "FAIL", r"(?i)aws.{0,20}(?:secret|private).{0,20}[\"'=:\s]+[0-9A-Za-z/+]{40}\b", "AWS secret access key"),
    ("github-token", "FAIL", r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,}\b|\bgithub_pat_[0-9A-Za-z_]{60,}", "GitHub token"),
    ("gitlab-token", "FAIL", r"\bglpat-[0-9A-Za-z_\-]{20,}", "GitLab personal access token"),
    ("slack-token", "FAIL", r"\bxox[abposr]-[0-9A-Za-z-]{10,}", "Slack token"),
    ("slack-webhook", "FAIL", r"https://hooks\.slack\.com/services/T[0-9A-Z]{8,}/B[0-9A-Z]{8,}/[0-9A-Za-z]{20,}", "Slack webhook URL"),
    ("google-api-key", "FAIL", r"\bAIza[0-9A-Za-z_\-]{35}\b", "Google API key"),
    ("gcp-service-account", "FAIL", r"\"type\"\s*:\s*\"service_account\"", "Google service account JSON"),
    ("anthropic-key", "FAIL", r"\bsk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_\-]{80,}", "Anthropic API key"),
    ("openai-key", "FAIL", r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{32,}", "OpenAI API key"),
    ("twilio-key", "FAIL", r"\bSK[0-9a-f]{32}\b", "Twilio API key"),
    ("sendgrid-key", "FAIL", r"\bSG\.[0-9A-Za-z_\-]{22}\.[0-9A-Za-z_\-]{43}\b", "SendGrid API key"),
    ("mailgun-key", "FAIL", r"\bkey-[0-9a-f]{32}\b", "Mailgun API key"),
    ("npm-token", "FAIL", r"\bnpm_[0-9A-Za-z]{36}\b", "npm access token"),
    ("pypi-token", "FAIL", r"\bpypi-AgEIcHlwaS5vcmc[0-9A-Za-z_\-]{50,}", "PyPI upload token"),
    ("discord-webhook", "FAIL", r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]{60,}", "Discord webhook URL"),
    ("private-key", "FAIL", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----", "private key"),
    ("jwt", "WARN", r"\beyJ[0-9A-Za-z_\-]{10,}\.eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}", "JSON Web Token"),
    ("db-url-password", "FAIL", r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:\s/]+:[^@\s/]{4,}@", "database URL with a password"),
    ("basic-auth-url", "WARN", r"https?://[^:\s/@]+:[^@\s/]{6,}@[\w.-]+", "URL with an embedded password"),
]
COMPILED = [(r, s, re.compile(x), l) for r, s, x, l in PROVIDERS]
GENERIC = re.compile(r"(?i)\b([\w.-]*(?:api[_-]?key|secret|token|passw(?:or)?d|pwd|auth|credential|private[_-]?key)[\w.-]*)\b\s*[:=]\s*[\"']([^\"'\s]{12,})[\"']")
PLACEHOLDER = re.compile(r"(?i)^(x+|\*+|your[_-]|example|changeme|placeholder|dummy|test|sample|redacted|<.*>|\$\{.*\}|process\.env|os\.environ|null|none|true|false)")

def entropy(s):
    if not s: return 0.0
    n = len(s); return -sum(c / n * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))

def mask(value):
    """Keep only the first 4 characters of a secret: enough to recognise it, useless to anyone reading the report."""
    return value[:4] + "…[redacted]"

TOKEN = re.compile(r"[A-Za-z0-9_\-+/=.]{20,}")
def redact(line, spans):
    """Replace every secret span in full, then blanket-mask any other long high-randomness token (a second pass, so a
    key no rule knows still never reaches a report), then trim. Evidence never carries a usable secret."""
    out, last = [], 0
    for a, b in sorted(spans):
        if b <= last: continue
        a = max(a, last); out.append(line[last:a]); out.append(mask(line[a:b])); last = b
    out.append(line[last:])
    t = "".join(out)
    t = TOKEN.sub(lambda m: mask(m.group(0)) if "[redacted]" not in m.group(0) and entropy(m.group(0)) >= 3.5 else m.group(0), t)
    return t.strip()[:140]

def secret_spans(chunk):
    """Every secret on the line: all provider matches plus generic credential values."""
    spans = [(m.start(), m.end()) for _r, _s, rx, _l in COMPILED for m in rx.finditer(chunk)]
    for m in GENERIC.finditer(chunk):
        if not PLACEHOLDER.match(m.group(2)) and entropy(m.group(2)) >= 3.5: spans.append((m.start(2), m.end(2)))
    return spans

def windows(line, size=20000, overlap=400):
    """Very long lines (minified bundles) are scanned in overlapping windows, never skipped."""
    if len(line) <= size: yield 0, line; return
    for start in range(0, len(line), size - overlap): yield start, line[start:start + size]

def scan(rel, text, emit):
    """emit(sev, rule, area, where, what, evidence)"""
    for i, line in enumerate(text.split("\n"), 1):
        seen = set(); taken = []  # absolute spans already reported: one key is one finding, whichever rules match it
        for off, chunk in windows(line):
            spans = secret_spans(chunk); hit = False
            for rid, sev, rx, label in COMPILED:
                for m in rx.finditer(chunk):
                    key = (rid, off + m.start()); A, B = off + m.start(), off + m.end()
                    if key in seen or any(A < y and x < B for x, y in taken): continue
                    seen.add(key); taken.append((A, B)); hit = True
                    if rid == "private-key": ev = m.group(0)  # the header only: the key body never goes into a report
                    else:
                        a, b = max(0, m.start() - 60), min(len(chunk), m.end() + 40)
                        ev = redact(chunk[a:b], [(max(0, x - a), min(b, y) - a) for x, y in spans if y > a and x < b])
                    emit(sev, f"secret-{rid}", "safety", f"{rel}:{i}", f"{label} in a file (rotate it: anything committed or shipped is exposed)", ev)
            m = GENERIC.search(chunk)
            if m and not PLACEHOLDER.match(m.group(2)) and entropy(m.group(2)) >= 3.5 and not any(x <= m.start(2) < y for x, y in [(mm.start(), mm.end()) for _r, _s, rx, _l in COMPILED for mm in rx.finditer(chunk)]):
                a, b = max(0, m.start() - 20), min(len(chunk), m.end() + 20)
                emit("WARN", "secret-generic", "safety", f"{rel}:{i}", f"hard-coded credential in `{m.group(1)}` (high-randomness value)", redact(chunk[a:b], [(max(0, x - a), min(b, y) - a) for x, y in spans if y > a and x < b]))
