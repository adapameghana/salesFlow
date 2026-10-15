-- =====================================================================
-- 02_schema.sql  -  tables, constraints and indexes
-- Run connected to the whatsapp_orders database as wa_app:
--
--   psql -U wa_app -h localhost -d whatsapp_orders -f database/02_schema.sql
-- =====================================================================

BEGIN;

CREATE TABLE departments (
    id               SERIAL PRIMARY KEY,
    department_name  VARCHAR(100) NOT NULL UNIQUE,
    description      TEXT,
    active           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE users (
    id             SERIAL PRIMARY KEY,
    display_name   VARCHAR(120) NOT NULL,
    username       VARCHAR(60)  NOT NULL UNIQUE,
    password_hash  VARCHAR(200) NOT NULL,
    role           VARCHAR(20)  NOT NULL
                   CHECK (role IN ('admin', 'supervisor', 'operator', 'department')),
    department_id  INTEGER REFERENCES departments(id),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Product catalogue: used to validate extracted items and to route orders.
CREATE TABLE products (
    id             SERIAL PRIMARY KEY,
    product_code   VARCHAR(30)  NOT NULL UNIQUE,
    product_name   VARCHAR(150) NOT NULL,
    aliases        TEXT,                       -- comma separated alternate names
    unit           VARCHAR(20)  NOT NULL DEFAULT 'box',
    department_id  INTEGER REFERENCES departments(id),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    description    TEXT,                       -- shown on the public shop
    stock_on_hand  NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (stock_on_hand >= 0),
    stock_reserved NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (stock_reserved >= 0),  -- held by confirmed orders
    reorder_level  NUMERIC(12, 2) NOT NULL DEFAULT 10   -- "low stock" when available <= this
);

-- Known delivery locations (branches / customers sites).
CREATE TABLE branches (
    id           SERIAL PRIMARY KEY,
    branch_name  VARCHAR(100) NOT NULL UNIQUE,
    address      TEXT,
    active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE orders (
    id                 SERIAL PRIMARY KEY,
    order_number       VARCHAR(30) NOT NULL UNIQUE,
    customer_name      VARCHAR(150),
    contact_reference  VARCHAR(100),
    delivery_address   TEXT,
    requested_date     DATE,
    status             VARCHAR(30) NOT NULL DEFAULT 'New'
                       CHECK (status IN ('New', 'Needs Review', 'Confirmed', 'Assigned',
                                         'In Progress', 'On Hold', 'Ready / Dispatched',
                                         'Completed', 'Cancelled')),
    department_id      INTEGER REFERENCES departments(id),
    assigned_user_id   INTEGER REFERENCES users(id),
    notes              TEXT,
    extraction_method  VARCHAR(20),            -- manual | rules | ai | shop
    review_flags       JSON,                   -- list of {field, message}
    stock_state        VARCHAR(10) NOT NULL DEFAULT 'none'
                       CHECK (stock_state IN ('none', 'reserved', 'shipped')),
    created_by         INTEGER REFERENCES users(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_orders_status         ON orders(status);
CREATE INDEX ix_orders_department     ON orders(department_id);
CREATE INDEX ix_orders_requested_date ON orders(requested_date);
CREATE INDEX ix_orders_created_at     ON orders(created_at);

CREATE TABLE order_items (
    id            SERIAL PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id    INTEGER REFERENCES products(id),
    product_name  VARCHAR(150) NOT NULL,
    quantity      NUMERIC(12, 2),
    unit          VARCHAR(20),
    item_notes    TEXT
);

CREATE INDEX ix_order_items_order ON order_items(order_id);

CREATE TABLE messages (
    id                   SERIAL PRIMARY KEY,
    source               VARCHAR(20)  NOT NULL DEFAULT 'simulator',  -- simulator | import | whatsapp
    external_message_id  VARCHAR(120),
    sender_reference     VARCHAR(60),
    sender_name          VARCHAR(120),
    message_text         TEXT NOT NULL,
    received_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_state     VARCHAR(20) NOT NULL DEFAULT 'received'
                         CHECK (processing_state IN ('received', 'parsed', 'needs_review',
                                                     'duplicate', 'failed')),
    error_text           TEXT,
    linked_order_id      INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    CONSTRAINT uq_messages_source_external UNIQUE (source, external_message_id)
);

CREATE INDEX ix_messages_received_at ON messages(received_at);

CREATE TABLE order_status_history (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    old_status  VARCHAR(30),
    new_status  VARCHAR(30) NOT NULL,
    changed_by  INTEGER REFERENCES users(id),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    comment     TEXT
);

CREATE INDEX ix_status_history_order ON order_status_history(order_id);

CREATE TABLE order_notes (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(id),
    note        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_order_notes_order ON order_notes(order_id);

-- match_field: product (product code), keyword (text in message/notes),
--              location (delivery address contains value)
CREATE TABLE routing_rules (
    id                    SERIAL PRIMARY KEY,
    rule_name             VARCHAR(120) NOT NULL,
    match_field           VARCHAR(20)  NOT NULL
                          CHECK (match_field IN ('product', 'keyword', 'location')),
    match_value           VARCHAR(150) NOT NULL,
    target_department_id  INTEGER NOT NULL REFERENCES departments(id),
    priority              INTEGER NOT NULL DEFAULT 100,   -- lower runs first
    active                BOOLEAN NOT NULL DEFAULT TRUE
);

-- Every change to stock: in (received), adjust (+/-), reserve / release (orders), dispatch (shipped).
CREATE TABLE stock_movements (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    movement_type   VARCHAR(10) NOT NULL
                    CHECK (movement_type IN ('in', 'adjust', 'reserve', 'release', 'dispatch')),
    quantity        NUMERIC(12, 2) NOT NULL,
    on_hand_after   NUMERIC(12, 2) NOT NULL,
    reserved_after  NUMERIC(12, 2) NOT NULL,
    order_id        INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    user_id         INTEGER REFERENCES users(id),     -- NULL = customer / system
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_stock_movements_product ON stock_movements(product_id, created_at);

CREATE TABLE audit_log (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id),
    action       VARCHAR(60) NOT NULL,
    entity_type  VARCHAR(40) NOT NULL,
    entity_id    INTEGER,
    details      TEXT,
    "timestamp"  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_audit_log_entity ON audit_log(entity_type, entity_id);

COMMIT;
