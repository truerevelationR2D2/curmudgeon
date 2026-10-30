## Code review

Reviewed `git diff main...HEAD` ("Add the app"). It adds 6 migration files and no application code. Nothing was posted and no files were changed. The 4 review agents flagged 3 distinct issues, and each was validated.

**CLAUDE.md compliance:** no issues. The repo has no CLAUDE.md files, so there are no rules to violate.

**Issues found (3):**

1. **`shop/migrations/0007_backfill.py:12`: dependency points to a migration that doesn't exist.**
   - It declares `dependencies = [("shop", "0006_product_slug")]`, but the only 0006 migration is `0006_safe`.
   - Django raises `NodeNotFoundError` when it builds the migration graph, so `migrate` fails.
   - Likely fix: depend on `("shop", "0006_safe")`.

2. **`shop/migrations/0006_safe.py:9`: depends on a missing `0005_initial`.**
   - It declares `dependencies = [("shop", "0005_initial")]`, but there is no 0005 migration on `main` or in the PR.
   - Django raises `NodeNotFoundError` once the `shop` app is set up properly. Fixing issue 1 alone won't help: the chain stays broken until `0005_initial` exists or the dependency is corrected.

3. **`alembic/versions/3b1f_add_refunds.py:12` and `:18`: `CONCURRENTLY` inside a transaction.**
   - `upgrade()` runs `CREATE INDEX CONCURRENTLY` and `downgrade()` runs `DROP INDEX CONCURRENTLY`, both through plain `op.execute`.
   - On PostgreSQL, Alembic's default is to run each migration in a transaction, which fails with "cannot run inside a transaction block". The `bigserial` column in `2a0e_safe.py` shows the target is PostgreSQL.
   - Fix: wrap those calls in `with op.get_context().autocommit_block():`.
   - Caveat: the PR has no `env.py`, so this rests on Alembic's default behaviour. It would not apply if an `env.py` outside this PR sets autocommit.

**Not flagged:**
- `CREATE INDEX CONCURRENTLY` in the two `db/migrations/*.sql` files: whether it fails depends on how the runner executes them, which the diff doesn't show.
- The PR description says it adds application code, but it only adds migration files. This is not a code defect.