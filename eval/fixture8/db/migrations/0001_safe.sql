-- correct migrations that only look risky
CREATE TABLE invoices (
  id bigserial PRIMARY KEY,
  total numeric NOT NULL,
  note text
);
CREATE INDEX invoices_total_idx ON invoices (total);
ALTER TABLE invoices ADD COLUMN status text NOT NULL DEFAULT 'draft';
CREATE INDEX CONCURRENTLY orders_created_idx ON orders (created_at);
ALTER TABLE orders ADD COLUMN gift_note text;
ALTER TABLE orders ADD COLUMN priority int NOT NULL DEFAULT 0;
ALTER TABLE orders ADD CONSTRAINT orders_total_positive CHECK (total > 0) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT orders_total_positive;
COMMENT ON COLUMN orders.note IS 'NOT NULL in a comment string; CREATE INDEX x ON y';
