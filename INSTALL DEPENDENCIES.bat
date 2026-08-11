@echo off
rem Elite Marcom website - one-time dependency installation (Windows)
setlocal
cd /d "%~dp0"

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD where python3 >nul 2>nul && set "PY_CMD=python3"
if not defined PY_CMD (
  echo Python 3.11+ is required. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Using Python: %PY_CMD%
if not exist ".venv" (
  %PY_CMD% -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)
echo.
echo Dependencies installed. Start the website with "START WEBSITE.bat"
pause
