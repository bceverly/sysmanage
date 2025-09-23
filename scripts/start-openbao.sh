#!/bin/bash
#
# OpenBAO Development Server Start Script
# Starts OpenBAO in development mode for sysmanage integration
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$PROJECT_DIR/.openbao.pid"
LOG_FILE="$PROJECT_DIR/logs/openbao.log"

# Ensure logs directory exists
mkdir -p "$PROJECT_DIR/logs"

# Check if OpenBAO is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "OpenBAO is already running with PID $PID"
        exit 0
    else
        echo "Stale PID file found, removing..."
        rm -f "$PID_FILE"
    fi
fi

# Find OpenBAO binary
BAO_CMD=""
if command -v bao >/dev/null 2>&1; then
    BAO_CMD="bao"
elif [ -f "$HOME/.local/bin/bao" ]; then
    BAO_CMD="$HOME/.local/bin/bao"
else
    echo "Error: OpenBAO (bao) not found in PATH or ~/.local/bin"
    echo "Please run 'make install-dev' to install OpenBAO"
    exit 1
fi

echo "Starting OpenBAO development server..."
echo "Log file: $LOG_FILE"
echo "PID file: $PID_FILE"

# Start OpenBAO in development mode
# -dev: Development mode (in-memory, unsealed)
# -dev-root-token-id: Set a predictable root token for development
# -dev-listen-address: Bind to localhost:8200 (matches sysmanage config)
nohup "$BAO_CMD" server \
    -dev \
    -dev-root-token-id="dev-only-token-change-me" \
    -dev-listen-address="127.0.0.1:8200" \
    -log-level="info" \
    > "$LOG_FILE" 2>&1 &

# Save PID
echo $! > "$PID_FILE"

# Wait a moment for startup
sleep 2

# Check if it started successfully
if ! kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "Error: OpenBAO failed to start"
    echo "Check log file: $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi

PID=$(cat "$PID_FILE")
echo "OpenBAO started successfully with PID $PID"
echo "Server URL: http://127.0.0.1:8200"
echo "Root token: dev-only-token-change-me"
echo ""
echo "To stop OpenBAO: make stop-openbao"
echo "To check status: make status-openbao"