#!/usr/bin/env bash
set -e

# Resolve project root whether executed from package root or launchers/macos/
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    PROJECT_ROOT="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/../../pyproject.toml" ]; then
    PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi
cd "$PROJECT_ROOT"

# Determine executable binary
EXEC_BIN=""
if [ -f "$PROJECT_ROOT/bin/rachel-proxy/rachel-proxy" ]; then
    EXEC_BIN="$PROJECT_ROOT/bin/rachel-proxy/rachel-proxy"
elif [ -f "$PROJECT_ROOT/bin/rachel-proxy" ]; then
    EXEC_BIN="$PROJECT_ROOT/bin/rachel-proxy"
elif [ -f "$PROJECT_ROOT/rachel-proxy" ]; then
    EXEC_BIN="$PROJECT_ROOT/rachel-proxy"
elif [ -f "$PROJECT_ROOT/python/bin/python3" ]; then
    EXEC_BIN="$PROJECT_ROOT/python/bin/python3 -m uvicorn rachel.proxy:app --host 0.0.0.0 --port 8000"
elif [ -f "$PROJECT_ROOT/venv/bin/python" ]; then
    EXEC_BIN="$PROJECT_ROOT/venv/bin/python -m uvicorn rachel.proxy:app --host 0.0.0.0 --port 8000"
fi

if [ -z "$EXEC_BIN" ]; then
    echo "Error: RACHEL standalone executable not found."
    echo "Please ensure the release package was extracted completely."
    read -p "Press Enter to exit..."
    exit 1
fi

echo "Starting RACHEL Proxy..."
$EXEC_BIN &
SERVER_PID=$!

cleanup() {
    echo "Shutting down RACHEL Proxy (PID: $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

sleep 2
open http://localhost:8000 &

wait "$SERVER_PID"


