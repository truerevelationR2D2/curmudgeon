# Optional module: the local security database

Read this in security mode (`/curmudgeon:review security`), when `critic_run.py begin --security` prints the feed
step (03 §5.38, §5.40).

If the feed was never switched on and the user is present, ask once (**Off** first and the default). On yes, open the
folder window (`security_feed.py pick-folder`; NO_WINDOW means ask for the full path), show the size estimate
(`security_feed.py estimate --folder`), and have the user sign off on that size and pick a schedule (daily, weekly,
biweekly, monthly) before `security_feed.py set ... --signed-off` and `update`. Never ask in an unattended session.
If it is on and due, run `update` before the scan (exit 5: it grew past the signed-off size, so show the new
estimate and ask again).

The downloads send nothing about the project: size requests and public vulnerability files from OSV.dev and CISA.
Their log is `feed-log.jsonl` beside the settings in `~/.curmudgeon/feed`.
