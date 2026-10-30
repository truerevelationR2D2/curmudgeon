# Labeller brief (5.2.4 benchmark, ruling §5.53)

Every labeller, and the tiebreaker, gets exactly this brief with its packet file and the app folder filled in. Nothing
else: not the tool that wrote a finding, not another labeller's labels, not the answer key.

---

You are checking code-review findings against the code they describe. Someone you don't know wrote each finding; some
are right and some are wrong. Your job is to say which, by reading the code.

The app is in `{APP_DIR}`. Read only inside that folder. The findings are in `{PACKET_FILE}`: a JSON list of
`{"id", "app", "finding"}`.

For every finding, open the file and lines it points to (search the folder when it gives none) and decide:

- **verdict**
  - `real`: the code really behaves as the finding says, and it matters to someone using or maintaining the app.
  - `trivial`: true, but not worth acting on (style, naming, a comment, a nit, a theoretical case with no way to reach it).
  - `wrong`: the code does not do what the finding says (it misreads the code, the guard it says is missing is
    there, the case it describes cannot happen), or it makes no claim you can check.
  - `none`: not a finding at all: a heading, a summary, a note about the review itself.
- **actionable** (`true` or `false`): could a developer fix it from what the finding says, without first working out
  what the problem is? `false` for `none`.
- **severity** (only when `real`, otherwise `null`): `critical` (data loss, a security hole an outsider can use, the
  app unusable), `high` (a main feature broken or a security weakness), `medium` (a feature wrong in some cases), `low`
  (a minor or rare problem).

Judge each finding on its own. Don't credit a finding for a problem it didn't describe, and don't mark it wrong because
it missed something else. When you can't tell, say `wrong` only if the claim can't be checked; otherwise decide from
the code as written.

Reply with only a JSON list, one object per finding, in any order, nothing else:

```json
[{"id": "F0a1b2c3d", "verdict": "real", "actionable": true, "severity": "medium"}]
```
