@echo off
title LoL Map Replay

echo ============================================
echo  LoL Map Replay  —  Local Server
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

:: Install / upgrade dependencies
echo Installing dependencies ...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Starting server on http://localhost:8000
echo Press Ctrl+C to stop.
echo.

python -m uvicorn server:app --port 8000

pause
