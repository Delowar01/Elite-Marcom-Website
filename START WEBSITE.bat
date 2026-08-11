@echo off
rem Elite Marcom website - start the local server (reuses the existing environment)
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Environment not found. Run "INSTALL DEPENDENCIES.bat" once first.
  pause
  exit /b 1
)

echo Starting Elite Marcom website at http://127.0.0.1:8847/
start "" http://127.0.0.1:8847/
".venv\Scripts\python.exe" -m uvicorn server.main:app --host 127.0.0.1 --port 8847
pause
