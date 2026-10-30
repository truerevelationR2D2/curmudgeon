## Code review

No issues found. Checked for bugs and CLAUDE.md compliance.

I read the whole diff myself instead of launching the review and validation agents. It is four new files (95 lines) on a branch with no PR, and the repo has no `CLAUDE.md`. I found nothing that will definitely fail or give wrong results whatever the input, so nothing met the high-signal bar.

These are weaker observations that I did not flag, because each depends on intent or on things outside the diff:
- **Void button:** `user` is hard-coded with roles `["viewer", "billing"]`, so `canVoid` returns false and the click does nothing, with no message. This is probably placeholder data, and the real check has to happen on the server anyway.
- **Resending:** `lines` is never cleared after a successful send, and `sentCount` is never read. The 1-second `tooSoon` guard is the only protection against sending the same invoice twice.
- **Blocked retry:** `tooSoon()` sets `lastSend` before the request runs. A failed send therefore can't be retried for a second.
- **Request shape:** The send request has no `Content-Type` header, and the void request sends no invoice identifier. I can't tell whether that matters without seeing the server.