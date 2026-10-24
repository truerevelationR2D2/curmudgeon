-- add order tracking
ALTER TABLE orders ADD COLUMN tracking_code text;

CREATE INDEX CONCURRENTLY orders_customer_idx ON orders (customer_id);

ALTER TABLE orders ADD CONSTRAINT orders_customer_fk FOREIGN KEY (customer_id) REFERENCES customers (id) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT orders_customer_fk;
