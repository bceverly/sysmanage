#!/bin/bash
#
# OpenBAO Development Server Stop Script
# Stops the OpenBAO development server
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$PROJECT_DIR/.openbao.pid"

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "OpenBAO is not running (no PID file found)"
    exit 0
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is actually running
if ! kill -0 "$PID" 2>/dev/null; then
    echo "OpenBAO process (PID $PID) is not running, cleaning up PID file"
    rm -f "$PID_FILE"
    exit 0
fi

echo "Stopping OpenBAO (PID $PID)..."

# Try graceful shutdown first
if kill -TERM "$PID" 2>/dev/null; then
    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "OpenBAO stopped gracefully"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
    done

    # If still running, force kill
    echo "Graceful shutdown timed out, force killing..."
    if kill -KILL "$PID" 2>/dev/null; then
        echo "OpenBAO force stopped"
    else
        echo "Failed to stop OpenBAO process"
        exit 1
    fi
else
    echo "Failed to send stop signal to OpenBAO process"
    exit 1
fi

# Clean up PID file
rm -f "$PID_FILE"
echo "OpenBAO stopped"