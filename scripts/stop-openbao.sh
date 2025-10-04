#!/bin/sh
#
# OpenBAO Development Server Stop Script
# Stops the OpenBAO development server
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$PROJECT_DIR/.openbao.pid"

# Function to kill process with optional sudo
kill_process() {
    local pid=$1
    local use_sudo=$2

    if [ "$use_sudo" = "true" ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo kill -TERM "$pid" 2>/dev/null && return 0
        fi
        return 1
    else
        kill -TERM "$pid" 2>/dev/null && return 0
        return 1
    fi
}

force_kill_process() {
    local pid=$1
    local use_sudo=$2

    if [ "$use_sudo" = "true" ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo kill -KILL "$pid" 2>/dev/null && return 0
        fi
        return 1
    else
        kill -KILL "$pid" 2>/dev/null && return 0
        return 1
    fi
}

# Check for orphaned bao/vault processes (running but no PID file)
if [ ! -f "$PID_FILE" ]; then
    echo "No PID file found, checking for orphaned OpenBAO processes..."

    # Find bao or vault processes
    ORPHANED_PIDS=$(ps aux | grep -E '[b]ao server|[v]ault server' | awk '{print $2}')

    if [ -z "$ORPHANED_PIDS" ]; then
        echo "OpenBAO is not running"
        exit 0
    fi

    echo "Found orphaned OpenBAO process(es):"
    ps aux | grep -E '[b]ao server|[v]ault server'

    for pid in $ORPHANED_PIDS; do
        echo "Stopping orphaned OpenBAO process (PID $pid)..."

        # Try without sudo first
        if kill_process "$pid" false; then
            # Wait up to 5 seconds
            i=1
            while [ $i -le 5 ]; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    echo "Process stopped gracefully"
                    continue 2
                fi
                sleep 1
                i=$((i + 1))
            done
            force_kill_process "$pid" false && echo "Process force stopped" && continue
        fi

        # If that failed, try with sudo
        echo "Permission denied, trying with sudo..."
        if kill_process "$pid" true; then
            # Wait up to 5 seconds
            i=1
            while [ $i -le 5 ]; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    echo "Process stopped gracefully (with sudo)"
                    continue 2
                fi
                sleep 1
                i=$((i + 1))
            done
            force_kill_process "$pid" true && echo "Process force stopped (with sudo)"
        else
            echo "Failed to stop process $pid"
        fi
    done

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
    i=1
    while [ $i -le 10 ]; do
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "OpenBAO stopped gracefully"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
        i=$((i + 1))
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
    # Permission denied - might be running as root
    echo "Permission denied, trying with sudo..."
    if command -v sudo >/dev/null 2>&1; then
        if sudo kill -TERM "$PID" 2>/dev/null; then
            # Wait up to 10 seconds for graceful shutdown
            i=1
            while [ $i -le 10 ]; do
                if ! kill -0 "$PID" 2>/dev/null; then
                    echo "OpenBAO stopped gracefully (with sudo)"
                    rm -f "$PID_FILE"
                    exit 0
                fi
                sleep 1
                i=$((i + 1))
            done

            # If still running, force kill with sudo
            echo "Graceful shutdown timed out, force killing with sudo..."
            if sudo kill -KILL "$PID" 2>/dev/null; then
                echo "OpenBAO force stopped (with sudo)"
                rm -f "$PID_FILE"
                exit 0
            fi
        fi
    fi
    echo "Failed to stop OpenBAO process"
    exit 1
fi

# Clean up PID file
rm -f "$PID_FILE"
echo "OpenBAO stopped"