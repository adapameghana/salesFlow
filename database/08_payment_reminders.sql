-- =====================================================================
-- 08_payment_reminders.sql  -  AI voice-call payment reminders.
-- Safe to run more than once. (A fresh install from 01-03 already includes this.)
--
--   psql -U wa_app -h localhost -d whatsapp_orders -f database/08_payment_reminders.sql
-- =====================================================================

BEGIN;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS preferred_language
    VARCHAR(5) NOT NULL DEFAULT 'en' CHECK (preferred_language IN ('en', 'hi', 'te', 'ta'));
ALTER TABLE orders ADD COLUMN IF NOT EXISTS reminders_enabled
    BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_promised_date DATE;

-- One row per reminder call (real phone call or browser test call).
CREATE TABLE IF NOT EXISTS payment_reminder_calls (
    id                  SERIAL PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    attempt_no          INTEGER NOT NULL DEFAULT 0,          -- 0 for browser test calls
    phone               VARCHAR(20),
    language            VARCHAR(5) NOT NULL,
    amount_due_at_call  NUMERIC(12, 2),                      -- balance when the call was placed
    provider            VARCHAR(20) NOT NULL CHECK (provider IN ('asterisk', 'browser')),
    status              VARCHAR(20) NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued', 'dialing', 'answered', 'no_answer', 'busy', 'failed', 'test')),
    intent              VARCHAR(30)
                        CHECK (intent IN ('paid_claimed', 'will_pay', 'ask_details', 'callback', 'dispute',
                                          'wrong_number', 'not_interested', 'no_response', 'other')),
    promised_date       DATE,
    transcript          JSONB,                               -- [{speaker, text, ts}]
    summary             TEXT,
    recording_path      TEXT,
    duration_seconds    INTEGER,
    error               TEXT,
    needs_followup      BOOLEAN NOT NULL DEFAULT FALSE,
    handled_by          INTEGER REFERENCES users(id),
    handled_at          TIMESTAMPTZ,
    handled_note        TEXT,
    started_by          INTEGER REFERENCES users(id),        -- NULL = scheduler
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_reminder_calls_order ON payment_reminder_calls(order_id, created_at);
CREATE INDEX IF NOT EXISTS ix_reminder_calls_followup ON payment_reminder_calls(needs_followup)
    WHERE needs_followup;

-- If this script was run as postgres, hand the new table to the app user.
ALTER TABLE payment_reminder_calls OWNER TO wa_app;

COMMIT;
