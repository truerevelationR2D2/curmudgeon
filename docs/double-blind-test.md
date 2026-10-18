# Double-blind tests: Curmudgeon against another AI (October 2026)

## Round 1: release 4.1.0

Curmudgeon reviewed its own release 4.1.0 (commit `5b7e035`) using its usual pipeline: three blind reviewers, a vote counted by a script, a dedup step and blind verification. Separately, ChatGPT reviewed the same commit from the source on GitHub. Neither saw the other's findings.

ChatGPT's findings were then put through Curmudgeon's own checks: the quote check, then blind verification by checkers that ran the code.

| | Curmudgeon | ChatGPT |
|---|---|---|
| Findings | 19 raised, 13 kept after the vote | 10 raised |
| Failed the quote check | 0 | 1 (the right code, cited 25 lines off) |
| Refuted by verification | 0 | 0 |
| Confirmed by verification (all 10 of ChatGPT's were verified, including the one the quote check failed) | 13 (all kept) | 10 (5 at the stated impact) |
| Real but rated one level too high | 1 (a High judged Medium) | 5 (Mediums judged Low) |
| **Found by both** | **0** | **0** |

Every finding from both reviews was a real problem. Not one appeared in both.

What this showed:
- **Reviewers from one model family share blind spots.** Curmudgeon's three reviewers agreed with one another often enough to merge findings, yet missed all ten of ChatGPT's. ChatGPT, in turn, missed all of theirs. A reviewer from another family adds real coverage. That is why version 4.2 adds the optional outside reviewer.
- **Running the code keeps impacts honest.** ChatGPT couldn't run anything, and half its findings were rated one level too high. Curmudgeon's reviewers ran most of theirs.
- **Outside citations need checking.** One citation was 25 lines off and four more were 2–4 lines off. So the outside reviewer's findings get the same quote check as Curmudgeon's own.

Every finding from both reviews was fixed in 4.1.1.

**How overlap was counted:** the same way Curmudgeon merges its own reviewers. Two findings are the same issue when one fix resolves both: matched first by file, quote and wording, then grouped by the blind dedup agent.

## Round 2: release 4.1.1

ChatGPT got a recheck brief with raw links at the pinned commit. Its answer went through the new outside-reviewer step: load, quote check, tally, dedup and blind verification.

| | Curmudgeon | ChatGPT |
|---|---|---|
| Findings | 19 raised by 3 reviewers, 10 issues after merging | 7 raised |
| Failed the quote check | 0 | 1 (cited about 24 lines off, on a line that appears twice) |
| Cited at the wrong line, moved to the quote's one real line | – | 3 |
| Refuted by verification | 0 | 0 |
| Confirmed | 10 (2 lowered to Low) | 6 (none lowered) |
| **Found by both** | **2** | **2** |

The final list held 14 confirmed issues, and only 2 were found by both reviewers. ChatGPT's line numbers were off by a steady 16–24 lines, probably because its file viewer drops blank lines. So since 4.2, an outside finding whose quote is long and appears on exactly one line is moved to that line, and the move is recorded.
