# Finding record

What every reviewer and verifier writes, and how it reads. Reviewers read this file, not the whole output contract: the teardown's layout (`output-contract.md`) is the lead's job.

## Writing rules (how the review reads)
- The first line is a finding or the banner (in the teardown: the banner, then the verdict line, as `output-contract.md` sets out). No greeting, no summary of what the work does, no praise, no recap, no closer. No "just", "really", "basically", "simply".
- Short sentences, active voice, one term per thing. Code, paths, commands and errors stay exact.
- Never drop "not", "never", "no", "only" or "except" to save words.
- **Security findings and anything irreversible get full, plain sentences**, never shorthand.
- Unsure? Write `q:` and the question. Don't hedge.

## Finding record (what reviewers write, as JSON)
A review file is `{"findings": [ ...finding records... ], "set_aside": [ {"file", "line", "what", "guard"} ], "sandbox": [ {"scenario", "happens", "result", "how"} ]}`; `sandbox` holds one line per scenario from `sandbox.md` (result "holds" or the finding's title, how driven or traced), numbered SB1, SB2 ... by the script into `.critic/counts.md`; a plain list of findings is still accepted. `set_aside` lists candidates the reviewer dropped and the guard it relied on: logged in the tally, never counted. `coverage` (`read`, `not_reached`: file paths) is how the script computes the Not reviewed line.

| Field | Meaning |
| --- | --- |
| `category` | Short kind of problem: xss, data-loss, race, a11y-focus, domain-leak, claim, ai-tell… |
| `impact` | Critical, High, Medium or Low (see `rubrics.md`) |
| `file`, `line` | Where. For a UI finding with no line, the file that renders it |
| `quote` | The code or text, **copied exactly** from the file. The merge script retracts a finding whose quote isn't there |
| `title` | One line: the problem |
| `evidence` | What was checked and seen (scripted ids, sandbox lines, file:line) |
| `failing_case` | The concrete input or sequence, and the wrong result. Required for Critical, High and Medium |
| `verified` | `executed` (you ran it and saw it fail), `traced` (followed the code path), or `inferred` |
| `remediation` | The structural fix, in one or two sentences |
| `requirement` | Optional. What the finding rests on when it is about intent or behaviour: `{"basis": "stated", "where": "docs/spec.md:12"}` when a document says it (the script checks the line exists), or `{"basis": "inferred", "why": "what you inferred it from"}`. A finding that rests on an inferred requirement is capped at Medium by the script: inferred is never presented as stated |
| `difficulty`, `exploit_scenario`, `fix_short`, `fix_long` | Audit mode (after Trail of Bits' report format): how hard the failure is to trigger (Low, Medium or High), who could trigger it and how, the quick fix, and the lasting fix (often a rule file or a test that keeps the bug class out). Optional elsewhere |

Group one issue found in several places into one record. Stable ids are made from the file, category and quote, so the same issue keeps its id across runs.
