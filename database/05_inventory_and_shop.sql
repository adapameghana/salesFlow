-- =====================================================================
-- 05_inventory_and_shop.sql  -  UPGRADE for a database created before stock
-- and the online shop were added. Safe to run more than once.
-- (A fresh install from 01-03 already includes all of this.)
--
--   psql -U wa_app -h localhost -d whatsapp_orders -f database/05_inventory_and_shop.sql
--
-- Orders confirmed before this upgrade do not hold stock; only orders
-- confirmed afterwards reserve and deduct it.
-- =====================================================================

BEGIN;

ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS stock_on_hand
    NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (stock_on_hand >= 0);
ALTER TABLE products ADD COLUMN IF NOT EXISTS stock_reserved
    NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (stock_reserved >= 0);
ALTER TABLE products ADD COLUMN IF NOT EXISTS reorder_level
    NUMERIC(12, 2) NOT NULL DEFAULT 10;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS stock_state
    VARCHAR(10) NOT NULL DEFAULT 'none' CHECK (stock_state IN ('none', 'reserved', 'shipped'));

CREATE TABLE IF NOT EXISTS stock_movements (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    movement_type   VARCHAR(10) NOT NULL
                    CHECK (movement_type IN ('in', 'adjust', 'reserve', 'release', 'dispatch')),
    quantity        NUMERIC(12, 2) NOT NULL,
    on_hand_after   NUMERIC(12, 2) NOT NULL,
    reserved_after  NUMERIC(12, 2) NOT NULL,
    order_id        INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    user_id         INTEGER REFERENCES users(id),
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_stock_movements_product ON stock_movements(product_id, created_at);

-- Loaded only the first time (while there are no stock movements yet).
-- Opening stock (on hand, low-stock level, shop description).
-- Insulin and thermometers start LOW and the oximeter starts OUT, so the demo shows every case.
UPDATE products p
   SET stock_on_hand = v.on_hand, stock_reserved = 0, reorder_level = v.reorder_level, description = v.description
  FROM (VALUES
    ('PH-PCM500', 200, 30, 'Fever and pain relief. Strip of 10 tablets.'),
    ('PH-AMX250', 120, 20, 'Antibiotic capsules. Strip of 10. Prescription required.'),
    ('PH-ORS',     60, 15, 'Oral rehydration salts. Box of 25 sachets.'),
    ('PH-CSY100',  40, 10, 'Cough syrup, 100 ml bottle.'),
    ('PH-INS10',    8, 10, 'Insulin vial, 10 ml. Cold-chain delivery.'),
    ('SS-GLV-M',   50, 10, 'Latex examination gloves, medium. Box of 100.'),
    ('SS-N95',     25, 10, 'N95 respirator masks. Box of 20.'),
    ('SS-SYR5',    80, 15, 'Sterile single-use 5 ml syringes. Box of 100.'),
    ('SS-BND',     30, 10, 'Cotton bandage rolls. Pack of 12.'),
    ('ME-BPM',      8,  3, 'Automatic upper-arm blood pressure monitor.'),
    ('ME-GLU',      6,  3, 'Blood glucose meter with lancets.'),
    ('ME-GSTR',    40, 10, 'Test strips for the glucometer kit. Box of 50.'),
    ('ME-OXI',      0,  3, 'Fingertip pulse oximeter (SpO2 and pulse rate).'),
    ('ME-THERM',    3,  5, 'Digital thermometer with beep alert.')
  ) AS v(code, on_hand, reorder_level, description)
 WHERE p.product_code = v.code
   AND NOT EXISTS (SELECT 1 FROM stock_movements);

INSERT INTO stock_movements (product_id, movement_type, quantity, on_hand_after, reserved_after, reason)
SELECT id, 'in', stock_on_hand, stock_on_hand, 0, 'Opening stock'
  FROM products
 WHERE stock_on_hand > 0
   AND NOT EXISTS (SELECT 1 FROM stock_movements);

-- If this script was run as postgres, the new table belongs to postgres and the app
-- (which connects as wa_app) gets "permission denied for table stock_movements".
-- Hand it to wa_app; the SERIAL sequence follows the table.
ALTER TABLE stock_movements OWNER TO wa_app;

COMMIT;
