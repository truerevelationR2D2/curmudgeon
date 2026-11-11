# Changelog

Every release of Curmudgeon, newest first. The repository's history starts at 4.2.1; earlier versions are summarised from the project's own build and review records. Numbers are the ones measured at the time; the README's Benchmarks section has the current ones and how they were measured.

## 5.6.0 (unreleased): the sandbox switch (03 §5.57 items 17, 20 and 36)

Claude Code's own sandbox, where it runs (macOS, Linux and WSL2), becomes the reviewers' real boundary; the guard stays as the tripwire everywhere, and the only boundary on native Windows.
- **Each run checks it.** `begin` prints one probe command, `cd <project> && … critic_run.py probe`. The `cd` keeps it inside the sandbox, as every reviewer command is. It tries to read a token in `.critic/` and records `os-enforced` (refused) or `tripwire-only`. The counts carry a Boundary line.
- **The owner chooses** with `critic_ledger.py boundary auto|require|off`: auto checks and reports (the default), require holds every reviewer until the boundary is enforced, off skips the check. The choice is kept in the owner's record outside the project.
- **Turning it on.** `critic_run.py boundary-settings` prints the settings: `sandbox.enabled`, `allowUnsandboxedCommands: false`, `denyRead` on `./.critic` and Curmudgeon's own records, `allowRead` on the reviewers' copies, and `excludedCommands` for Curmudgeon's own scripts. Only on the user's yes, `critic_ledger.py boundary write` merges them into `.claude/settings.local.json`. They take effect in a new session.
- **Why the lead's scripts still work.** Anthropic's docs (settings reference and sandboxing, checked 10 Nov 2026) say an excluded command leaves the sandbox only when the call holds no `cd`. The lead's own script calls hold none and are excluded. Every reviewer command must start with `cd` into its copy, so none is.

Not built: wrapping reviewer commands with Anthropic's `sandbox-runtime` on native Windows. It is alpha there, and its install needs administrator rights and changes the machine, so it stays a decision (see the Progress Log).

## 5.5.0 (unreleased): the proctor, N5, the approved backlog and WSL2 as a required check (03 §5.57 items 34-36)

