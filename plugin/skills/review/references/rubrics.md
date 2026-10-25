# Rubrics and the impact score

## Impact score
| Score | Meaning |
| --- | --- |
| **Critical** | Data loss or corruption; security (XSS, leaked secrets, broken access); money moved wrongly; crash on a core path; legal exposure; WCAG A failure or keyboard trap; blocks the main task |
| **High** | Hits users in normal use; WCAG AA failure; a race under ordinary timing; a performance cliff within 10× the current data; a success message for something that failed |
| **Medium** | Occasional friction; maintainability that will rot; degraded performance with workarounds; inconsistent behaviour |
| **Low** | A real fault a user can notice that loses nothing and misleads no one: a wrong label, a misaligned control, an unclear wording. It needs a concrete failing case like any finding |
| **Nit** | True but not a failure: polish, naming, style, a speculative concern with no failing case, a better way to write working code. Listed under Nits, never counted, never verified, never blocking (SC-79) |

When two findings share a score, the more likely one goes first. If you can't name what goes wrong for a user, it is a Nit, not a Low. **However rare the path, anything that loses or corrupts data, gives a wrong result, or reports a failure as success is High or worse, never Low**: how often it happens changes the order of the list, not the impact.

## Rubric 1: code
| Component | Fail condition (what AI code defaults miss) | Inspect | Remediation requirement |
| --- | --- | --- | --- |
| Error handling and edge cases | `catch {}` that swallows; a status never checked; success shown while the work failed; only the happy path; null, empty and huge inputs assumed away | Every catch, every promise without a handler, every write without a confirmed result, every function given empty, null or huge input | Each failure is shown to the user with a cause and a next step, recorded with context, and leaves data consistent |
| Type safety and boundaries | `undefined` flowing through optional chains; string/number confusion from inputs and storage; fields assumed present on old records; values put into URLs, HTML or SQL unencoded | Data from storage, files, imports, the network and the DOM; every place a value crosses into another language | One validator or normaliser per boundary; encode at every sink |
| Async and races | A debounce writing to whatever is "current" when it fires; responses applied out of order; state read after `await` without rechecking; double submit; a promise never awaited | Timers and closures over mutable state, request handlers, save queues, handlers that `await` | Capture the target at schedule time; one writer per record; abort or ignore stale responses; idempotent actions. Name the interleaving that breaks today |
| Scalability | O(n²) work per keystroke or render; `innerHTML +=` in loops; full re-renders on every change | Work per keystroke and per render; cost at 10× and 100× | State the cost and a budget; deliver the cached, incremental or batched version |
| State persistence | Parse at load with no try; quota errors swallowed; no flush on close; `Date.now()` ids; no version on the saved shape | Load, save, unload, id generation, schema changes | Guarded load with recovery; surfaced write failures; flush on `pagehide`; collision-free ids; a version and a migration path |
| **Domain leaks** | Business rules (pricing, tax, permissions, eligibility) written inside render code, handlers or components; I/O inside view functions; the same rule computed in two places | Arithmetic and conditionals on money, roles or status inside UI files | Move the rule to one pure, named function or domain object with its own test; the view only displays the result |
| Secrets and trust boundaries | Keys, tokens or passwords in client code or the repo; the client trusted to enforce limits | Any string that looks like a credential; any check that only the browser performs | Secrets live on a server; the server enforces; rotate anything already shipped |

Rows for the scripted lenses (tests of the tests, CI and supply chain, agent and MCP configuration, release and rollback, requirements and intent, operations) are in `lenses.md`; your brief names the sections that apply to this payload.

## Rubric 2: design (interface payloads only; your brief says when)
| Element | AI laziness pattern | Standard | Remediation requirement |
| --- | --- | --- | --- |
| Visual hierarchy | Everything the same weight; centred cards in a grid; walls of muted grey; a flat type scale | One primary action per screen; a deliberate type scale (steps of at least 1.25×) | Name the primary action, demote the rest; give sizes, weights and spacing |
| States and micro-interactions | No loading, empty, error, disabled or success state; controls that do nothing visible; no hover, focus or active difference; destructive actions with no confirm or undo | Every control shows what happened; empty states say what to do next; errors say what failed and how to fix it | List each missing state per component with its copy and behaviour |
| Responsive | Fixed widths; desktop squeezed onto a phone; hover-only controls; clipped text | Works at 390 px and 1360 px and at 200% zoom; nothing scrolls sideways | Breakpoint by breakpoint, with the CSS |
| Accessibility (WCAG 2.1 AA) | Contrast under 4.5:1; outlines removed; keyboard traps; unlabelled controls; placeholder as label; colour as the only signal; motion with no reduced-motion option | Full keyboard path with visible focus, a name on every control, measured contrast, no traps, zoom allowed | Cite the criterion and element. Get the level right: 2.5.5 (44 px targets) is **AAA** in 2.1; 2.5.8 (24 px) is AA in 2.2 |
| Off-the-shelf boilerplate | See `ai-tells.md` | A look chosen for this product and its users | Name each tell and replace it with a specific choice, unless the brief asked for it |
| Copy | Vague buttons ("Submit"), an action renamed mid-flow, errors that apologise or blur what happened, success with an exclamation mark for something unverified | The button says what happens; the same verb all the way through; errors name the problem and the fix | Rewrite each string |

## Not findings by default (the post-review filter)
These are dropped unless the reviewer shows a concrete, likely failing case with real impact. A project can add to the list, or remove items from it, under `## Not findings` in `.critic/rules.md`.
- Denial of service, rate limiting or resource exhaustion with no shown path to it.
- "Input should be validated" with no input that breaks something.
- Style that a formatter or linter in the project already enforces.
- A race with no named interleaving that breaks it.
- A missing test, on its own. Name the behaviour that's unprotected, and show it could break.
- Framework idioms used as documented.
- A "best practice" with no consequence in this code.
- Anything the ledger records as accepted.

## Severity descriptors (so impact means the same thing every run)
| Impact | Code | UI | Documents and plans |
| --- | --- | --- | --- |
| Critical | Loses or corrupts data, leaks a secret, moves money wrongly, runs attacker code, crashes the main path | The main task can't be done at all, or not by keyboard or screen reader | A wrong number or claim that a decision will rest on |
| High | Wrong result in normal use; a race under ordinary timing; failure shown as success | AA failure on a main path; a dead or misleading control | A requirement missed or contradicted |
| Medium | Wrong in an edge case with a workaround; code that will rot | Friction or inconsistency off the main path | Unclear or untestable wording |
| Low | A small real fault with a failing case, nothing lost or misreported | A small visible fault a user will hit | A wrong but minor detail |
| Nit | Style, naming, a speculative concern | Polish, taste | Tone, wording preference |

## Heuristic scores (optional, for UI payloads)
Score Nielsen's ten heuristics 0–4 each. Mark any that don't apply `n/a` and renormalise (for example /32 when two are n/a). Record the total in the ledger with `critic_ledger.py score` so later runs show the trend.
