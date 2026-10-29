```json
[
  {
    "file": "alembic/versions/3b1f_add_refunds.py",
    "line": 13,
    "summary": "CREATE INDEX CONCURRENTLY is run with op.execute inside Alembic's default transactional DDL, and PostgreSQL rejects it inside a transaction block.",
    "failure_scenario": "`alembic upgrade head` on PostgreSQL fails with 'CREATE INDEX CONCURRENTLY cannot run inside a transaction block'. The migration aborts and the revision is not applied. It needs `with op.get_context().autocommit_block():`, or the CONCURRENTLY keyword removed."
  },
  {
    "file": "alembic/versions/3b1f_add_refunds.py",
    "line": 18,
    "summary": "The downgrade runs DROP INDEX CONCURRENTLY in the same transaction, which PostgreSQL rejects. The statement order also leaves a half-done downgrade.",
    "failure_scenario": "`alembic downgrade 2a0e` fails on the DROP INDEX CONCURRENTLY line with the same transaction-block error, so the rollback cannot complete. The `reason` column drop runs first. If the migration were not transactional, this would leave a partly rolled-back schema. Wrap the drop in autocommit_block, or use a plain DROP INDEX."
  },
  {
    "file": "shop/migrations/0007_backfill.py",
    "line": 13,
    "summary": "The dependency names '0006_product_slug', but the previous migration file is 0006_safe.py, so the migration graph is broken.",
    "failure_scenario": "`manage.py migrate` raises NodeNotFoundError ('dependencies reference nonexistent parent node (shop, 0006_product_slug)'). No migrations in the app can run. The dependency should be ('shop', '0006_safe')."
  },
  {
    "file": "db/migrations/0001_safe.sql",
    "line": 9,
    "summary": "CREATE INDEX CONCURRENTLY sits in a multi-statement file, which most SQL migration runners execute as one transaction (psql -1, Flyway, golang-migrate multi-statement), and PostgreSQL rejects it there.",
    "failure_scenario": "The runner wraps the file in a transaction, or sends it as one multi-statement simple query. The index statement errors, and either the whole migration rolls back or the index is never built. It needs its own non-transactional migration file or runner directive. The same applies to 0002_orders.sql line 4."
  },
  {
    "file": "db/migrations/0001_safe.sql",
    "line": 12,
    "summary": "ADD CONSTRAINT ... NOT VALID is followed by VALIDATE CONSTRAINT in the same file. Run as one transaction, the ACCESS EXCLUSIVE lock from the ADD is held through the validation scan.",
    "failure_scenario": "On a large orders table, the migration holds an ACCESS EXCLUSIVE lock for the whole validation scan. That blocks all reads and writes, which is the outage NOT VALID is meant to avoid. VALIDATE should go in a separate migration or transaction. The validation will also fail outright if any existing row has total <= 0."
  },
  {
    "file": "db/migrations/0002_orders.sql",
    "line": 7,
    "summary": "The foreign key is added NOT VALID and validated in the same script. Run as one transaction, it keeps a SHARE ROW EXCLUSIVE lock on both orders and customers during validation.",
    "failure_scenario": "Writes to orders and customers block while validation scans orders. If any order has an orphaned customer_id, the validation fails and rolls back the whole migration, including the tracking_code column and the index. Split it into two migrations."
  },
  {
    "file": "db/migrations/0001_safe.sql",
    "line": 14,
    "summary": "The migration alters, indexes and comments on the `orders` table and its `note` column, but nothing in this tree creates `orders` or `orders.note`.",
    "failure_scenario": "On a fresh database, 0001 creates only `invoices`. The following `CREATE INDEX ... ON orders` and `ALTER TABLE orders` then fail with 'relation orders does not exist'. The COMMENT ON COLUMN orders.note also fails if that column does not exist. The migrations only work if another system created the table first."
  },
  {
    "file": "shop/migrations/0007_backfill.py",
    "line": 7,
    "summary": "The backfill loads every product and calls save() one at a time (N+1 writes), and it ignores the unique and NULL cases.",
    "failure_scenario": "On a large shop_product table, this is one UPDATE per row inside a single migration transaction, which is slow and holds locks the whole time. A single `Product.objects.filter(slug='').update(slug=Cast('pk', CharField()))` would do the same job. Because save() is called without update_fields, it can also overwrite concurrent changes to other columns."
  },
  {
    "file": "shop/migrations/0006_safe.py",
    "line": 12,
    "summary": "The RunSQL sets slug = '' for NULL rows and has only a no-op reverse, so the data change is irreversible. It also sits next to a RunPython whose forward function does nothing.",
    "failure_scenario": "Rolling back with `migrate shop 0005` leaves every previously NULL slug as '' with no way to restore the original NULLs. A later unique constraint on slug would then collide on the empty strings. The same irreversibility applies to the `active` backfill in 0007 line 15."
  },
  {
    "file": "alembic/versions/2a0e_safe.py",
    "line": 15,
    "summary": "The refunds table is created with no foreign key to orders, and its only index is on the primary key column `id`, which is already indexed.",
    "failure_scenario": "`refunds_created_idx ON refunds (id)` duplicates the primary key index, so it costs write overhead for nothing. The name suggests a created_at column that does not exist. Orphaned `order_id` rows are also allowed, since no FK constraint ties them to orders."
  }
]
```