**The proctor (03 §5.57 item 35), the permanent check on reviewer blindness.** Curmudgeon writes a unique run mark into every brief's own part, every reviewer's review (on every line, stamped by the stop hook when the reviewer finishes), every file the scan writes and each of its rows, the tally, the counts, the dedup list and each verification packet. At each reviewer's stop, and again at every tally, a script reads that reviewer's own transcript on your machine (the output of every command it ran and every file it read) for any mark but its own brief's and review's. A reviewer that saw one is voided: its votes don't count and the counts name it, with what it saw. A finding only a voided review raised goes to a blind verifier and is kept only if the verifier reproduces it by running it, labelled, with no vote and never at a higher impact. A transcript the proctor can't read leaves the review counted and marks the run DEGRADED. There is no replacement reviewer (Ryan's ruling). Reviewers who need something outside their copy ask `critic_proctor.py ask read|list|git`, which never hands over `.critic/`, `~/.curmudgeon` or `~/.claude`, withholds any answer holding a run mark, and lists every request in `.critic/proctor/requests.jsonl`.

The first build also matched pieces of other reviews' wording. The first blind round showed that voided honest reviewers who saw the same test failure or rule another quoted, so only marks count now. That round also caught the stop hook recording the last review file a reply mentions instead of the one the reviewer wrote, live: a reviewer that named another review in its report got that review's stop record. It records the file the reviewer wrote now.

Reviewed blind twice before release (three reviewers and blind verification each time): the first round found 19 problems, the second 12 in the fixes (a stop record from an agent that never wrote the review could clear a void, the marks list could lose marks when stop hooks ran at once, `git blame --contents` could print any file, and more N5 gaps). All are fixed, each with a test that fails on the code before it. The second round's fixes were not reviewed a third time. Reviewers now also read no brief by path (their own is their prompt) and no session transcript under `~/.claude/projects` (the lead's holds other reviewers' reports).

**N5.** A reviewer's inline script that mentions `requests`, `socket` or `curl` only inside a string is data, not network code, when the code has no way to run text. Any Python comment, a builtins lookup, a module named in a string, a resolver by name (`pkgutil.resolve_name`, `pydoc.locate`), decoding or interpolation keeps the whole text judged as before. The case table is the test (3 allowed rows, 29 refused).

**The approved backlog (03 §5.57 item 34):**
- A run stopped and begun again on the same files carries over the outside answer it had loaded (P15).
- A stopped run (`critic_ledger.py abort`) is no longer active for the hooks.
- The plan mentions the tier you chose last time for the same files (R4), from a ledger written on this machine only.
- `begin` says when it removes private copies a dead stop hook left behind.
- The counts say which blindness check failed: no stop record, or a record saying the agent had no private copy.
- A new round moves the briefs aside with the reviews; `critic_ledger.py round` and `critic_run.py status` name the round's blind re-review step by step.
- `critic_outside.py brief` prints its own line telling the lead to hand the brief over.
- The WSL2 CI job is required, after 40 green runs in a row.

Budgets (`claude plugin details`, 10 November 2026, loaded from the repository): about 919 tokens added to every session, unchanged; the review skill about 8.9k when it runs (5.4.2: about 8.7k) and the reviewer agent about 1.9k (5.4.2: about 1.7k), for the proctor's steps.

## 5.4.2 (10 November 2026)

Everything merged after 5.3.0 (pull requests #34 to #42): the 5.3.1, 5.4.0 and 5.4.1 changes below, released together. 5.4.2 changes no code; it is the version number for this release. The Windows acceptance run in Claude's desktop app (03 §5.57 item 32) covered the 5.4.1 build from #41, not this exact build: it passed with no DEGRADED banner and every reviewer's blindness recorded. Two things it did not cover in the app: #42, merged after it, which changed which single reply the stop hook checks when there is no hand-back (covered by its own tests), and the verifier path, because that run needed no verifier (a verdict saved from a hand-back is covered by the test with the recorded shapes). An outside check was tried twice and not completed: both times the other AI read none of the files, so it is not counted as a review. Budgets (`claude plugin details`, 10 November 2026, loaded from the repository): about 919 tokens added to every session, up from about 864 in 5.3.0, mostly the new `/curmudgeon:check-updates` listing (about 50); the review skill about 8.7k when it runs, up from about 8.5k. The sections below are each change as it landed, newest first.

## 5.4.1 (released in 5.4.2): the stop hook reads the hand-back first (the 10 Nov acceptance run)

The Windows acceptance run of 5.4.0 (03 §5.57 item 32) still came back DEGRADED: no blindness records, and a verifier's verdict was lost. The hooks did run. On Claude's desktop app an agent ends with a `SubagentHandback` tool call, its report in `input.message`, and the host's `last_assistant_message` was not that report. The 5.4.0 hook read the transcript only when that field was missing, so it checked the wrong text, blocked, and the host, which doesn't resume an agent that has handed back, ignored the block. Now:
- The hook reads the transcript first and checks the last hand-back report. Without one, it checks a single final reply: `last_assistant_message`, else the transcript's last assistant text. It never joins the two, so an earlier verdict can't stand in for the final reply (Qodo on #41).
- When a block can't take effect, because the agent has already handed back, the private copy is still removed.

The new test uses the shapes recorded on Ryan's machine: the `SubagentHandback` call and a `last_assistant_message` that isn't the report. It fails on 5.4.0 with the run's own error.

## 5.4.0 (released in 5.4.2): fixes from the second Windows run, four backlog items and an update check (03 §5.57 item 31)

**The stop hook never finished in Claude's app (the 9 Nov rerun's R1, High).** The app sends no `last_assistant_message` on SubagentStop, and reviewers hand their report back through a tool call, so `check_contract.py` never saw the reply: it blocked every reviewer and verifier, the app went on without honouring the block or calling again, and the hook never wrote the blindness record, never saved a verifier's verdicts and never removed the private copy. So every run in the app was DEGRADED, and a lost verdict could change the verdict word (CLEAN became CONCERNS in one run). The hook now reads the reply from the agent's transcript (`agent_transcript_path`, a hand-back tool call included) when the message is missing, and records the blindness record and verdicts before it decides whether to block. The tests had passed because they fed the hook a `last_assistant_message` the app never sends; the new test uses the keys the app really sent.

From the 9 Nov run of 5.3.0 on Windows (the run report's N items):
- **N1 and N4, reviewer blindness depended on the shell's folder (High).** The lead had `cd`'d into `.critic/briefs`, and the hooks and scripts took that folder as the project: reviewers' private copies held the three briefs and not the code, and the background scan couldn't find its file list. Any folder inside `.critic/` now maps back to the project, in the hooks and in every script that finds the project from the current folder (the scanner is given `--root`); the printed scan command names the project and its file list in full, and the scanner reads a relative `--only` against `--root`.
- **N2.** Outside git, briefs said "From the last commit message:" with nothing after it. Now no intent is stated, as in 4.2.1.
- **N3.** A run with no kept finding printed the SHA-256 of empty input as the cited files' hash. Now it says no kept finding cites a file.
- **N6.** The change map kept the mapped tier after the owner chose another. It now shows both.
- **N8.** `begin` starts the run, so a plan changed afterwards threw away the work. `critic_run.py plan` proposes the plan and starts nothing; with the user present, the skill runs it first.
- N7 (a 4.2.1 ledger set aside after the upgrade) needs no change: the message names `critic_ledger.py adopt`, and trusting old ledgers automatically would undo the check that stops a planted ledger. N5 (the offline guard refusing a script that only mentions network words in its text) is in the backlog: loosening a guard needs its own design and blind round.

Backlog items:
- **P8.** Scripts `critic_run.py` starts are logged with their exit codes, and `critic_ledger.py log "<command>" <exit>` records a command the lead runs itself (a sandbox run, a re-check).
- **P10.** `critic_ledger.py abort ["why"]` records a run the owner stopped; `ledger.md` lists it.
- **P11.** `critic_ledger.py decision --amend N "text"` and `--retract N "why"` correct a decision; its earlier words stay in the ledger, and a retracted one no longer reaches reviewers.
- **P15.** A run stopped and begun again on the same change is the same review, so the outside-reviewer question isn't asked again.
- **`/curmudgeon:check-updates`** (new). Says whether a newer Curmudgeon is on GitHub and how to update. One request to GitHub for the public version file; nothing about the user or the project is sent, nothing is downloaded or installed, and only the user can start it. Listed in PRIVACY.md.

Three blind review rounds on these changes found more problems, all fixed here with tests: the wider folder rule took a project kept under a folder named `.critic` (`~/.critic/projects/app`) to be its parent (now one shared helper, `projroot.py`. After three review rounds on rules that guessed from what a folder holds, each with new holes such as letter case, empty or nested `.critic` folders, drive roots and generic names like `history`, the rule guesses nothing: the folder above the first `.critic` in the path is the project, in any letter case. The hooks, which build and guard reviewers' copies, ignore a `.critic` above the folder the session started in (`CLAUDE_PROJECT_DIR`, which Claude Code gives hooks and which stays put when the session changes folder), so a project kept under a folder named `.critic` stays itself. Scripts don't get that value, so for such a project the README says to set `CRITIC_ROOT`); `plan` changed a live run's files and skipped the linked-folder check (it now refuses a linked `.critic` and puts back every file it wrote); the update check took its address from an environment variable, followed redirects and printed whatever text came back (now the built-in address only, no redirects, and only a plain version number is ever printed); `decision --amend/--retract` relied on an `assert` for its bounds and accepted empty text (now a real check, the author can't be the source, and `ledger.md` shows every earlier wording); a retracted decision could still reach a reviewer through a sub-project's ledger in its copy; the change map said "the owner's choice" in audit mode; and `abort` accepted a finished run while `next` carried on after an abort; and a ledger whose decisions aren't records is refused as the wrong shape instead of crashing.

The fresh self-review of 5.4.0 (headless, three reviewers, $7.32; scripted checks skipped, so DEGRADED) counted 6 Medium and 7 Low; fixed here: `plan` proposed the wrong tier for an audit; `critic_run.py early` and `status` didn't refuse a reviewer's copy, so a reviewer could read the scan's FAIL rows; `ledger.md` now numbers decisions as `--amend`/`--retract` take them; exit codes come first in a run-log line so a long command can't cut them off; the change map also notes a tier the job plan chose; README and PRIVACY.md describe the update check; two tests that couldn't fail now can. Left in the backlog: a restarted run's outside answer is left out of the tally rather than carried over (P15 is wording only), and an aborted run still counts as active for the guard hooks until it expires.

Qodo on #37 and #38: a session started inside a folder named `.critic` takes that folder as the project; the README says to start Claude in the project folder (a warning tried here was removed, since a hook can't tell the two path shapes apart and would have warned wrongly). A session in `P/.critic/briefs` and a project at `/tmp/.critic/briefs/app` have the same shape of path, so no path rule can serve both; the choice is recorded in the Project's settled-design register so it doesn't flip again. A verifier's verdict that fails the contract is never saved, on a second stop too, so the merge counts it as missing and marks the run DEGRADED; a relative `--only` list is always read from the scanned project, never from the shell's folder; `critic_ledger.py log` writes one run-log line and leaves the ledger alone; and the skill now says a new session asks the outside-reviewer question again, since nothing records the answer.

The sandbox-switch card was rechecked against Anthropic's docs (Progress Log): Claude Code's sandbox doesn't run on native Windows, and `sandbox-runtime`'s Windows support is alpha and needs a one-time elevated install.

## 5.3.1 (released in 5.4.2): fixes from the first Windows run (03 §5.57 item 29)

Ryan's Windows run on 5 November 2026 found 15 problems, on the 4.2.1 copy then installed. Four were still in 5.3.0. Each has a test that fails on the code before it:
- **P1, hooks on Windows:** every hook ran as the shell string `python3 "…"`. On Windows without Git Bash, or where `python3` is the Microsoft Store placeholder, the file-write guard couldn't start, and Claude Code treated that as a block, so every file write in every project was refused. Every hook now starts through `hooks/run.sh`. It tries `python3`, then `python`, then `py -3`, and runs the hook with the first one that really starts Python 3.9 or later. It keeps that choice in the plugin's own data folder, as one of those three names and nothing else, and never writes it through a link. The kept choice is checked again before every hook, so one that stopped working, or now starts an older Python, is replaced before the hook runs; the hook itself runs once, never again with another interpreter (Qodo on #34: a check only after the run let a Python 3.8 failure pass as the hook's answer, and a hook that ran and was killed could run twice). The launcher makes the data folder if it isn't there yet, since Claude Code makes it only when a hook names it (Qodo on #34; Anthropic's plugins reference: "created on first reference"). A missing hook script, or no working Python, is reported and never exits 2, Claude Code's "block" (second blind round). The PreToolUse hooks are marked `onFailure: "continue"`, as Anthropic's hooks reference advises, so a guard that can't start never blocks the user's own work (03 §5.57 item 29 replaces item 22's "the hooks keep `python3`"). The review skill, the detector and the sandbox guide say to use `py -3` on Windows when `python3` isn't there, and the commands the scripts print (the scan, the security-feed steps, the briefs' syntax-tree tool) now name the Python that ran them instead of a bare `python3` (Qodo on #34). On Windows a path with a space or an accent is printed in its short form, so the line runs as printed in PowerShell too, and the launcher started with no hook exits 1 rather than dash's 2 (third blind round). Where Windows has no short name for a path (short names switched off on that drive), the path is printed in double quotes, which Git Bash and PowerShell read alike, an apostrophe included; the test no longer breaks in a checkout whose path has a space (Qodo on #35). A path with `!` gets single quotes, since Bash expands `!` inside double quotes, and printing a command never starts a program or swaps in another Python: a `py -3` fallback tried here was removed, because a bare `py` is found in the project's own folder first on Windows (Qodo on #36). Left over: on a drive with short names off, a Python path that needs quotes stays quoted, and PowerShell needs `&` in front of it.
  - A first version listed each hook three times (`py -3`, `python` and `python3`) and let one copy work. The blind round on it showed that a leftover `py` launcher or an MSYS2 Python could make no copy run, or two, and that starting a bare interpreter name with no shell might pick up a program of that name in the project folder. The launcher avoids all three.
- **P2, unparseable Python:** the scan reported "pass" on a file that doesn't parse. It now reports a WARN (`python-parse`) with the error and line. It is never a FAIL, because valid Python 2 with tabs, templates and newer syntax fail to parse too (blind round).
- **P5, apply with nothing to apply:** `critic_merge.py apply` with no verdict files now records the run instead of refusing it. A `verdicts/*.json` pattern the shell left as written (PowerShell and cmd never expand one) is expanded, so verdicts that exist are applied. A pattern in `.critic/verdicts/` that matches nothing means none; one anywhere else (a wrong folder, a typo) is refused (blind rounds).
- **P7, help with side effects:** `critic_map.py --help` showed nothing helpful and ran git first. It now prints its help and does nothing else.
- **Already fixed in 5.3.0:** P3 and P4 (UTF-8 output on Windows), P6 (the "confidence lowered" note), P12 (the approve skill is gone) and P14 (reviewers work in a private copy without `.critic/`).
- **Backlog [PROPOSED]:** P8 (exit codes in the run log), P10 (abort, and per-round archives), P11 (amending a recorded decision) and P15 (whether the outside-reviewer answer carries over to a restarted run).

## 5.3.0 (5 November 2026)

Everything merged after 5.2.6 (pull requests #17 to #28 and #30 to #32; #15, #16 and #29 were closed and their changes carried into later ones): native Windows and macOS support with Windows and macOS failures failing CI, private folders locked and read back on every platform, the reviewers' guard on Windows paths, audit batches 3 to 6, and Qodo's rounds on #15 to #31. Budgets (`claude plugin details`, 5 November 2026, each version installed from its own tag or branch): about 864 tokens added to every session, unchanged from 5.2.6; the review skill about 8.5k when it runs, down from about 8.8k in 5.2.6 because the optional modules moved out of it (batch 6). The sections below are each change as it landed, newest first.

### native Windows and macOS (03 §5.57 item 20)

**Qodo on #31:** on macOS, a failed `chmod -N` or `ls -le`, or an empty listing, now refuses the lock instead of passing it. On Windows, an entry whose saved access list has no `D:` part or says `NO_ACCESS_CONTROL` (a null DACL, which lets every account in) refuses it, and every entry inside must keep a grant for the user or SYSTEM.

**Private folders, redesigned after Qodo's review of #30 and a blind review round** (03 §5.57 item 26). Earlier rounds fixed one finding at a time and tested against a stand-in for `icacls`. This one changes the lock as a whole. Three blind reviewers then read the redesign, and every point that at least two of them raised is fixed here. The lock reports success only after reading the result back:
- **Who "you" are:** on Windows this comes from the process's own token, never from `USERNAME`/`USERDOMAIN`, which a project's code could set to `Users`.
- **Links inside:** a folder holding a link, junction or hard link is refused before anything runs, so neither a reset nor Windows' own inheritance can reach a file elsewhere. A folder that can't be listed is refused with its reason.
- **Order:** the folder is granted to you and made yours, then every other account's grant and every deny (yours and SYSTEM's included) are removed and the folder is read back. Only then do the contents inherit from it. They are reset without `/C`, so `icacls` fails on the first entry it can't change. They are made yours, and every entry is read back.
- **POSIX:** the mode is read back with `os.stat`, so a file system that ignores `chmod` (WSL's `/mnt/c` without `metadata`, FAT, many network shares) refuses the lock. On macOS every extended access entry is removed with `chmod -N`, and `ls -le` must show none.
- **Callers:** the browser refuses a `.critic` that is a link. A junction at `.critic` or `.critic/scratch` is treated as a link. The browser's private folder gets its `.gitignore` before the lock. A reviewer's old copy is deleted before its folder is locked.
- **CI:** the Windows-only checks run even when a script test fails.
- **Tests on real machines:** on Windows, a junction to an outside folder (refused, outside untouched), existing denies and grants, a file with its own Everyone grant, and owners. On macOS, an inherited `staff` access entry.
- **Not changed** (each raised by only one reviewer, or out of scope): a link swapped in while the lock runs, by another program with write access to the folder.

**Windows and macOS failures fail CI** (03 §5.57 item 24): every platform passed on b52d73f. Of 423 tests, Windows passed 410 and skipped 13 (each with its reason), macOS and WSL2 each passed 412 and skipped 11, and Linux passed on Python 3.9–3.14. The Windows script tests and the macOS job no longer may fail without failing the run; blocking a merge on them also needs a required-check rule in the repository's settings, and a test keeps it so. WSL2 joins after five green runs in a row. The Windows test harness rewrote `C:\` paths into `C:/` by turning every backslash into a slash, code's doubled escapes (`\\u002e`) too, so one guard test checked a plain path and passed only by chance on Windows (it failed in 3 of 6 Windows runs, and 2 of 12 repeats in one run); it now rewrites single separators only, and a test keeps it so. The README's Windows limit is rewritten: the tests pass, a full Claude Code session on native Windows hasn't yet been checked by hand, and the hooks need `python3` itself on PATH.

**Qodo on #27** (eight findings, each with a test that fails on the code before it, "Qodo on #27"):
- **Reviewers' guard (High):** `r = '\x2f'; os.listdir(r)` got past the guard again after the #25 change. The rule is now the one Qodo proposed. Code that lists folders and also builds characters as it runs is refused, unless every built character is clearly harmless (`chr` or `fromCharCode` of codes that are neither `/` nor `\`). That covers a name, a tuple, a loop, a return value and a keyword, and an unrelated `chr(65)` still runs.
- A path written out from the agent's own folder that stays inside it (`<own>/notes/../notes/out.txt`) is no longer refused.
- Every Curmudgeon agent's PowerShell and Monitor commands are refused, the detector's included, so the owner-consent tripwire can't be skipped through PowerShell.
- The Windows folder dialog writes its path as UTF-8.
- The stop gate decodes git's file list with `surrogateescape`, so a name that isn't UTF-8 keeps its bytes.
- The CI probe uses PowerShell 5.1 syntax, not `||`.
- The link test reports SKIP where links can't be made, such as Windows without Developer Mode.

**Qodo on #27, second review** (three findings, each with a test that fails on the code before it, "Qodo on #27 (2)"):
- `root = '/'  # a comment` is followed like `root = '/'`.
- A path written out from the agent's own folder that holds escapes (`\x2e\x2e`) is refused. When the code runs, those escapes become `..`.
- The stop gate hashes a file name that isn't UTF-8 by its bytes. Before, the hash raised and the gate let the stop through.

**Qodo on #29** (three findings on the Windows lock, each with a test that fails on the code before it, "Qodo on #29"):
- A link or junction is refused before anything runs, and `icacls` is told not to follow links (`/L`), so a junction planted at `.critic/restore` can't send the change to files elsewhere.
- The steps run in an order where none leaves the folder looser than it was:
  1. inheritance off, with only the user and SYSTEM granted;
  2. the folder's contents reset to inherit that;
  3. any other principal's explicit grant on the folder removed.

  Before this, the folder was reset first, so a failed grant left existing keys under broader permissions.
- The System32 folder comes from Windows (`GetSystemDirectoryW`), not from `SystemRoot`, which a project's code could set.
- The lock now identifies SYSTEM and the user by their security ids (SYSTEM is `S-1-5-18`), not by a name ending in `SYSTEM`. A foreign domain's account named `SYSTEM` used to keep its grant, and a translated Windows (`AUTORITE NT\Système`) used to lose the real SYSTEM's. An account whose id can't be resolved is removed (Qodo on #29, second review).
- The lock reads the folder's grants with `icacls /save`, which writes them in SDDL: every account is a security id or a fixed alias (`SY` is SYSTEM, `WD` is Everyone), and no names appear. It then removes every account that isn't SYSTEM or the user, by id. Before, it parsed the translated text listing, which broke two ways. On a German Windows, `NT-AUTORITÄT\SYSTEM` in the console's code page couldn't be looked up, and the lock failed. A project under `Ásgeir`, which that code page prints as `?`, got no reviewer copy (the Windows CI showed this). An alias the lock doesn't know refuses the lock rather than guessing. (Qodo on #29, third review.)
- Every entry in the saved access list counts. That includes object and conditional entries (`XA`, `ZA`), whose expressions sit in nested parentheses. An entry the lock can't read, or whose type it doesn't know, refuses the lock. Before, the parser skipped those entries silently and could report a folder private while another account still had a conditional grant. A temp file that can't be made (a full disk) now fails the lock instead of raising. (Qodo on #29, fourth review.)
- The access list is scanned with quotes and depth tracked, so a quoted `S:` or `)` inside a condition (`@User.Title == "S:contractor"`) doesn't end the list or the entry. A failed lock records why (`privacy.WHY`), and the reviewer copy, the browser driver and restore saves include the reason in their refusal. (Qodo on #29, fifth review.)
- An SDDL alias whose id depends on the machine or domain is expanded by Windows (`ConvertStringSidToSidW`). One example is `LA`, the local administrator, which is the Windows CI's own user. The fixed table had no entry for it, so the lock refused every private folder on that runner, and no reviewer copy was made. The new failure reason showed it. An alias Windows can't expand still refuses.
- An own-folder path holding an escape is judged as written. The step that resolves a short name to its long form skips it, because on Windows it would reshape `\x2e` into a path separator.

**Windows CI round** (402 of 407 on 3f936a7, up from 393):
- The guard reads `/proc` paths after a drive letter, since Git Bash serves `/proc`, and reads a bare `//` as the root.
- Three tests no longer assume POSIX:
  - Windows resolves `node_modules/..` by text;
  - the runner's `bash` is WSL's launcher;
  - the escape test writes its own path in `C:/` form.

**Qodo on #28** (five findings, each with a test that fails on the code before it, "Qodo on #28"):
- `icacls.exe` runs from Windows' System32 folder, so a project's own `icacls.exe` can never run instead.
- The lock resets the folder's existing permissions first, including its contents. It then removes inheritance and grants only the current user and SYSTEM, so an explicit broad grant already on the folder doesn't survive.
- `make_private()` reports a failed lock, a failed `chmod` included. What happens then depends on the caller:
  - the reviewer copy isn't made;
  - the browser driver refuses to write its signing key;
  - a restore copy, which can hold keys, isn't saved;
  - the scratch-folder message stops calling the folder private.
- The browser driver's key folder is locked when it already exists too, once per run.
- Only an escape that makes `.`, `/` or `\` counts as one in an own-folder path (`\x2e`, `\u002e`, `\056`, `\N{...}`), so a Windows separator or `notes\2024` doesn't.

**Windows guard paths:** the folder-above-the-project check now reads Windows paths (`C:\Users\x`, `C:/Users/x`, `\\server\share`) as well as `/home/x`, and compares the long form Windows resolves a short name to (`RUNNER~1` → `runneradmin`). An absolute path from the agent's own folder that is written in another form is known as its own, unless it holds `..`, which resolving would hide. Two tests stopped replacing the real Windows `msvcrt` and checking POSIX modes on Windows.

**Private folders on Windows** (03 §5.57 item 23): restore copies, reviewers' scratch folders and the browser driver's key folder are made through one helper, `privacy.make_private()`. It sets 0700, and on native Windows, which ignores POSIX modes, it also removes inherited permissions and grants only the current user (`icacls`). A test checks the `icacls` call and refuses any private folder made without the helper.

- **Text encoding.** On native Windows, Python reads and writes text in the ANSI code page (cp1252) unless told otherwise. That includes a hook's output to Claude Code, which goes through a pipe. A report line with an arrow or an accented name crashed there, and the Windows CI job stopped after 305 of 396 tests (run 41749011233, still shown as passed because the job may fail). Every text read, write and subprocess call in the plugin, the eval kit and the tests now names `encoding="utf-8"`: 959 calls, added by a rewriter that edits the parsed code and touches nothing else. Every entry script imports `utf8io.py`, which switches stdout and stderr to UTF-8. One file sits in `hooks/`, `skills/review/scripts/` and `eval/`, the same in each. Tests: no text I/O call may omit its encoding, and a script printing non-ASCII text to a cp1252 pipe doesn't crash. On Linux and macOS, which already default to UTF-8, nothing changes.
- **Paths with `/`.** A project-relative path was written with `str()`, which gives `src\a.js` on Windows. 36 places now use `.as_posix()`, so reports, ledgers and finding ids match across platforms. A test refuses `str(... .relative_to(...))`.
- **Stopping a hung command.** Windows has no `os.killpg`, `signal.SIGKILL` or `signal.SIGHUP`, and the mutation and project-check runners raised on them. `kill_tree()` uses the process group where there is one and `taskkill /T /F` on Windows. The mutation run registers only the signals the platform has.
- **Line endings.** A `.gitattributes` checks text out with LF on every platform, so a Windows checkout has the bytes the hash and fixture tests compare.
- **The reviewers' guard through a link.** On macOS, `/var` is `/private/var`, and an honest heredoc writing to the agent's own notes through the unresolved path was refused, because the guard removed only the resolved spelling of the agent's folder (the macOS CI job's one failure). Every spelling is now removed. Reads of the project's records stay refused either way.
- **PowerShell and Monitor.** On Windows without Git Bash, Claude Code turns the PowerShell tool on by itself, and its docs say hooks that inspect shell commands should match `Bash|PowerShell`. The reviewers' tool lists don't include PowerShell. As a second line of defence, the guard now also watches PowerShell and Monitor and refuses them for reviewers and verifiers, since it reads bash only.
- **Blind review of these fixes** (two reviewers; their findings are fixed with failing-first tests):
  - The guard now treats `..` in code that names the agent's own folder, in any spelling, as a climb, and removes that folder's path only up to a boundary. Stripping the link spelling had let code start there and climb to the review records. A version of the climb from the resolved spelling was older than this change. The agent `r1` no longer covers `scratch/r10`.
  - `utf8io` reconfigures stdin too. With Python's default at cp1252, a hook reading Claude Code's input for a project under `Ásgeir` failed to decode and let the call through.
  - Output from outside programs (project checks, git, PowerShell's folder dialog) is decoded as UTF-8 with `errors="replace"`, so a tool writing in its own code page can't stop the run. File reads stay strict, because the scanners rely on that.
  - The WSL2 job copies the checkout from `$PWD` and runs with `pipefail`.
- **First CI results** (#27, before Qodo's fixes): macOS passed 404 of 404 and WSL2 passed 404 of 404, 11 skipped each. Native Windows passed 371 of 404, up from a crash at test 305. Python probe: `python3`, `python` and `py -3` all ran in Git Bash, PowerShell 5.1 and PowerShell 7, both on the runner and on the owner's machine (Python 3.13), so the hooks keep `python3` (03 §5.57 item 22).
- **Windows follow-ups:**
  - The stop gate's message and the copy's record (links, dependency folders) wrote `src\b.py`, so they now use `/`.
  - The test runner gives the guard commands in the form Git Bash needs (`C:/Users/...`). An unquoted `C:\Users\...` is broken by the shell before any program sees it.
  - The 0700 check on restore copies runs only where POSIX modes exist. On native Windows, the folder's ACL decides who can read them.
- **WSL2 in CI.** A job runs the script tests, golden and replays in Ubuntu 24.04 on WSL2 (`Vampire/setup-wsl` v7.2.0, pinned by commit). It isn't a required check until it has passed five runs in a row.

### Qodo on #25

Four findings. Each has a test that fails on the code before it (`plugin/tests/cases_8.py`, "Qodo on #22" tests (1) and (6)).
- **Reviewers' guard:** a listing is refused only when its own starting argument is built from character codes or escapes, or names a value that holds the root at that point. An unrelated `chr(65)` elsewhere in the code no longer refuses a listing of the copy. Names are followed in order, statement by statement, so `start = root; start = 'src'; os.walk(start)` runs. `r = chr(47); os.walk(r)` is refused.
- **Test lens:** a nested `TestCase`'s `test_*`, `setUp` and `__call__` count only when the test hands it to a runner (`loadTestsFromTestCase`, `TestSuite`, `TextTestRunner`, `.run()` and the like). A `TestCase` that is built but never run checks nothing. A nested class's `__init__` counts when the test calls the class.

### Qodo on #24

Four findings, plus the run-time root from #23 under the owner's ruling that a bypass found in the code is patched (03 §5.57 item 18). Each comes with a test that fails on the code before it (`plugin/tests/cases_8.py`, "Qodo on #22" tests (1) and (6)).
- **Reviewers' guard:** inline code that lists folders from a path built out of character codes or escapes (`chr(47)`, `String.fromCharCode(47)`, `'\x2f'`, base64, hex) is refused. The guard checks this on the command's raw text, because its words lose their backslashes before they are split. A name that holds the root through an alias (`root = '/'; start = root; os.walk(start)`) is followed.
- **Test lens:** a nested class's methods count as checks only when its base class names a framework that calls them: `do_GET` for a request handler, `test_a` for a `TestCase` handed to a runner, `get` for a view, `run` for a thread. Any other class's methods count only when the test names them, so an unused `get()` is no check. A method under `if False:` doesn't exist, so it doesn't count.

### Qodo on #23

Five of six findings fixed, each with a test that fails on the code before it (`plugin/tests/cases_8.py`, "Qodo on #22" tests (1), (2), (5) and (6)).
- **Reviewers' guard:** `ack -f DIR` lists files and takes no pattern. The #22 fixes had read DIR as the pattern and left it unjudged; it is judged again.
- **Reviewers' guard:** `root = '/'` set aside beside `os.walk('src')` is no longer refused. A name set to the root counts only when a listing call starts from it.
- **Test lens:** a nested subclass's methods count only when a framework calls them (`do_GET`, `setUp`, `handle`, `__call__` and the like) or the test names them. An unused helper with an assert is not a check, and a handler defined under a class-level `if` or `try` is found.
- **Live request cap:** in a review run, a scan whose shared ledger can't be read or locked sends nothing, as the browser driver already did.

Finding 1 (`os.walk(chr(47))`) was first left as a known limit (03 §5.57 item 17), then patched under item 18; see Qodo on #24.

### Qodo on #22

Seven findings, each with a test that fails on the code before it (`plugin/tests/cases_8.py`, "Qodo on #22").
- **Reviewers' Bash guard, inline code (High).** Code run by an interpreter (`python3 -c`, a heredoc fed to python, `node -e`) could walk the disk from `/` and build the name `.critic` as it ran (`'.cri' + 'tic'`), so neither the name nor a path above the copy showed. The lone `/` in a heredoc is blanked for the shell's words (audit V22), and the old check needed the name written out. Now code that lists or searches folders from the root, the home folder or an absolute wildcard is refused, and so is code that writes out a folder at or above the project. Splitting or joining on `/`, and walking the copy's own folders, still run. The guard is still a tripwire, not a sandbox: a script written to `notes/` and then run is not read (listed below under batch 5).
- **Reviewers' Bash guard, search options (Medium).** `grep FILE -e x` and `rg PATH --files` were read as a pattern and then a path, so FILE and PATH went unjudged. GNU grep and ripgrep take options after the operands; the guard now reads the whole command before deciding which operand is the pattern.
- **Live request cap (High).** The scan checked the run's count and recorded a request in two steps, and a browser session read the count once and recorded its requests after its replay. Parallel sessions could each pass the check on the same count. Each request to a live site is now reserved, by the scan and by every session, under one lock before it is sent (`browse.reserve`), and nothing is recorded a second time afterwards.
- **Benchmark scorer (Medium).** Fix advice in one field of a structured finding (`Fix:` in the evidence) cut off the fields after it, so a planted defect named only in `failing_case` lost its credit. Each field is now stripped on its own.
- **Operations lens (Medium).** `app.JS` was admitted to the scan but skipped by the operations checks, which compared the suffix case-sensitively.
- **Test lens (Low).** An assert inside a method of a nested class the test uses (a request handler's `do_GET`, a mock's method) now counts as a check; a class defined and never used still doesn't.
- **Background stop check (Low).** A check that can never run for a file (an unreadable security database, a part made of binary files) kept that file in the retry slot at every stop. A file version that has failed three times is now recorded as given up; a new edit starts the count again.

Two blind reviewers checked these fixes, one on the guard and one on the rest, each in a private copy with only the diff. Their findings are fixed, each with a failing-first test:
- The first version of the root rule refused honest probes that print `'//'`, use `sep='/'`, build a route with `'/' + name` or `path.join('/', ...)`, or count `'/*'` in files. It missed `os.getenv('HOME')`, `abspath('/')`, `.anchor` and `parents[-1]`. Now the root counts only as the first argument of a listing call (or of a `path.join` there), or as a name set to it on its own line.
- `ag -f` (follow links) and `ack -f` take no value; `ack --match PATTERN` names the pattern.
- A file given up on went back into the retry slot at its next failure; it now stays given up until it changes.
- Only the suffix is folded for the operations lens. Folding the whole path had left `.GitHub/Workflows/*.yaml` unchecked by either scanner.
- Only a nested subclass's methods count as reachable (a framework calls them). A plain stub's `raise NotImplementedError` is not a check.
- A live-request ledger that can't be read or locked now stops the request from being sent.

Not re-reviewed: these follow-up fixes. A `'/*'` word in a heredoc body is still judged as a path, as before; use `-c` for a probe that counts it.

### audit batch 6 (optional modules)

Ruled in 03 §5.57.5 and confirmed on 3 Nov 2026 as in-plugin modules, not a companion plugin. Browser checks, live sites, mutation testing and the local security database each have their own instructions file under `plugin/skills/review/references/modules/`, which the review skill reads only on a run that uses that feature. The text was moved, with a few sentences added from the code (which controls count as destructive, the request cap per run, the mutation backups); the consent steps keep their wording, and the scripts still refuse a live host, a real send or an unapproved test command without the owner's record. The background stop check was already the gate skill's. The README has an "Optional modules" table. The review skill's cost when it runs fell from about 8.8k to about 8.5k tokens (`claude plugin details`); the always-on cost is unchanged at about 864. A smoke eval of the skill change is still to run [PROPOSED], since moving instructions can change what the lead does.

### audit batch 5 (Mediums, Lows and Nits)

**After the blind review (3 reviewers, round 1).** They found that several of the guard's new exemptions let a reviewer read `.critic/` again, and each of their cases is now a test. Nothing at or after a redirect is text (`tr a a < FILE`). Separators are per command (`paste -s` and `column -t` are flags). `grep -e.`, `-f`, `--file=`, `rg --files` and `ag -g` leave every operand judged. A here-string, a `<<` inside quotes, a heredoc with no terminator, and a body fed to a shell or `xargs` are judged word for word; only a body read by a script interpreter or written to a file has its lone slashes blanked. Variables are judged with every value the command gave them (prefix assignments, `for` loops, `${X%%...}`, `typeset`, `+=`). `/proc` paths are normalised, so `/proc/self/../1` and `//proc/1` are refused and `/proc/cpuinfo` is allowed. A Glob with 64 or more alternatives, or over 5,000 matches, is refused whenever its pattern can reach `.critic/`. Inline code naming `.critic` is refused only when it can leave the copy.
**Round 2 (3 reviewers).** They found gaps the round-1 fixes left or opened, and each executed case is now a test. `/proc/*/cmdline`, `/proc/[0-9]*` and climbs to `/proc` are refused after expansion. A variable is judged with its last values first. `${Y:-path}`, `${X:+path}`, `${X/a/b}`, arrays, `set --`, `read`, `printf -v`, `declare -x`, `Y=$X`, Bash braces and `$'..'` are expanded before judging. A heredoc piped on to another command is judged word for word. `cat <<EOF > f`, `tee f <<EOF` and probes opened with `timeout` or `VAR=` keep their division. `grep -T` and `ag -t` take no value, and `ack -g` keeps its operands judged. Inline code naming `.critic` that climbs by API (`parents`, `pardir`, an absolute glob) is refused. A Glob that hides a climb or an absolute path inside its braces is refused past 64 alternatives. A prompt holding several briefs is refused, and briefs are claimed under a lock, so parallel starts can't share one. A nested ledger is copied with its rulings only. A grouped tally must count exactly the reviews of the tally that listed the candidates. A base64 secret with inner slashes is found. `blogger` is no logger. The docs now say that `--online` and `--project-checks` are outside the module table and that local sends need consent only.
**Round 3 (3 reviewers, the last; these fixes are not re-reviewed).** Each executed case is a test. The guard now refuses by text what it can't evaluate exactly, instead of chasing each spelling: a path word built with `${X%..}`, `${X#..}`, `${X/..}`, `${X:n}`, `${!X}`, `$@`, `$*`, a `{a..b}` sequence or `$"..."`, and any `/proc/<pid>`, `/proc/$PPID`, `/proc/self/cwd`, `root` or `fd` path. A variable with more values than it follows is refused rather than trimmed. An unset variable is judged as empty too, and `"$X"tic` ends the name at the quote. A `#` no longer hides the rest of a command. Process substitution starts a command. `bash -c` sees the outer command's variables. A crash in the guard now refuses the command instead of allowing it. Inline code that climbs two levels (`../..`, `dirname(dirname(..))`, `.parent.parent`) is refused, since the copy sits inside `.critic/`; a heredoc's code is checked as written. A nested `.critic/` in the real project can't be read, and the copy's git shows no phantom ledger. `grep --color` keeps its file judged. Python probes ending in `2>&1` or `| tail` work again, as do probes naming a `.critic` folder inside the copy. The secret scanner treats `/opt/MyCompany/vault` as a path and a value whose segments mix capitals, small letters and digits as a key. `dblogger` is a logger again.
Still open, as a tripwire's known limits (PRIVACY.md: the real boundary is Claude Code's permission mode): a script written to the notes folder and then run is not read; `eval`, command substitution and code that builds a path from pieces (`'.'*2`, `os.sep.join`, `String.fromCharCode`) aren't followed; and a confirmed cross-file group lists the other reviewer's place beside the verified one.
Also from the review: a nested `.critic/` keeps only an allow-list of the owner's settings; each reviewer must get its own brief; a cross-file dedup group is verified at any impact (two reviewers' Lows were dropped); a review that wasn't in the tally that listed the dedup candidates can't join the grouped one; database URLs in XML, templates, IPv6 hosts and flow maps are found again; a base64 secret starting with `/` is found again; `applogger.info(...)` counts as a log call again; `press Shift+KeyA` types nothing into a password field; standalone live scans don't share one cap; and behaviour1's "no page errors" check, which an inline comment had swallowed, is back.

Batch 5 of the ultimate audit of 30 Oct 2026 (03 §5.57). Each fix has a test that fails on the code before it (`plugin/tests/cases_8.py`). F-0dcc1490, V44 and Q13 were already fixed in batch 1.
- **The reviewers' Bash guard (V22, Q16, Q01, P3, V14).** It no longer reads a URL, a search pattern, `tr`'s sets, an `awk -F` or `cut -d` separator, or a lone `/` in a heredoc body as a path, so `grep -rn "http://"`, `grep "../"` and a probe that divides two numbers work again. The same paths written as operands are still refused. It expands a command's own variables (`X=.cri; cat ${X}tic/...`), refuses inline code that names `.critic` or `~/.curmudgeon`, refuses `ps`, `pgrep`, `lsof` and `/proc` reads (other agents' command lines), and recognises `require("https")` and its relatives as network code. It is still a tripwire, not a sandbox.
- **Globs (V27, Q17).** A Glob's `{a,b}` alternatives are expanded and judged. One with more than 5,000 matches from a folder that holds `.critic/` is refused, never cut off silently.
- **Hooks (V26, Q11).** The stuck watcher's refusal now reaches a repeated Write or Edit. A notebook edit gets the while-you-work scan.
- **Reviewers' copies (V24, V23).** A tracked file the copy left out (over 5 MB) no longer shows as deleted in the copy's git, while the owner's own deletions still do. An earlier run's output in a nested `.critic/` (reviews, findings, history) is neither copied nor put in the copy's git; a nested ledger or recorded copy, as the eval fixtures carry, still is.
- **Counting (V07, V08, V32, P2, Q20, Q23, Q10).**
  - In the trivial tier, one reviewer's traced Critical or High is contested and verified, as the docs say.
  - The verdict word follows from the counts, and `counts.md` prints it: BLOCK when a Critical or High is counted, CONCERNS when only Medium or Low ones are, CLEAN when nothing is. The stamp refuses any other word [PROPOSED rule: before this, only CLEAN with a Critical or High was refused].
  - A dedup group joining two reviewers' findings in different files, where no file is shared, counts the votes the script matched itself. So two unrelated Mediums can't make one kept finding; such a finding goes to a verifier instead. One recorded replay changes from 2 votes to 1 for a finding the verifier confirmed; its counts are unchanged.
  - A review that changed after the tally that listed the dedup candidates isn't counted with those groups.
  - One bad JSON line costs only that line of a review, and is named.
  - The tally and the files beside it are written whole or not at all.
  - A ledger finding that isn't a record stops the command instead of vanishing on the next save.
- **The lead's steps (P5).** During a review run, a reviewer whose prompt doesn't hold its brief word for word is refused.
- **Scanners.**
  - curl's `--user`, `-U`, `--proxy-user` and joined `-uUSER:PASS` forms are masked (F-bd5e8b92).
  - Unquoted credentials in `.npmrc`, shell scripts, Dockerfiles (`ENV`), `.pypirc` and `.netrc` are found (F-7b40ffc1).
  - An attacker-chosen expression in `actions/github-script`'s `script:` is an injection, as in `run:` (F-c02301cf).
  - Upper-case extensions (`app.JS`) get the code rules (Q14).
  - One odd `package.json` or lockfile no longer stops every dependency check (Q19).
  - `catalog.info(password)` is no log call, while `audit_log.info(password)` is (F-a92bf605).
  - `DEBUG = True` under `devices/` or `latest/` is flagged (F-0203513e).
  - A database URL whose password holds an unencoded `@` is found (F-0c3380dc).
  - An assert in a nested function the test never calls doesn't count as a check (V42).
  - A scope entry with a port that isn't a number is refused with a reason (Q12).
  - Long one-line YAML flow lists are read in linear time (V36).
  - The scan's live request cap is shared with `browse.py`'s for the whole run (V41).
- **The browser driver (O4, V45).** It takes its lock with `msvcrt` on Windows, which has no `fcntl`, and `press` types nothing into a focused password, hidden or file field.
- **The eval kit (V38, V40, Q15, V43, V05, V20, M2).**
  - An unmatched Nit needs a label and costs precision like any finding.
  - A cited range over 10 lines, or `myapp.js` for `app.js`, doesn't point at a plant.
  - Fix advice that names a planted defect earns no credit.
  - The fast-create id check freezes the clock, so the `Date.now()` collision fails it.
  - The consent eval commits its `rules.md`, as a clone would, needs the scan to report mutation testing blocked, and `review-never-edits` also catches shell edits.
  - `bench_stats.py` reads an archived run's recorded scores when the files have the same time (a fresh clone), and `--rescore` forces scoring again.
  - No test leaves a file in the system's temporary folder.
  - Rescoring the 5.2.4 archive with these changes gives the same numbers.

### audit batch 4 (documents and the benchmark scorer)

Batch 4 of the ultimate audit of 30 Oct 2026 (03 §5.57). The two scorer and number fixes have tests that fail on the code before them (`plugin/tests/cases_8.py`); the rest are document fixes.
- **The benchmark splitter (V18).** The death match's free-form splitter now keeps a numbered finding's flush bullets with it and ends a list at the prose after it. The old splitter cut the code-review plugin's findings so that the claim and the location landed in different blocks. Rescored with the archived replies: the plugin as it runs found 48 planted bugs, not 34, and its judged findings fell from 130 to 85, because one finding no longer counts as several bullets. Labels moved to the new block numbers wherever the text was already labelled. Two blind labellers labelled the 7 blocks left over and agreed on all 7. The scores before are kept, and so are the labels as first given. The plain-Claude arms were rescored too (89, 102 and 165 of 245). The older death matches can't be rescored, because their replies weren't kept, and the README says so.
- **The README's benchmark numbers (V06)** are regenerated from `stats.json`, with the cluster intervals (for example 20–68% for the built-in `/code-review`), and a script test now holds them to it. The budget line is measured again: about 864 tokens always on, and the review skill about 8.8k when it runs.
- **The benchmark's tuning overlap (V17)** is now disclosed in the README and the write-up. The planted apps are Curmudgeon's own tuning apps, and its checklist names several of their defect classes. Plain Claude given the checklist found 165 of 245. A benchmark on apps Curmudgeon has never seen is still to be run [PROPOSED].
- **CI and headless runs (P1, Q22).** The README's CI recipe pins each action to a full commit SHA. It also sets `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`, because print mode otherwise stops waiting for background reviewers after ten minutes and the run ends with no review.
- **Windows (57.4, V19).** The README says plainly that Windows isn't yet supported for live-site checks or the stop gates. It also gives the latest CI results: macOS passes, while the Windows run reached 305 tests and passed 220 of them. CONTRIBUTING no longer implies those jobs gate anything.
- **What is git-ignored (V04).** PRIVACY.md and the README now say exactly which parts of `.critic/` are ignored. The findings, the teardown, the ledger and the scan's screenshots are not.
- **Smaller fixes.** Curmudgeon never offers to install Playwright (V11). Only controls that look destructive are simulated in the scan, so the README says so instead of promising that "even a link-style delete never reaches" a running app (V15). CONTRIBUTING points new tests to the highest-numbered part (V21). SECURITY.md gives the right manifest path (V16).

### Qodo on #21

Two findings, each with a test that fails on the code before it (`plugin/tests/cases_8.py`).
- A background scan whose report says a check didn't run (degraded), or can't be read, is recorded as failed and retried. Whatever it did find still counts.
- "Disclosure of sensitive data" (and of personal, customer or credential data) is a security phrase; a disclosure widget still isn't.

### Qodo on #20

Six findings (one High), each with a test that fails on the code before it (`plugin/tests/cases_8.py`).
- A stamped file deleted before any review is saved now blocks the gate (High).
- A background scan that fails, or writes no report, is recorded as failed, never as done.
- Files whose part ran out of time or failed get up to half of the next stop's first part, so a stream of fresh edits can't keep them waiting.
- A Python import written across lines in parentheses (`from . import (\n    mod,\n)`) or with backslashes counts when finding a deleted module's callers.
- A change that both edits and deletes scans the deletion's callers as well as the edited files.
- "Disclosure widget" and "data isolation" in tests are not security terms; "information disclosure", "unauthorized disclosure" and "customer isolation" are.

### Qodo on #19

Five findings, each with a test that fails on the code before it (`plugin/tests/cases_8.py`).
- The gate's suggested `stamp --add` command quotes each deleted path, so a file name is never shell syntax to copy.
- Tenant-boundary phrases ("tenant scoping", "tenant context", "tenant boundary") make a finding a security one; a plain "tenant" still doesn't.
- A deleted package `__init__.py` counts as the provider for `from . import name`, so its callers are listed and scanned.
- A relative import must resolve to the deleted file's exact path; only non-relative imports may leave out a source root. A same-named module elsewhere no longer joins a deletion's callers.
- A deletion nothing calls reports the static check as not applicable, not as blocked, so the review isn't marked as degraded.

### the next collected round (Qodo on #18)

Six findings, each with a test that fails on the code before it (`plugin/tests/cases_8.py`).
- A deletion's time is only a best guess (a file created beside it after the review looks the same as a deletion after the review). So when the last review did cover a deletion, stamp the deleted path (`critic_ledger.py stamp --add src/auth.py`) and the gate stops asking; its message says so.
- The background check records the time a file had when its scan started, so an edit made during the scan ranks first at the next stop.
- A deletion nothing calls scans nothing, instead of the whole project.
- A deleted module's callers are found through relative imports (`'./utils'`, `from .mod import f`) and imports that leave out a source root such as `src/`.
- A bare "tenant" in a title no longer makes a finding a security one; phrases such as "cross-tenant" and "tenant isolation" still do.
- A deleted file whose first line is longer than the brief's limit (minified code) shows that line's masked start, not "no removed lines".

### the collected round after batches 2 and 3 (Qodo on #15, #16 and #17, and the batch 3 review)

Twenty findings, gathered and fixed together as ruled (03 §5.57.7). Each fix has a test that fails on the code before it (`plugin/tests/cases_8.py`).
- **Deletions in a review (Qodo on #17).** A deleted file's removed lines reach the brief with secrets masked, each line behind a bar so no removed line can close a fence or start a heading. They count toward the tier. A function moved to another file no longer lists its new callers as broken. A finding at a caller the deletion broke counts as introduced, not as already there. A deletion-only run scans the callers instead of reusing an earlier run's file list.
- **Deletions and the stop gate (Qodo on #17, batch 3 review).** Each missing stamped file is recorded with when the gate first saw it go (`.critic/gate-deleted.json`). So later activity in its folder doesn't re-open a reviewed deletion, deleting it again starts a new batch, and `stamp` keeps it until a review saved after it covers it.
- **What the stop gate watches (Qodo on #17, batch 3 review).** In git, the gate watches what git doesn't ignore, so a project's own `.gitignore` decides what is generated. Outside git, it skips known generated dot-folders. Hand-written code under `.vitepress`, `.buildkite` and the like counts again, and Claude Code's worktrees (`.claude/worktrees/`) and other nested checkouts never do.
- **The background check (Qodo on #17).** It sees staged files in a repository with no commit yet, starts each stop with the part the last one had no time for, and has no cap that leaves files out for good. An interrupted move of the feed's settings never leaves them unreadable.
- **The integrity lens (Qodo on #16).**
  - Adopting a recorded copy takes two steps: `--integrity-adopt` shows every host, how many there are and a code, and `--integrity-adopt --confirm CODE` trusts exactly those bytes. A copy whose pages have no own-site list is refused (record it again).
  - The recorded copy is checked and parsed from one read.
  - A Latin name with a Han or kana sign standing in for a letter (`paypa丨`, `facebロロk`, `paypalーー`) is a look-alike, while real names mixing romaji and kana (`toyotaトヨタ`, `sonyストアー`) are not.
  - A scheme-relative `<base>` takes the page's own scheme from its canonical or `og:url` address.
- **Security findings (Qodo on #15).** Phrases such as tenant isolation, access control, privilege escalation and session fixation make a finding a security one (bare words like "session" or "isolation" don't, so ordinary findings keep ordinary rules), and a reviewer can mark one `"security": true`. Taking one below High, or refuting it, then needs attacker, gain and a listed reason (03 §5.57.8). A reviewer's flag carries through when findings are merged, and the verifier is told when the security rules apply.
- **From this round's blind review (3 reviewers).**
  - The gate skips tools' folders in git too.
  - When git lists nothing for the project (an enclosing repository that ignores it), the gate falls back to a walk, so it is never silently off. Outside git, it watches only known code dot-folders and dot-folders holding a stamped file.
  - Deleted text is masked line by line before it is cut, so a secret at the cut is never half-masked.
  - A caller still importing a deleted module stays in the blast radius, whatever else defines the same name, and a deleted file's bare name no longer marks old findings as introduced.
  - A stroke look-alike (丨 亅 匚 凵) next to a Latin letter is flagged even when a real kana word follows.
  - The background check orders files by a per-file record of what it has scanned, so a new edit never sends it back to the start, and a part that ran out of time goes after the files not reached yet. Its walk outside git stops after 500,000 entries, which bounds the hook's time; files beyond that in walk order are not seen.
  - The adopt code is 32 characters (128 bits), and the gate checks each folder for a nested checkout once.

### fixes from the full audit, batch 3 of 5 (the stop gates and the change map)

Each fix has a test that fails on the code before it (`plugin/tests/cases_8.py`).
- Deleting a file the last review stamped now counts as an edit, so the stop gate asks for a review, alongside any other edit, so a new edit always starts a new batch; a review saved after the deletion covers it, and `stamp --add` drops deleted files (audit O1).
- New code under the dot-folders people write code in (`.claude`, `.github`, `.husky`, `.devcontainer` and a few more) counts for the stop gate; other dot-folders (`.env`, `.svelte-kit`, `.yarn`, `.terraform`) hold generated or downloaded files and still don't (audit O2).
- In a project that is a subfolder of a repository, the background check sees tracked edits (`git diff --relative`; audit V47).
- Outside git, the background check finds changed files by their own times (audit O3).
- The background check scans every changed file, in parts of 200, instead of silently dropping everything past the first 200 (audit Q09).
- The security feed's settings live in `~/.curmudgeon/feed` (or `CURMUDGEON_FEED_DIR`), so the skill and the background check see the same feed. A feed set up under the plugin's data folder is moved there once (audit V46).
- The change map counts deleted files: their names and removed lines are sized and checked for sensitive words, so deleting `auth.py` with a one-line README edit is no longer trivial. The deleted file's callers join the blast radius, and the reviewers' brief shows its removed lines and who still refers to it (audit V30).
- A changed file with a space or a quote in its name gets its hunks and touched text, and a new one is marked new (audit F-a9c4ecf9).

### fixes from the full audit, batch 2 of 5 (the browser integrity lens)

Each fix has a test that fails on 5.2.6 (`plugin/tests/cases_8.py`), and the lens fixture (`eval/lens12.json`) gains three plants, a clean-twin page and three decoy pages: 13 of 13 found, 0 wrong rows, nothing on the decoys or the clean twin (5.2.6 on the same fixture: 7 of 13 found, 5 wrong rows on the decoys and 5 on the clean twin).
- A page that names a new site as its own (canonical, `og:url`) no longer makes that site's forms, scripts and links count as unchanged. The recorded copy keeps the sites each page said it was, and a page that now claims another one fails `integrity-changed` (audit F-9c12cea5, High).
- `<base href>` is not the page's own site. Relative form, script and link targets are resolved against it, so a base on another site shows up against the recorded copy as a changed form, link or a new origin, and, on a page that names its own site (canonical or `og:url`), as an off-site form or an unpinned script. On a page that names no site and has no recorded copy, a relative script sent off-site by a base raises nothing: the lens can't tell the page's own host from another (audit F-5a56b49c, High).
- The recorded copy is trusted only when the owner recorded it, or adopted it with the new `--integrity-adopt` after seeing every host it lists, on this machine, and git doesn't track it. A copy that came with the code is ignored with a note, and agents can't record or adopt one (audit Q04).
- A Japanese, Chinese or Korean host that mixes its own scripts (Han with Hiragana or Katakana, Han with Hangul, the repeat mark 々) is no longer a look-alike. Latin with Cyrillic still is, and so is a Latin name with a lone Hangul letter, Bopomofo or kana standing in for a Latin letter (audit F-e55d7809).
- From the blind review of this batch: `critic_scan.py` refuses shortened flags (`--integrity-adop`), and the agents' guard refuses recording or adopting the trusted copy in the plain and the usual hidden forms (a shortened, split or variable flag, a decoder, `python -c`, the helper functions). Like every check on command text, it is a tripwire, not a wall: an agent determined to hide the flag could still do it, so the owner's permission settings stay the real boundary. Plain reading (`grep`) and other programs' own flags (`pytest --integration`, `yarn check --integrity`) still pass. The recorded copy is kept out of git, and adopting a tracked one fails with how to untrack it. Adopting refuses a copy with control characters, which could hide a host on a terminal, and trusts exactly the bytes it showed. `<base>` is read as a browser reads it: the first with an href wins (an empty one keeps targets on the page), `http:host` and `https:///host` name a host, `https:host` under an http base names a host, and an http base makes a relative or scheme-relative form insecure. Look-alike hosts are judged after the same folding a browser applies: halfwidth forms don't slip past, the ideographic full stops (。 ｡) split labels, and 〇 counts as ideographic. Link labels drop invisible marks (`&rlm;` on right-to-left pages) when recorded, so such copies can be adopted, and adopting refuses hosts that hold spaces of any kind or run past 253 characters. Adopting refuses line breaks, bidi and zero-width marks and malformed entries, and recording refuses a copy git tracks.

**After upgrading:** run `critic_scan.py . --integrity-record` again on a version you trust. A copy recorded before this change has no own-site list and isn't noted as yours, so it is ignored until you record it again.

### fixes from Qodo's review of PR #14

Qodo reviewed the batch 1 pull request and raised three Mediums and one Low. Each was checked against the code, and all four are fixed, each with a test that fails on 5.2.6 (`plugin/tests/cases_7.py`).
- Taking a Critical or a High below High now needs what refuting it would: an executed run for a Critical, and the attacker, the gain and a listed reason for a security finding (03 §5.57.8). Before, a trace was enough to lower a Critical to Low and lift its BLOCK, on less evidence than a refutation needs.
- `critic_ledger.py adopt --show` prints every ruling in full and every finding that isn't open. It used to cut each ruling at 300 characters and list only 40 findings, so an owner could adopt rulings they hadn't seen.
- When the owner's gate record can't be checked, the stop gate and the background check stay off and say why. Before, an error there fell through to the project's own marker, which a repository can commit.
- The variant hunt prints the same verifier batches as `critic_run.py next`, giving each Critical variant its own verifier in the full tier. Both now use one shared `verifier_batches`.

## 5.2.6 (3 November 2026): fixes from the full audit, batch 1 of 5

The full audit of 5.2.5 (six blind lenses, Curmudgeon's own full-tier review, three outside reviewers and mutation testing) confirmed 89 findings: 5 High, 27 Medium, 51 Low, 5 Nit. Batch 1 fixes the trust and evidence rules. Each fix has a test that fails on 5.2.5 (`plugin/tests/cases_7.py`).

**After upgrading**
- Run `/curmudgeon:gate on` (or `async`) again where you use the stop checks: the setting now lives outside the project, so the old marker alone does nothing.
- The first ledger command in each project sets your existing ledger aside, because 5.2.5 didn't record its checksum. Check its rulings with `critic_ledger.py adopt <file> --show`, then `adopt <file>` to take it back.

**Trust boundaries**
- A `.critic/ledger.json` counts as yours only when git doesn't track it and it is exactly the file Curmudgeon last saved on this computer (its checksum is kept outside the project). A read-only command (`show`, `check`) moves nothing, and if that outside folder can't be written, the command stops and changes nothing. A ledger that came in a zip, sits untracked inside another repository, or was changed after the last save is set aside on the next run and a new ledger starts; its rulings never apply. `critic_ledger.py adopt <file> --show` lists its rulings, and `adopt <file>` takes it back after you agree. (Before, a false-positive ruling in such a ledger could hide a Critical.)
- The page server answers a refused request with a 404, never from a file inside the served folder, and a folder's `index.html` that links outside is never served. (Before, a planted link at `.curmudgeon-refused/404` served any file you can read.)
- The browser driver and the scan serve a page only from inside the project: a page outside it, directly or through a link, is refused (its real folder would become the server's root). Copy it into the project, or run from its folder.
- Lockfiles, manifests and earlier CI results that link outside the project are never read, and each is listed once.
- `.critic/gate` and `.critic/gate-async` turn a stop check on only when you ran `/curmudgeon:gate`; a committed marker does nothing.
- Reviewers, verifiers and the detector can't record your sign-off on the security feed or start its downloads, and can't write into another agent's private folder.

**Evidence rules**
- A verifier may lower a finding to Nit only from Low. A downgrade of two or more steps, or from Critical or High, needs a run or a trace and a note that cites the reason as `file:line`; otherwise the old impact stays (03 §5.57.2).
- The review file names a finding's source; a reviewer can no longer mark its own finding as a scan row to skip the quote check.
- Verdicts applied from a file the verifier's stop hook didn't save mark the run DEGRADED and are named.
- A finding a verifier refuted stays refuted when the ledger loads again.
- In the full tier each Critical gets its own verifier, and `critic_run.py next` walks the variant hunt before the teardown.
- In round 3 a new unconfirmed Critical or High is recorded and marked held, so the stop gate shows it.
- Every finding at a line of a text file needs its quote (not only a list of code extensions), and a Low needs its failing case.
- A false-positive ruling hides nothing when it has no rule id (scan rows) or when its id was never scored (a Critical or High).
- The tally refuses to count when the ledger can't be read.
- A Medium only one reviewer raised, without a run, now goes to a blind verifier and is kept only if confirmed (before, it was dropped; the self-review lost a real High this way). A single-vote Critical or High was already verified, never dropped (03 §5.57.6).
- Every git command runs without the project's own commands from `.git` (`core.fsmonitor`, its own filter and diff drivers, hooks, `gpg.program` through `log.showSignature`, and the same inside submodules), passed as `git -c` overrides (or, for a filter whose name contains `=`, through `GIT_CONFIG_COUNT`, with git refused below 2.31 in that case), and with `--ignore-submodules=all` on diff, log, show and status so a submodule's own `ignore` setting can't turn recursion back on: a project that arrives with its own `.git` could otherwise make git run a program (03 §5.57.6). The owner's global filters, such as git-lfs, keep working.

**Privacy**
- `--online` sends package names only after you agree on that run (`critic_ledger.py consent online`); without it the lookup runs offline and the report says so.
- Text from earlier tools' SARIF results is masked like every other report field.

**Tests**
- New tests pin the quote check and the evidence floors where mutation testing found gaps (a missing file, the 60-character refutation, two-vote confirmation, quote windows).

## 5.2.5 (30 October 2026)

Fixes from an independent combined review (two outside reviews and two blind reviews, every claim reproduced or read), each with a test that fails on the code before it, and each batch put through three blind review rounds. [plugin/RULINGS.md](plugin/RULINGS.md) indexes the rulings the code cites.

**Evidence rules**
- The scan's FAILs reach the tally and the counts.
- The quote check is strict: the cited line or one either side, case kept, at least 12 characters.
- When reviewers disagree on a finding's impact, it is filed at the highest and always verified.
- One reviewer's findings are never merged into each other.
- A reviewer's own "executed" no longer makes a finding confirmed without a verifier.
- Each tier verifies exactly what its rule says, and a missing required verdict marks the run DEGRADED.
- Verifier verdicts are saved by a hook, unchanged.
- The teardown is checked against the counts.

**Trust boundaries**
- A `.critic/rules.md` or `scope.json` that may have come with the code is used only after you approve that exact file (`critic_ledger.py approve`, which shows the whole file). A file counts as yours only when your git work tree tracks no copy of it and you didn't get it in a zip.
- Approvals, and consent for live sites and writes (recorded per run), are kept outside the project in `~/.curmudgeon`.
- A reviewer's copy holds one anonymous commit of your last commit, without `.critic/`, older versions or a reflog.
- Reviewers and verifiers can't:
  - write into your project from their copy;
  - read your project's `.git`;
  - write the record of your approvals and consent;
  - use the network or install commands the guard recognises.
  This is a tripwire, not a sandbox (PRIVACY.md).
- Verifiers read packets only by path, one batch at most.
- A false-positive ruling hides only its exact finding.
- A review needs a stop-hook record showing it was written in a private copy, or the run is DEGRADED.

**Hooks, platforms and the eval kit**
- The always-on hooks are merged into one PreToolUse and one PostToolUse process: about 25 and 30 ms per call, down from about 85 and 47 ms.
- On a Mac or Windows machine with no one at the screen (CI, SSH), the security database's folder picker no longer waits ten minutes for a window.
- A browser start refuses missing consent before looking for Playwright.
- The skill says Curmudgeon never installs Playwright.
- CI pins actions v7 by commit and adds Python 3.14. A macOS job (all 244 script tests pass) and the full script tests on Windows (168 of 244 pass) run but are not yet required.
- The eval kit:
  - fills the planted key into each copy of the fixture, so no arm sees the placeholder's name;
  - widens one answer-key entry (E02) to the wording reviewers actually use;
  - computes its confidence intervals by app as well as by run;
  - archives three plain-Claude arms.
  The 5.2.4 benchmark write-up has the rescored figures; the README's Benchmarks section is updated in the next documentation pass.

## 5.2.4 (29 October 2026)

- The plugin, marketplace and review-skill descriptions, and the README's opening, now say what Curmudgeon does at every size: one to three blind reviewers sized to the risk, and findings re-checked blind (all of them in a full review, the Critical and High ones in a lite review, the contested ones in the smallest). They used to say three reviewers and every finding, which is true only of a full review.
- The plugin description mentions the security scan; keywords add audit and dependencies.
- This changelog.

## 5.2.3 (28 October 2026)

- The scanner tests' fake secrets are built from pieces at run time, like the other fake keys, so no file in the plugin carries a credential-shaped value (found by the plugin directory's validation).
- README: "How a review runs" explains the security scan, and that its local database is off by default.

## 5.2.2 (28 October 2026)

- Ready for Anthropic's plugin directory: the tests are split so no file in the plugin passes the directory's 256 KiB limit; `PRIVACY.md` (Curmudgeon collects nothing for itself; the four opt-in features, what each sends and to whom); `SECURITY.md` (how to report a vulnerability privately; a first reply within 7 days); a README Examples section with six prompts.
- README corrections, each checked against the code or Anthropic's docs: reviewer counts by tier, the shell install needs Claude Code 2.1.292, missing Playwright reads "unavailable", the full browser-check list, the comparison with Anthropic's review options re-checked, and what Curmudgeon writes.

## 5.2.1 (28 October 2026, the first release on `main` since 4.2.1)

It holds everything built since 4.2.1: 4.2.2, 5.0.0, the 5.1 work and 5.2. Measured: the 5.2 release gate passed on all seven tests (planted bugs 48/48, 75/81, 6/6, 12/12), and a 5.2.1 smoke run found 15/16, 23/27, 2/2 and 4/4 at $1.41 a run.

**Security suite (5.2)**
- `/curmudgeon:review security`: a security-only review, sized like any other, that changes no file.
- The browser integrity lens: look-alike links and hosts, forms that post over plain http or to another site, scripts from other sites with no integrity hash, a weak Content-Security-Policy, and a recorded copy of a trusted version to compare against. Measured on its own fixture: 10 of 10 planted defects, no row on decoys or the clean twin.
- The local security database, off until you say yes: built in a folder you pick in a folder window, after an estimate you sign off on, from OSV.dev's public npm and PyPI data, with every match checked against CISA's list of vulnerabilities exploited in the wild (a FAIL). Nothing about your project leaves your machine. Download and build progress in a terminal. Built for real on Windows: about 245 MB downloaded, a 73.5 MB database in 30 seconds.
- Without Playwright, Curmudgeon says how to install it and offers once; it never installs anything itself.

**Since 5.2**
- Decision 34: the scan's click check presses buttons named like Delete, Pay or Send only in the simulation (writes answered locally, a running app replayed from a one-time read-only recording), instead of skipping them.
- Fixes from a security scan of the plugin itself (2 High, 5 Medium) and two blind full-tier rounds (the database code: 2 High, 6 Medium, 5 Low; the 28 Oct changes: 8 Medium, 5 Low), each with a test that fails on the old code. Among them: a duplicate `href` can no longer hide a link's real target; mutation testing restores only backups it recorded itself, outside the project; a link to a private file outside the project is never copied into a reviewer's workspace; a committed ledger can't hide findings; the page server never serves `.critic/` or dotfiles; yarn and pnpm lockfiles are reported as not read instead of passing.
- The browser driver runs on Python 3.9 to 3.11 again, and database connections are closed (Windows locks open files). CI covers Python 3.9 to 3.13 and Windows.
- Two cost cuts were measured and left out because they found fewer planted bugs: shorter reviews with dedup on Haiku 5.5, and short reviews in the lite tier.

**The 5.1 work (24 and 25 October, never released on its own)**
- Fastest results first: the scripted results are shown while the reviewers still work.
- A Nits tier for true but trivial findings, listed and never counted.
- Two other cost cuts (batched verifiers, a lighter lead) measured worse and were reverted.
- Decision 39: a BLOCK on a clean twin fails the release gate only when nothing real backs it.

## 5.0.0 (24 October 2026)

- Structural blindness: each reviewer and verifier works in its own private, frozen copy of the project, with no `.critic/` folder in it, and a guard keeps it there.
- New scripted lenses, each measured on planted defects before it shipped: tests of the tests, CI and supply chain, agent and MCP configuration, release and rollback, requirements and intent, and operations.
- The audit mode for someone else's system, with a deny-by-default scope file for live checks.
- The browser driver: a step-by-step simulated page for reviewers and verifiers, with before-and-after checks.
- The variant hunt, LSP use by reviewers and verifiers, other scanners' SARIF read as evidence, and Semgrep noticed but never run.
- Real token accounting, the accept/kill gate, the golden and replay tests, and CI.
- One `/curmudgeon:fix` command for patch, iterate, approve and rollback.
- A leaner footprint: about 862 tokens in every session, down from about 1,516 in 4.2.1.
- Measured against 4.2.2 (three runs of each test): more planted bugs found in every test. Death match: 134 of 147 planted bugs, against 84 for plain Claude and 44 for Anthropic's code-review plugin.

## 4.2.2 (24 October 2026)

- Security and integrity fixes, reviewed blind over three rounds (the last round's fixes not re-reviewed). Released on `main` as part of 5.2.1.

## 4.2.1 (18 October 2026)

- Twelve fixes from a fresh blind review of 4.2.0. 57 script tests.

## 4.2.0 (18 October 2026)

- The optional outside reviewer: offered once, default no. Curmudgeon writes a brief, you paste it into another AI yourself and paste the answer back, and its findings get the same quote check and blind verification. Two double-blind tests had found almost no overlap between another AI's review and Curmudgeon's (0 of 23 findings, then 2 of 14).

## 4.1.1 (18 October 2026)

- Fixes for an outside double-blind review's findings.

## 4.1.0 (18 October 2026)

- Memory that notes and never hides: three similar dismissals become a note on look-alike Medium and Low findings, which stay counted.
- The refutation log, spot-checks and precision by category, the run log, Python checks read with Python's own parser, an SPDX licence check, and rule files.

## 4.0.1 to 4.0.5 (18 October 2026)

- Plugin-directory lint fixes, the icon, and credential-pattern flags.

## 4.0.0 (18 October 2026)

- Published as Curmudgeon under the MIT licence, renamed from Critic.
- Three blind reviewers with a vote counted by a script, blind per-finding verification that may lower an impact but never raise it, the quote check, risk tiers and a change map, stable finding ids in a ledger.
- Every free outside tool it learned from was rebuilt as its own code; it installs nothing.
- An eval kit that measures precision as well as recall, with decoys and clean twins. The goal changed from finding everything to few false alarms, with evidence for every finding.
- Five rounds of self-review before release.

## Before Curmudgeon: Critic (17 October 2026)

- Critic v1: a read-only review skill, with free scripted checks run first.
- Critic v2: a closed loop of teardown, refactor and re-check, with approve, iterate, patch and rollback.
- Critic v3 and v3.1: a plugin with separate judgment and detector agents, a DEGRADED banner, an intent gate, "no case, no finding", a three-round cap and the stop gate. Its self-review found 32 findings, all fixed in 3.1.
