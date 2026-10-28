# Security policy

## Reporting a vulnerability

Please report security problems privately, so they can be fixed before they are public. Don't put any details of a security problem in a public issue.

Use GitHub's private vulnerability reporting: on the repository's **Security** tab, choose **Report a vulnerability**, or open https://github.com/truerevelationR2D2/curmudgeon/security/advisories/new. Only you and the maintainer can see the report. Include the version (`/plugin` shows it, or `.claude-plugin/plugin.json`) and the steps or files that show the problem.

If you can't use that form, open an issue at https://github.com/truerevelationR2D2/curmudgeon/issues/new with the title **Security contact request** and no details of the problem, and the maintainer will reply with another private way to send it.

Anything that isn't a security problem, including questions and ordinary bugs, goes in [Issues](https://github.com/truerevelationR2D2/curmudgeon/issues) as usual.

## What to expect

- A first reply within 7 days.
- A fix in the next release when the report is confirmed, with a regression test that fails on the old code, as every Curmudgeon fix has.
- Credit in the release notes, unless you'd rather not be named.

## Supported versions

Only the latest release gets security fixes. Update with `/plugin` (Installed tab, **Update now**) or `claude plugin update curmudgeon@curmudgeon`.

## Scope

Curmudgeon runs on your own computer with your permissions. Its hooks keep its own review agents blind to each other and protect its state files; they are not a sandbox against hostile code, as the README explains. Reports about that boundary are welcome. What the plugin collects and sends is described in [PRIVACY.md](plugin/PRIVACY.md).
