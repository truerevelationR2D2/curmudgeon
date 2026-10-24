# When patching stops converging: the design finding (SC-73)

`critic_ledger.py round` and `import` print a `WHACK-A-MOLE` line when one control in one file has had at least two
findings marked fixed and another is open. Each fix closed one hole and the next review found another. More patches of
the same kind will not converge. Stop fixing that control and give the owner one **design finding** instead.

## What to write

One finding with `category: design`, the file and the control named in the WHACK-A-MOLE line, and:

1. **The pattern.** The findings that were fixed and the one still open, by id. Then one sentence on what they have in
   common, for example "each bypass reached `.critic/` through a path the shell parser didn't model".
2. **The real requirement.** What the control is for, in one plain sentence, and the threat it has to stop. Name the
   threat model explicitly, honest mistake or hostile actor, because the right fix depends on it.
3. **Up to five solutions, ranked best to worst.** Use the ladder below to rank them. Give each one:
   - what it is, in one or two sentences;
   - what it removes (code, checks, steps) and what it adds;
   - the risk that remains after it;
   - its cost: effort, run time or tokens, and anything the user has to set up;
   - whether it needs the owner's yes (it changes a rule, loosens a default, or can't be undone).
4. **The recommendation.** Which one to build, and how we'll know it worked: the test that fails today and passes after.

Do not build any of them until the owner chooses. Report what wasn't re-reviewed (the three-round rule).

## The ladder: how to rank solutions, best first

1. **Remove the need.** Change the design so the dangerous thing isn't there to reach: the data isn't in the agent's
   world, the capability isn't granted, the input is never parsed. Nothing is left to bypass.
2. **Isolate by construction.** Put a boundary the actor can't cross by accident: a separate copy, process, sandbox,
   user or origin, set up so the safe path is the default one.
3. **Allow only what's known good, at one choke point.** A typed API, a fixed list of permitted actions, positive
   validation where the input enters. Everything not on the list fails closed.
4. **Detect and refuse.** A denylist, pattern match or parser that tries to spot the bad case. Every new spelling is a
   new hole, so this is best effort. Use it as a backstop behind rungs 1 to 3, never alone.
5. **Accept, document and watch.** Write down the remaining risk, tell the user, and log or alert when it happens. This
   is right only when the rungs above cost more than the harm.

Repeated holes in a rung-4 control are the usual sign that the design should move up the ladder. Rank by how much risk
each option leaves, then by cost; a cheaper option never outranks a safer one unless the owner says so.
