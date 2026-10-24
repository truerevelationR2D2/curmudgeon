# Output contract

## Writing rules (how the review reads)
- The first line is a finding or the banner. No greeting, no summary of what the work does, no praise, no recap, no closer. No "just", "really", "basically", "simply".
- Short sentences, active voice, one term per thing. Code, paths, commands and errors stay exact.
- Never drop "not", "never", "no", "only" or "except" to save words.
- **Security findings and anything irreversible get full, plain sentences**, never shorthand.
- Unsure? Write `q:` and the question. Don't hedge.

## Finding record (what reviewers write, as JSON)
A review file is `{"findings": [ ...finding records... ], "set_aside": [ {"file", "line", "what", "guard"} ]}`; a plain list of findings is still accepted. `set_aside` lists candidates the reviewer dropped and the guard it relied on: logged in the tally, never counted. `coverage` (`read`, `not_reached`: file paths) is how the script computes the Not reviewed line.

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

Group one issue found in several places into one record. Stable ids are made from the file, category and quote, so the same issue keeps its id across runs.

## Banner
If the judgment and detector passes could not run in separate contexts, the first line is `DEGRADED: single context (<why>)`. If no independent reviewer was possible at all and the user asked for a fresh review, the first line is `BLOCKED: no independent reviewer available` and the review stops there.

## First line: the verdict
After the banner (if any), the first line is the verdict and the counts, so a reader who stops there has the answer: `**BLOCK** · Counts: 1 Critical, 2 High, 0 Medium, 3 Low` (copied from `.critic/counts.md`; the same word and counts as section 5).

## Quiet mode (`/curmudgeon:review quiet`, or when the user asks for a short review)
Critical and High findings are written in full. Medium and Low findings are folded into one counted list under their section, one line each with the same id and impact (`- **C4** \`file:line\` | Medium | the defect in a few words`). Every count stays exact; nothing is dropped, only shortened. INTENT GATE, RISK MAP and SANDBOX LEDGER shrink to one line each.

## Headers (exactly these)
#### INTENT GATE
The questions asked and the answers, or "not needed: <why>". If there was a stated intent: **Asked but not done:** … · **Done but not asked:** … (or "none").
#### RISK MAP
Files ranked by risk (what saves, renders input, moves money, holds secrets, runs async), with the reading budget spent on each.
#### SANDBOX LEDGER
Scenario → what happens → finding id or "holds" (driven or traced).
#### 1. CODE AND ARCHITECTURE
Findings of every impact, worst first.
- **C1** `file:line` | **IMPACT: Critical** | `F-1a2b3c4d` · confidence confirmed · votes 3/3 | **Defect:** …
- **Evidence:** what was checked and what was seen, with ids (S012 for a scripted row, SB4 for a sandbox line).
- **Failing case:** the concrete input or sequence, and the wrong result.
- **Remediation theory:** the structural change in one or two sentences.
#### 2. UI/UX & INTERACTION FRICTION
- **U1** `screen / component` | **IMPACT: High** | **UX flaw:** … then Evidence, Failing case, **Heuristic violated** (named heuristic or WCAG criterion with the right level), Remediation theory.
#### 3. THE "ANTI-AI" CLEANUP
- **A1** `where` | **IMPACT: Low** | the tell, its **Evidence**, and the specific replacement. Skip tells the brief asked for, and say so.
#### 4. CLAIMS, NUMBERS AND CONSISTENCY
- **D1** `file:line` | **IMPACT: …** | only when documents, READMEs or plans are in the payload: the claim, its **Evidence** (the source it needs, or the recomputed arithmetic), and the correction.
#### 5. VERDICT
- One line: **BLOCK**, **CONCERNS** or **CLEAN**, in bold, and only one of the three in bold anywhere in this section (a past verdict such as "as delivered it was a block" is written in plain words). CLEAN is impossible while any Critical or High is open or deferred.
- A line starting `Counts:` with the counts by impact, copied from `.critic/counts.md` (they must add up to the findings listed). Put no other impact numbers on that line.
- Panel: how many reviewers, how many findings were dropped, retracted, refuted, hidden by the owner's rulings, or noted as like past dismissals (from `counts.md`).
- A finding with a memory note keeps its place and its count; add one line under it: `Like past dismissals: <reason> (memory N). Close with critic_ledger.py dismiss --like N, or keep.` Never drop or move a finding because of a note.
- The five fixes worth the most per hour.
- `Not checked:` everything in scope you did not verify, and why.
- `Not reviewed:` files skipped for the budget, binary or generated files, and checks that were blocked or unavailable. Mandatory, even when it's "nothing".
- `Variants:` the confirmed variants from `.critic/variants.md` (full tier), each with its id, impact and place; they are listed apart and are not in the Counts line.
- Change map: a link to `.critic/change-map.md`, never pasted in.

Low findings may use one line each: `L1 file:line: problem. fix.` They count as Low in the verdict.

## Refactor (full mode only)
```xml
<refactoring_manifest>
path — finding ids — rewrite | edit | new
</refactoring_manifest>
```
Then the files: complete files for pasted payloads; for files on disk, write them whole and show a diff summary.

```xml
<workspace_state_ledger>
CURRENT_REFACTOR: files or component
FIXED_DEFECTS: ids fixed and verified this round
PENDING_RISKS: [UNCERTAIN RISK] items and anything that needs the owner
ROUND: n of 3
</workspace_state_ledger>
```
Then the **Closure table**: id | status (fixed, deferred, won't fix) | where | how verified (scripted row gone, test added, scenario replayed). Every check result is one of pass, fail, unavailable, blocked or n/a.

## Hooks (end every response)
After a review (no files changed):
- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only that one.

After a refactor:
- `/curmudgeon:fix approve` to keep these changes.
- `/curmudgeon:fix iterate [component]` to go deeper on one part, or try another approach.
- `/curmudgeon:fix patch [issue]` to fix only that issue.
- `/curmudgeon:fix rollback` to undo this refactor.
