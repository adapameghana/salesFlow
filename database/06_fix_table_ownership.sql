-- =====================================================================
-- 06_fix_table_ownership.sql  -  REPAIR. Gives every table in the app's
-- schema back to wa_app. Use it if the backend fails with
-- "permission denied for table ..." (for example after running a script
-- as postgres). Safe to run more than once.
--
--   psql -U postgres -h localhost -d whatsapp_orders -f database/06_fix_table_ownership.sql
--
-- Must be run as postgres (or another superuser).
-- =====================================================================

DO $$
DECLARE
    t RECORD;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables
              WHERE schemaname = 'public' AND tableowner <> 'wa_app'
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO wa_app', t.tablename);
        RAISE NOTICE 'Table % now owned by wa_app', t.tablename;
    END LOOP;
END $$;

-- Check: every row should show wa_app.
SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
