#!/usr/bin/env bash
set -e

echo "============================================"
echo " LoL Map Replay  —  Local Server"
echo "============================================"
echo

# Prefer python3, fall back to python
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Install Python 3.9+ from https://python.org"
    exit 1
fi

echo "Installing dependencies ..."
$PYTHON -m pip install -r requirements.txt --quiet

echo
echo "Starting server on http://localhost:8000"
echo "Press Ctrl+C to stop."
echo

$PYTHON -m uvicorn server:app --port 8000
