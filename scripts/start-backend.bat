@echo off
REM Starts the FastAPI backend on http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)
cd /d "%~dp0..\backend"
if not exist .env copy .env.example .env >nul
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
