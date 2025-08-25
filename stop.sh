#!/bin/bash

# SysManage Server Stop Script
# Stops both the backend API server and frontend web UI

echo "Stopping SysManage Server..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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
        echo "Stopping $service_name processes..."
        echo "$pids" | xargs kill 2>/dev/null
        sleep 2
        # Force kill if still running
        local remaining_pids=$(pgrep -f "$pattern" 2>/dev/null)
        if [ -n "$remaining_pids" ]; then
            echo "Force stopping $service_name processes..."
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

# Backend port (6443)
backend_pid=$(lsof -ti:6443 2>/dev/null)
if [ -n "$backend_pid" ]; then
    echo "Killing process on port 6443 (PID: $backend_pid)..."
    kill -9 $backend_pid 2>/dev/null
fi

# Frontend port (7443)
frontend_pid=$(lsof -ti:7443 2>/dev/null)
if [ -n "$frontend_pid" ]; then
    echo "Killing process on port 7443 (PID: $frontend_pid)..."
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
backend_check=$(lsof -ti:6443 2>/dev/null)
frontend_check=$(lsof -ti:7443 2>/dev/null)

if [ -z "$backend_check" ] && [ -z "$frontend_check" ]; then
    echo ""
    echo "✅ SysManage Server stopped successfully!"
else
    echo ""
    echo "⚠️  Warning: Some processes may still be running"
    if [ -n "$backend_check" ]; then
        echo "   Backend still running on port 6443"
    fi
    if [ -n "$frontend_check" ]; then
        echo "   Frontend still running on port 7443"
    fi
    echo "   You may need to manually kill these processes"
fi

echo ""