# Security policy

## Reporting a vulnerability

Please report security problems privately, so they can be fixed before they are public:

1. Go to the repository's **Security** tab and choose **Report a vulnerability** (GitHub's private vulnerability reporting), or open https://github.com/truerevelationR2D2/curmudgeon/security/advisories/new.
2. Describe the problem, the version (`/plugin` shows it, or `.claude-plugin/plugin.json`), and the steps or files that show it.

Please don't open a public issue for a security problem. Anything else, including questions and ordinary bugs, goes in [Issues](https://github.com/truerevelationR2D2/curmudgeon/issues).

## What to expect

- A first reply within 7 days.
- A fix in the next release when the report is confirmed, with a regression test that fails on the old code, as every Curmudgeon fix has.
- Credit in the release notes, unless you'd rather not be named.

## Supported versions

Only the latest release gets security fixes. Update with `/plugin` (Installed tab, **Update now**) or `claude plugin update curmudgeon@curmudgeon`.

## Scope

Curmudgeon runs on your own computer with your permissions. Its hooks keep its own review agents blind to each other and protect its state files; they are not a sandbox against hostile code, as the README explains. Reports about that boundary are welcome. What the plugin collects and sends is described in [PRIVACY.md](plugin/PRIVACY.md).
