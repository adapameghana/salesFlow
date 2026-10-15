-- =====================================================================
-- 01_create_database.sql
-- Run as the PostgreSQL superuser (postgres), connected to the default
-- "postgres" database:
--
--   psql -U postgres -h localhost -f database/01_create_database.sql
--
-- Change the password below, and put the same value in backend/.env
-- (DATABASE_URL).
-- =====================================================================

CREATE ROLE wa_app WITH LOGIN PASSWORD 'wa_app_password';

CREATE DATABASE whatsapp_orders
    WITH OWNER = wa_app
         ENCODING = 'UTF8'
         TEMPLATE = template0;

GRANT ALL PRIVILEGES ON DATABASE whatsapp_orders TO wa_app;
