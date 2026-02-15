#!/bin/bash
#
# OpenBAO Development Server Status Script
# Checks the status of the OpenBAO development server
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$PROJECT_DIR/.openbao.pid"
LOG_FILE="$PROJECT_DIR/logs/openbao.log"

echo "OpenBAO Status Check"
echo "===================="

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "Status: Not running (no PID file)"
    exit 0
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is running
if kill -0 "$PID" 2>/dev/null; then
    echo "Status: Running (PID $PID)"
    echo "Server URL: http://127.0.0.1:8200"

    # Try to get server status if bao command is available
    # OPENBAO_BIN environment variable takes priority if set
    BAO_CMD=""
    if [ -n "$OPENBAO_BIN" ] && [ -x "$OPENBAO_BIN" ]; then
        BAO_CMD="$OPENBAO_BIN"
    elif command -v bao >/dev/null 2>&1; then
        BAO_CMD="bao"
    elif [ -f "$HOME/.local/bin/bao" ]; then
        BAO_CMD="$HOME/.local/bin/bao"
    fi

    if [ -n "$BAO_CMD" ]; then
        echo ""
        echo "Server Status:"
        export BAO_ADDR="http://127.0.0.1:8200"
        export BAO_TOKEN="dev-only-token-change-me"
        if "$BAO_CMD" status 2>/dev/null; then
            echo ""
            echo "Health Check: OK"
        else
            echo "Health Check: Server not responding to API calls"
        fi
    fi

    # Show recent log entries
    if [ -f "$LOG_FILE" ]; then
        echo ""
        echo "Recent log entries:"
        echo "-------------------"
        tail -5 "$LOG_FILE" 2>/dev/null || echo "No recent log entries"
    fi
else
    echo "Status: Not running (process $PID not found)"
    echo "Cleaning up stale PID file..."
    rm -f "$PID_FILE"
fi