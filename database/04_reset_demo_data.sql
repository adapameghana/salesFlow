-- =====================================================================
-- 04_reset_demo_data.sql  -  OPTIONAL: clear all orders and messages
-- Keeps users, departments, products, branches and routing rules,
-- and puts every product back to its opening stock.
-- Use it to start the demo with an empty dashboard:
--
--   psql -U wa_app -h localhost -d whatsapp_orders -f database/04_reset_demo_data.sql
-- =====================================================================

BEGIN;

TRUNCATE TABLE order_payments, stock_movements, order_notes, order_status_history, order_items, messages, orders, audit_log
    RESTART IDENTITY CASCADE;

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
 WHERE p.product_code = v.code;

INSERT INTO stock_movements (product_id, movement_type, quantity, on_hand_after, reserved_after, reason)
SELECT id, 'in', stock_on_hand, stock_on_hand, 0, 'Opening stock'
  FROM products
 WHERE stock_on_hand > 0;

COMMIT;
