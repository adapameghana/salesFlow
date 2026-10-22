-- =====================================================================
-- 07_payments.sql  -  UPGRADE for a database created before product prices
-- and payment tracking were added. Safe to run more than once.
-- (A fresh install from 01-03 already includes all of this.)
--
--   psql -U wa_app -h localhost -d whatsapp_orders -f database/07_payments.sql
--
-- Existing orders start as Unpaid with no amount set. Products that have no
-- price yet get the demo sample prices.
-- =====================================================================

BEGIN;

ALTER TABLE products ADD COLUMN IF NOT EXISTS unit_price
    NUMERIC(12, 2) CHECK (unit_price >= 0);
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS unit_price
    NUMERIC(12, 2) CHECK (unit_price >= 0);

UPDATE products p
   SET unit_price = v.price
  FROM (VALUES
    ('PH-PCM500',    25.00),
    ('PH-AMX250',    85.00),
    ('PH-ORS',      450.00),
    ('PH-CSY100',   110.00),
    ('PH-INS10',    520.00),
    ('SS-GLV-M',    650.00),
    ('SS-N95',      900.00),
    ('SS-SYR5',     550.00),
    ('SS-BND',      240.00),
    ('ME-BPM',     1850.00),
    ('ME-GLU',     1200.00),
    ('ME-GSTR',     750.00),
    ('ME-OXI',     1500.00),
    ('ME-THERM',    250.00)
  ) AS v(code, price)
 WHERE p.product_code = v.code
   AND p.unit_price IS NULL;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS amount_due
    NUMERIC(12, 2) CHECK (amount_due >= 0);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS amount_paid
    NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (amount_paid >= 0);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status
    VARCHAR(20) NOT NULL DEFAULT 'Unpaid'
    CHECK (payment_status IN ('Unpaid', 'Partially Paid', 'Paid'));

CREATE INDEX IF NOT EXISTS ix_orders_payment_status ON orders(payment_status);

CREATE TABLE IF NOT EXISTS order_payments (
    id           SERIAL PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    amount       NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    method       VARCHAR(20) NOT NULL
                 CHECK (method IN ('cash', 'upi', 'bank_transfer', 'card', 'cheque', 'other')),
    reference    VARCHAR(100),
    paid_on      DATE NOT NULL,
    note         TEXT,
    recorded_by  INTEGER REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_order_payments_order ON order_payments(order_id);

-- If this script was run as postgres, hand the new table to the app user.
ALTER TABLE order_payments OWNER TO wa_app;

COMMIT;
