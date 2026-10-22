@echo off
REM Starts the AI voice agent on http://127.0.0.1:8100 (needed for payment-reminder test calls).
REM First time: see "Laptop demo (Windows, no NVIDIA card)" in voice_agent\README.md
cd /d "%~dp0.."
if not exist voice_agent\.env (
  echo voice_agent\.env is missing - copy voice_agent\.env.example and set VOICE_AGENT_SECRET
  exit /b 1
)
REM Use the voice agent's own virtual environment (it has torch and the speech models).
set "PY=python"
if exist voice_agent\.venv\Scripts\python.exe set "PY=voice_agent\.venv\Scripts\python.exe"
"%PY%" -m voice_agent.server
