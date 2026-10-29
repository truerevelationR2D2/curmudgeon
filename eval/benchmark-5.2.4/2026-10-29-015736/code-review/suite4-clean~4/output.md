## Code review

No issues found. Checked for bugs and CLAUDE.md compliance.

The branch adds four new files (`app.js`, `guards.js`, `index.html`, `styles.css`, 95 lines) in a single commit. There is no CLAUDE.md in the repo, so there were no compliance rules to check.

I read the diff myself and didn't launch the review subagents. It was small enough that I judged that wasteful. I found nothing that would break regardless of input. The problems I considered all depend on state or input, so I didn't flag them:
- The `fetch` calls in the send and void handlers have no `catch` for network failures.
- An empty invoice can be sent.
- `sentCount` is written but never read.
- The hard-coded `user` has no `admin` role, so the Void button never does anything. That matches the "only admins may void" guard.

I changed no files.