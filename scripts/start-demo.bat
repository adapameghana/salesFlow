@echo off
REM Opens the backend and the frontend in two windows. Ollama runs as its own service if installed.
start "Order Desk - Backend" cmd /k "%~dp0start-backend.bat"
timeout /t 3 /nobreak >nul
start "Order Desk - Frontend" cmd /k "%~dp0start-frontend.bat"
echo Backend:  http://127.0.0.1:8000/docs
echo Frontend: http://localhost:4300   (login: operator / Demo@123)
