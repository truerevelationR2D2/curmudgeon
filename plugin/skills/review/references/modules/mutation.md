# Optional module: mutation testing

Read this when a run asks for `--mutate <files>`. Mutation testing changes one source line at a time while the
project's tests run, and puts each file back. It is one of the two checks that run a project command; the other is
`--project-checks`.

It runs the test command given with `--test-cmd`, or the `Test command:` line in `.critic/rules.md` only together with
`--project-checks`, and only from a rules.md the owner approved as it now is (step 2 of SKILL.md says how: show the
user everything `critic_ledger.py approve rules.md --show` prints, and approve only on their yes). With neither, the
scan reports mutation testing as blocked and runs nothing. A backup of each changed file is kept beside it, and a
private list of the backups outside the project, so a killed run is restored on the next one.
