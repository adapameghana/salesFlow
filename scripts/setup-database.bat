@echo off
REM Creates the whatsapp_orders database, tables and demo master data.
REM Asks for the password of the PostgreSQL "postgres" superuser, then the wa_app password
REM (default wa_app_password, as set in database\01_create_database.sql).
setlocal
cd /d "%~dp0.."
set PSQL=psql
where psql >nul 2>nul || set "PSQL=C:\Program Files\PostgreSQL\17\bin\psql.exe"

echo === Step 1/3: create role and database (enter the postgres superuser password) ===
"%PSQL%" -U postgres -h localhost -v ON_ERROR_STOP=1 -f database\01_create_database.sql || goto :fail

echo === Step 2/3 and 3/3: tables and seed data (enter the wa_app password) ===
"%PSQL%" -U wa_app -h localhost -d whatsapp_orders -v ON_ERROR_STOP=1 -f database\02_schema.sql -f database\03_seed_data.sql || goto :fail

echo.
echo Database ready. Demo users: admin, supervisor, operator, pharmacy, surgical, equipment, dispatch
echo Password for all demo users: Demo@123
exit /b 0

:fail
echo.
echo Database setup failed - see the error above.
exit /b 1
