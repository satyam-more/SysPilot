#!/usr/bin/env bash
#
# TrailBack launcher.
# Double-click this (or run ./launch.sh) to start the desktop app.
#
# It will:
#   1. Ensure the Python virtualenv exists and deps are installed.
#   2. Build the React frontend if it hasn't been built yet.
#   3. Launch the desktop window.

set -e

# Resolve the directory this script lives in, so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PY="$SCRIPT_DIR/.venv/bin/python"
VENV_PIP="$SCRIPT_DIR/.venv/bin/pip"

echo "=== TrailBack launcher ==="

# 1. Virtualenv check -------------------------------------------------------
if [ ! -x "$VENV_PY" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    "$VENV_PIP" install --upgrade pip
    "$VENV_PIP" install -r requirements.txt
fi

# 2. Frontend build check ---------------------------------------------------
if [ ! -f "$SCRIPT_DIR/frontend/dist/index.html" ]; then
    echo "Building frontend (first run)..."
    if command -v npm >/dev/null 2>&1; then
        (cd frontend && npm install && npm run build)
    else
        echo "ERROR: npm is not installed. Install Node.js, then run this again." >&2
        read -rp "Press Enter to close..."
        exit 1
    fi
fi

# 3. Launch the desktop app -------------------------------------------------
echo "Starting TrailBack..."
exec "$VENV_PY" desktop.py
