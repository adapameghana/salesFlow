@echo off
REM Starts the Angular dashboard on http://localhost:4300 (calls to /api are proxied to the backend)
cd /d "%~dp0..\frontend"
if not exist node_modules call npm install
call npx ng serve --port 4300 --open
