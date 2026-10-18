# Double-blind test: Curmudgeon against another AI (October 2026)

Curmudgeon reviewed its own release 4.1.0 (commit `5b7e035`) using its usual pipeline: three blind reviewers, a vote counted by a script, a dedup step and blind verification. Separately, ChatGPT reviewed the same commit from the source on GitHub. Neither saw the other's findings.

ChatGPT's findings were then put through Curmudgeon's own checks: the quote check, then blind verification by checkers that ran the code.

| | Curmudgeon | ChatGPT |
|---|---|---|
| Findings | 19 raised, 13 kept after the vote | 10 raised |
| Failed the quote check | 0 | 1 (the right code, cited 25 lines off) |
| Refuted by verification | 0 | 0 |
| Confirmed by verification | 13 (all kept) | 10 (5 at the stated impact) |
| Real but rated one level too high | 1 (a High judged Medium) | 5 (Mediums judged Low) |
| **Found by both** | **0** | **0** |

Every finding from both reviews was a real problem. Not one appeared in both.

What this showed:
- **Reviewers from one model family share blind spots.** Curmudgeon's three reviewers agreed with one another often enough to merge findings, yet missed all ten of ChatGPT's. ChatGPT, in turn, missed all of theirs. A reviewer from another family adds real coverage. That is why version 4.2 adds the optional outside reviewer.
- **Running the code keeps impacts honest.** ChatGPT couldn't run anything, and half its findings were rated one level too high. Curmudgeon's reviewers ran most of theirs.
- **Outside citations need checking.** One citation was 25 lines off and four more were 2–4 lines off. So the outside reviewer's findings get the same quote check as Curmudgeon's own.

Every finding from both reviews was fixed in 4.1.1.
