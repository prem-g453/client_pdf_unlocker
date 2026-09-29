#!/usr/bin/env bash

# Client PDF Unlocker Launcher for macOS / Linux
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "================================================================"
echo "               CLIENT PDF UNLOCKER - LAUNCHER"
echo "================================================================"
echo ""

# Check python
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
else
    echo "[ERROR] Python 3 is required. Please install Python 3.11+."
    exit 1
fi

# Set up local virtual environment
if [ ! -d ".venv" ]; then
    echo "[*] Initializing local virtual environment..."
    $PYTHON_CMD -m venv .venv || true
fi

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run launcher
python run.py
