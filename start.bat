@echo off
title LoL Scouting Replays Kit
setlocal

echo ============================================
echo  LoL Scouting Replays Kit  --  Local Server
echo ============================================
echo.

:: ── Locate Python ────────────────────────────────────────────────────────────
:: Try "python" first, then "py" (Windows Python Launcher)
set PYTHON=
python --version >nul 2>&1
if not errorlevel 1 set PYTHON=python

if "%PYTHON%"=="" (
    py --version >nul 2>&1
    if not errorlevel 1 set PYTHON=py
)

if "%PYTHON%"=="" (
    echo.
    echo  ERROR: Python was not found on this machine.
    echo.
    echo  To fix this:
    echo    1. Go to https://www.python.org/downloads/
    echo    2. Download Python 3.9 or newer
    echo    3. Run the installer
    echo    4. IMPORTANT: tick "Add Python to PATH" before clicking Install
    echo    5. Close this window and double-click start.bat again
    echo.
    pause
    exit /b 1
)

:: ── Install / upgrade dependencies ───────────────────────────────────────────
echo Installing dependencies ...
%PYTHON% -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo  Server running at http://localhost:8000
echo  Press Ctrl+C to stop.
echo.

%PYTHON% -m uvicorn server:app --port 8000

pause
