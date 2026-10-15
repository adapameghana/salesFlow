@echo off
REM Restores a backup made by backup.bat.  Usage:  scripts\restore.bat backups\whatsapp_orders_20261012_1800.dump
REM WARNING: replaces the current contents of the whatsapp_orders database. Stop the backend first.
setlocal
cd /d "%~dp0.."
if "%~1"=="" (
  echo Usage: restore.bat path\to\backup.dump
  exit /b 1
)
set PG_RESTORE=pg_restore
where pg_restore >nul 2>nul || set "PG_RESTORE=C:\Program Files\PostgreSQL\17\bin\pg_restore.exe"
choice /m "Replace all data in whatsapp_orders with %~1"
if errorlevel 2 exit /b 1
"%PG_RESTORE%" -U wa_app -h localhost -d whatsapp_orders --clean --if-exists --no-owner "%~1" || goto :fail
echo Restore complete.
exit /b 0
:fail
echo Restore failed.
exit /b 1
