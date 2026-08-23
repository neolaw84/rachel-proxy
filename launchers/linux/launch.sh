#!/usr/bin/env bash
set -e

# Resolve project root whether executed from package root or launchers/linux/
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    PROJECT_ROOT="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/../../pyproject.toml" ]; then
    PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi
cd "$PROJECT_ROOT"

# Ensure Python 3.12+ or fallback python3 is available
PYTHON_CMD=""
for cmd in python3.12 python3.13 python3 python; do
    if command -v "$cmd" > /dev/null 2>&1; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "Error: Python 3 is not installed or not in PATH."
    echo "Please install Python 3.12 or newer: https://www.python.org/downloads/"
    exit 1
fi

# Ensure virtual environment exists and is bootstrapped
if [ ! -d "venv" ] || [ ! -f "venv/bin/python" ]; then
    echo "First-time setup: Creating virtual environment in ./venv using $PYTHON_CMD..."
    "$PYTHON_CMD" -m venv venv
    echo "Installing RACHEL proxy and dependencies..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -e .
fi

export PYTHONPATH="src:${PYTHONPATH:-}"

echo "Starting RACHEL Proxy..."
./venv/bin/python -m uvicorn rachel.proxy:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

cleanup() {
    echo "Shutting down RACHEL Proxy (PID: $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

sleep 2
if command -v xdg-open > /dev/null 2>&1; then
    xdg-open http://localhost:8000 &
fi

wait "$SERVER_PID"
