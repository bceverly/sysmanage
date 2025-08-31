#!/bin/bash

# SysManage Server Stop Script
# Stops both the backend API server and frontend web UI

echo "Stopping SysManage Server..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Function to get configuration value
get_config_value() {
    local key=$1
    local config_file="sysmanage.yaml"
    
    if [ -f "$config_file" ]; then
        python3 -c "
import yaml
import sys
try:
    with open('$config_file', 'r') as f:
        config = yaml.safe_load(f)
    keys = '$key'.split('.')
    value = config
    for k in keys:
        value = value[k]
    print(value)
except:
    sys.exit(1)
" 2>/dev/null
    else
        return 1
    fi
}

# Function to kill process by PID file
kill_by_pidfile() {
    local pidfile=$1
    local service_name=$2
    
    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "Stopping $service_name (PID: $pid)..."
            kill "$pid"
            sleep 2
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                echo "Force stopping $service_name..."
                kill -9 "$pid" 2>/dev/null
            fi
        fi
        rm -f "$pidfile"
    fi
}

# Function to kill processes by name pattern
kill_by_pattern() {
    local pattern=$1
    local service_name=$2
    
    local pids=$(pgrep -f "$pattern" 2>/dev/null)
    if [ -n "$pids" ]; then
        local pid_count=$(echo "$pids" | wc -l)
        echo "Found $pid_count $service_name process(es), stopping them..."
        echo "$pids" | while read pid; do
            if [ -n "$pid" ]; then
                local cmd=$(ps -p "$pid" -o command= 2>/dev/null | head -c 60)
                echo "  Stopping PID $pid: $cmd"
            fi
        done
        echo "$pids" | xargs kill 2>/dev/null
        sleep 2
        # Force kill if still running
        local remaining_pids=$(pgrep -f "$pattern" 2>/dev/null)
        if [ -n "$remaining_pids" ]; then
            local remaining_count=$(echo "$remaining_pids" | wc -l)
            echo "⚠️  $remaining_count $service_name process(es) still running, force stopping..."
            echo "$remaining_pids" | xargs kill -9 2>/dev/null
        fi
    fi
}

# Stop using PID files if they exist
if [ -d "logs" ]; then
    kill_by_pidfile "logs/backend.pid" "Backend API"
    kill_by_pidfile "logs/frontend.pid" "Frontend Web UI"
fi

# Fallback: kill by process patterns
kill_by_pattern "uvicorn.*backend.main:app" "Backend API (uvicorn)"
kill_by_pattern "react-scripts start" "Frontend Web UI (React)"
kill_by_pattern "node.*react-scripts.*start" "Frontend Web UI (Node)"

# Kill any processes on the specific ports
echo "Checking for processes on SysManage ports..."

# Get configured ports
BACKEND_PORT=$(get_config_value "webui.port")
if [ $? -ne 0 ] || [ -z "$BACKEND_PORT" ]; then
    BACKEND_PORT=8080  # Default fallback
fi

FRONTEND_PORT=3000  # React dev server default

# Backend port
backend_pid=$(lsof -ti:$BACKEND_PORT 2>/dev/null)
if [ -n "$backend_pid" ]; then
    echo "Killing process on port $BACKEND_PORT (PID: $backend_pid)..."
    kill -9 $backend_pid 2>/dev/null
fi

# Frontend port
frontend_pid=$(lsof -ti:$FRONTEND_PORT 2>/dev/null)
if [ -n "$frontend_pid" ]; then
    echo "Killing process on port $FRONTEND_PORT (PID: $frontend_pid)..."
    kill -9 $frontend_pid 2>/dev/null
fi

# Clean up PID files and process environment
if [ -d "logs" ]; then
    rm -f logs/backend.pid
    rm -f logs/frontend.pid
    rm -f logs/processes.env
fi

# Verify everything is stopped
sleep 1
backend_check=$(lsof -ti:$BACKEND_PORT 2>/dev/null)
frontend_check=$(lsof -ti:$FRONTEND_PORT 2>/dev/null)

if [ -z "$backend_check" ] && [ -z "$frontend_check" ]; then
    echo ""
    echo "✅ SysManage Server stopped successfully!"
else
    echo ""
    echo "⚠️  Warning: Some processes may still be running"
    if [ -n "$backend_check" ]; then
        echo "   Backend still running on port $BACKEND_PORT"
    fi
    if [ -n "$frontend_check" ]; then
        echo "   Frontend still running on port $FRONTEND_PORT"
    fi
    echo "   You may need to manually kill these processes"
fi

echo ""