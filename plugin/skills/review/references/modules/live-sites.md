# Optional module: live sites and real sends

Read this when a run's page isn't on this computer, or when it would send data to a local server for real.

A live URL (not localhost) loads only when the owner's `.critic/scope.json` lists its origin (`scripts/scope.py`
documents the format) and the run carries `--allow-live HOST`. Ask the user to type the host on every run, with one
line on why ("This loads a real website at HOST. Use it only on a test copy you own."), never fill it in yourself, and
then record it with `critic_ledger.py consent live HOST`. The scan and `browse.py` refuse a live host without it, and
then send only GET, HEAD and OPTIONS, up to the target's request cap for the whole review run.

`--allow-writes` (a click that sends data to the user's real local server) likewise needs `critic_ledger.py consent
writes` after the user's yes.

A scope.json that git tracks, or one in a folder that isn't the top of its own git work tree, could have come with the
code: it isn't used until the owner approves it (`critic_ledger.py approve scope.json --show`, then approve on their
yes).
