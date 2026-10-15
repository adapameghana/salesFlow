@echo off
REM Creates a compressed backup in the backups folder:  backups\whatsapp_orders_YYYYMMDD_HHMM.dump
REM Copy the backups folder to a separate drive or approved network location.
setlocal
cd /d "%~dp0.."
set PG_DUMP=pg_dump
where pg_dump >nul 2>nul || set "PG_DUMP=C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set STAMP=%%i
if not exist backups mkdir backups
"%PG_DUMP%" -U wa_app -h localhost -d whatsapp_orders -F c -f "backups\whatsapp_orders_%STAMP%.dump" || goto :fail
echo Backup written to backups\whatsapp_orders_%STAMP%.dump
exit /b 0
:fail
echo Backup failed.
exit /b 1
