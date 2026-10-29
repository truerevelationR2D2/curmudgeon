**BLOCK** · Counts: 0 Critical, 2 High, 3 Medium, 0 Low

I ran the lite tier on the six migration files: one blind reviewer, and blind verification of the two High findings. The scripted scan reported 0 FAIL. I changed no project files; only the review's own `.critic/` output was written. The full teardown is in `.critic/last-review.md`.

**High (verified by tracing the code)**
- **C1** `alembic/versions/3b1f_add_refunds.py:12` (`F-9a88dadc`): `CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY` run inside Alembic's default migration transaction, and PostgreSQL rejects both there. Upgrade and downgrade would both fail. The repo has no `env.py`, so the default transactional setup is an assumption.
- **C2** `shop/migrations/0007_backfill.py:12` (`F-d118973e`): 0007 depends on `0006_product_slug`, but the only 0006 present is `0006_safe`. Django's migrate would raise `NodeNotFoundError`.

**Medium (one reviewer, not verified, confidence "possible")**
- **C3** `db/migrations/0002_orders.sql:4` (`F-74ac8b08`): there is no down script. After a failed `CONCURRENTLY` build, the file can't be rerun.
- **C4** `db/migrations/0002_orders.sql:6` (`F-d19f80d9`): the `CONCURRENTLY` index, `NOT VALID` and `VALIDATE` share one file, so no single runner mode suits all three. The runner isn't in the change, so this is inferred.
- **C5** `shop/migrations/0007_backfill.py:6` (`F-fdc1b10a`): the backfill saves one row at a time and ends with an unbatched `UPDATE`, all in one transaction.

There was also one nit, not counted: the `COMMENT` at `db/migrations/0001_safe.sql:14` targets `orders.note`, and no migration in the change creates that column.

**What wasn't checked**
- Nothing was executed. Django, Alembic and PostgreSQL were not run, so every finding is traced from the code.
- The `orders` and `customers` definitions, the SQL migration runner, any Alembic `env.py` and `shop/migrations/0005_initial` are not in the change.
- C3, C4 and C5 got no blind verification, because the lite tier verifies only Critical and High.

Most valuable fixes first:
1. Correct the dependency name in 0007, and add `manage.py migrate --plan` to CI.
2. Wrap the `CONCURRENTLY` statements in `autocommit_block()` with `IF [NOT] EXISTS`.
3. Split `0002_orders.sql` into one statement kind per file, with down scripts or a one-way marker.
4. Replace the per-row loop with one `.update()` or batches.
5. Document which runner and transaction mode apply to `db/migrations`.

Next steps:
- `/curmudgeon:review fix` to fix every finding.
- `/curmudgeon:fix patch [id]` to fix only one.