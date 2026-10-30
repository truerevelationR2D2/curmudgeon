## Code review: `git diff main...HEAD` (1 commit, 6 new migration files)

I checked the diff for bugs and for CLAUDE.md compliance. The repo has no CLAUDE.md. I read the diff myself and did not launch the agent pipeline, because the change is six small files. I did not run any of the migrations.

### Issues found

**1. Broken migration dependency in `shop/migrations/0007_backfill.py` (line 12), so Django cannot load the graph.**
- `dependencies = [("shop", "0006_product_slug")]` points at a migration that doesn't exist. The branch only adds `0006_safe.py`.
- Django will raise `NodeNotFoundError` on `migrate` and `makemigrations`.
- `shop/migrations/0006_safe.py` (line 10) has the same problem. It depends on `("shop", "0005_initial")`, and `main` has no `shop` migrations at all.
- Fix: point `0007` at `0006_safe` and make `0006_safe` depend on a migration that really exists.

**2. `CREATE INDEX CONCURRENTLY` inside an Alembic migration in `alembic/versions/3b1f_add_refunds.py` (lines 13 and 18).**
- `upgrade()` runs `op.execute("CREATE INDEX CONCURRENTLY ...")` and `downgrade()` runs `DROP INDEX CONCURRENTLY`. Neither is wrapped in `with op.get_context().autocommit_block():`.
- Alembic runs each migration inside a transaction on Postgres by default, and Postgres rejects these statements there with `CREATE INDEX CONCURRENTLY cannot run inside a transaction block`. The upgrade and the downgrade would both fail.
- Caveat: the branch has no `env.py`, so I assumed Alembic's default transactional DDL. If `transaction_per_migration` is turned off or the migration is otherwise run outside a transaction, this wouldn't fail.

### Not flagged
- `db/migrations/*.sql` reference `orders` and `customers`, which no file on this branch creates. Those tables may come from elsewhere, and I can't confirm that from the diff.
- Whether `CONCURRENTLY` works in `db/migrations/*.sql` depends on how the runner applies the files, and the branch doesn't include one.