-- =====================================================================
-- 03_seed_data.sql  -  master data + demo users
-- Run after 02_schema.sql:
--
--   psql -U wa_app -h localhost -d whatsapp_orders -f database/03_seed_data.sql
--
-- All demo users have the password:  Demo@123
-- =====================================================================

BEGIN;

INSERT INTO departments (department_name, description) VALUES
    ('Pharmacy',            'Tablets, syrups, injections and other medicines'),
    ('Surgical Supplies',   'Gloves, masks, syringes, bandages and consumables'),
    ('Medical Equipment',   'Devices such as BP monitors, glucometers, oximeters'),
    ('Dispatch & Logistics','Urgent deliveries and transport coordination');

-- password for every user below: Demo@123 (bcrypt)
INSERT INTO users (display_name, username, password_hash, role, department_id) VALUES
    ('System Admin',        'admin',      '$2b$10$VVRW9sLTR6YolKyUV2x9AOTbkbCQwhcBJMAMK9qn/mL2bXuOgakbW', 'admin',      NULL),
    ('Sales Supervisor',    'supervisor', '$2b$10$VVRW9sLTR6YolKyUV2x9AOTbkbCQwhcBJMAMK9qn/mL2bXuOgakbW', 'supervisor', NULL),
    ('Order Operator',      'operator',   '$2b$10$VVRW9sLTR6YolKyUV2x9AOTbkbCQwhcBJMAMK9qn/mL2bXuOgakbW', 'operator',   NULL),
    ('Pharmacy Desk',       'pharmacy',   '$2b$10$VVRW9sLTR6YolKyUV2x9AOTbkbCQwhcBJMAMK9qn/mL2bXuOgakbW', 'department',
        (SELECT id FROM departments WHERE department_name = 'Pharmacy')),
    ('Surgical Desk',       'surgical',   '$2b$10$VVRW9sLTR6YolKyUV2x9AOTbkbCQwhcBJMAMK9qn/mL2bXuOgakbW', 'department',
        (SELECT id FROM departments WHERE department_name = 'Surgical Supplies')),
    ('Equipment Desk',      'equipment',  '$2b$10$VVRW9sLTR6YolKyUV2x9AOTbkbCQwhcBJMAMK9qn/mL2bXuOgakbW', 'department',
        (SELECT id FROM departments WHERE department_name = 'Medical Equipment')),
    ('Dispatch Desk',       'dispatch',   '$2b$10$VVRW9sLTR6YolKyUV2x9AOTbkbCQwhcBJMAMK9qn/mL2bXuOgakbW', 'department',
        (SELECT id FROM departments WHERE department_name = 'Dispatch & Logistics'));

INSERT INTO products (product_code, product_name, aliases, unit, department_id) VALUES
    ('PH-PCM500', 'Paracetamol 500mg Tablets', 'paracetamol,pcm,dolo,crocin',            'strip',
        (SELECT id FROM departments WHERE department_name = 'Pharmacy')),
    ('PH-AMX250', 'Amoxicillin 250mg Capsules', 'amoxicillin,amoxy,mox',                 'strip',
        (SELECT id FROM departments WHERE department_name = 'Pharmacy')),
    ('PH-ORS',    'ORS Sachets',                'ors,electral,oral rehydration',         'box',
        (SELECT id FROM departments WHERE department_name = 'Pharmacy')),
    ('PH-CSY100', 'Cough Syrup 100ml',          'cough syrup,syrup,benadryl',            'bottle',
        (SELECT id FROM departments WHERE department_name = 'Pharmacy')),
    ('PH-INS10',  'Insulin Vial 10ml',          'insulin',                               'vial',
        (SELECT id FROM departments WHERE department_name = 'Pharmacy')),
    ('SS-GLV-M',  'Surgical Gloves (Medium)',   'gloves,surgical gloves,latex gloves',   'box',
        (SELECT id FROM departments WHERE department_name = 'Surgical Supplies')),
    ('SS-N95',    'N95 Face Masks',             'n95 masks,n95 mask,n95,face masks,face mask,masks,mask',              'box',
        (SELECT id FROM departments WHERE department_name = 'Surgical Supplies')),
    ('SS-SYR5',   'Disposable Syringes 5ml',    'syringe,syringes,5ml syringe',          'box',
        (SELECT id FROM departments WHERE department_name = 'Surgical Supplies')),
    ('SS-BND',    'Cotton Bandage Rolls',       'bandage,bandages,cotton roll,gauze',    'pack',
        (SELECT id FROM departments WHERE department_name = 'Surgical Supplies')),
    ('ME-BPM',    'Digital BP Monitor',         'bp monitor,bp machine,blood pressure monitor', 'unit',
        (SELECT id FROM departments WHERE department_name = 'Medical Equipment')),
    ('ME-GLU',    'Glucometer Kit',             'glucometer,sugar machine,glucose meter', 'unit',
        (SELECT id FROM departments WHERE department_name = 'Medical Equipment')),
    ('ME-GSTR',   'Glucometer Test Strips (50)','test strips,glucometer strips,sugar strips',  'box',
        (SELECT id FROM departments WHERE department_name = 'Medical Equipment')),
    ('ME-OXI',    'Pulse Oximeter',             'oximeter,pulse oximeter,spo2',          'unit',
        (SELECT id FROM departments WHERE department_name = 'Medical Equipment')),
    ('ME-THERM',  'Digital Thermometer',        'thermometer',                           'unit',
        (SELECT id FROM departments WHERE department_name = 'Medical Equipment'));

INSERT INTO branches (branch_name, address) VALUES
    ('Vijayawada',    'Vijayawada branch, MG Road, Vijayawada'),
    ('Guntur',        'Guntur branch, Brodipet, Guntur'),
    ('Hyderabad',     'Hyderabad branch, Ameerpet, Hyderabad'),
    ('Visakhapatnam', 'Visakhapatnam branch, Dwaraka Nagar, Visakhapatnam'),
    ('Nellore',       'Nellore branch, Trunk Road, Nellore'),
    ('Tirupati',      'Tirupati branch, Tilak Road, Tirupati'),
    ('Kurnool',       'Kurnool branch, Park Road, Kurnool');

-- Rules are evaluated by priority (lowest first); first match wins.
-- If no rule matches, the department of the first catalogue product is used.
INSERT INTO routing_rules (rule_name, match_field, match_value, target_department_id, priority) VALUES
    ('Emergency orders go to Dispatch', 'keyword',  'emergency',
        (SELECT id FROM departments WHERE department_name = 'Dispatch & Logistics'), 10),
    ('Insulin is cold-chain (Pharmacy)', 'product', 'PH-INS10',
        (SELECT id FROM departments WHERE department_name = 'Pharmacy'), 20),
    ('Device repairs to Equipment',     'keyword',  'repair',
        (SELECT id FROM departments WHERE department_name = 'Medical Equipment'), 30),
    ('Masks to Surgical Supplies',      'product',  'SS-N95',
        (SELECT id FROM departments WHERE department_name = 'Surgical Supplies'), 50);

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
