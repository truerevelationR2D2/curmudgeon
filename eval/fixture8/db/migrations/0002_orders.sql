-- add order tracking
ALTER TABLE orders ADD COLUMN tracking_code text NOT NULL;

CREATE INDEX orders_customer_idx ON orders (customer_id);

ALTER TABLE orders ADD CONSTRAINT orders_customer_fk FOREIGN KEY (customer_id) REFERENCES customers (id);

ALTER TABLE orders DROP COLUMN legacy_ref;
