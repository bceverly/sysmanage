#!/bin/bash

# SysManage Server Startup Script
# Starts both the backend API server and frontend web UI

echo "Starting SysManage Server..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

# Function to get configuration value
get_config_value() {
    local key=$1
    local config_file=""
    
    # Use same priority as backend config loader: /etc/sysmanage.yaml first, then sysmanage-dev.yaml
    if [ -f "/etc/sysmanage.yaml" ]; then
        config_file="/etc/sysmanage.yaml"
    elif [ -f "sysmanage-dev.yaml" ]; then
        config_file="sysmanage-dev.yaml"
    else
        return 1
    fi
    
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
}

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local port=$1
    local service_name=$2
    local max_attempts=30
    local attempt=0
    
    echo "Waiting for $service_name to start on port $port..."
    while [ $attempt -lt $max_attempts ]; do
        if check_port $port; then
            echo "$service_name is ready!"
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
        echo -n "."
    done
    echo
    echo "ERROR: $service_name failed to start within 30 seconds"
    return 1
}

# Function to check for running server processes
check_existing_processes() {
    local found_processes=false
    
    # Check for backend processes
    local backend_pids=$(pgrep -f "backend.main" 2>/dev/null)
    if [ -n "$backend_pids" ]; then
        echo "⚠️  Found existing backend processes:"
        echo "$backend_pids" | while read pid; do
            if [ -n "$pid" ]; then
                local cmd=$(ps -p "$pid" -o command= 2>/dev/null | head -c 80)
                echo "   PID $pid: $cmd"
            fi
        done
        found_processes=true
    fi
    
    # Check for frontend processes
    local frontend_pids=$(pgrep -f "react-scripts start" 2>/dev/null)
    if [ -n "$frontend_pids" ]; then
        echo "⚠️  Found existing frontend processes:"
        echo "$frontend_pids" | while read pid; do
            if [ -n "$pid" ]; then
                local cmd=$(ps -p "$pid" -o command= 2>/dev/null | head -c 80)
                echo "   PID $pid: $cmd"
            fi
        done
        found_processes=true
    fi
    
    # Check configured ports
    BACKEND_PORT=$(get_config_value "api.port")
    if [ $? -ne 0 ] || [ -z "$BACKEND_PORT" ]; then
        BACKEND_PORT=8080
    fi
    
    local backend_port_pid=$(lsof -ti:$BACKEND_PORT 2>/dev/null)
    if [ -n "$backend_port_pid" ]; then
        echo "⚠️  Found process using backend port $BACKEND_PORT (PID: $backend_port_pid)"
        found_processes=true
    fi
    
    FRONTEND_PORT=$(get_config_value "webui.port")
    if [ $? -ne 0 ] || [ -z "$FRONTEND_PORT" ]; then
        FRONTEND_PORT=3000
    fi
    
    local frontend_port_pid=$(lsof -ti:$FRONTEND_PORT 2>/dev/null)
    if [ -n "$frontend_port_pid" ]; then
        echo "⚠️  Found process using frontend port $FRONTEND_PORT (PID: $frontend_port_pid)"
        found_processes=true
    fi
    
    if [ "$found_processes" = true ]; then
        echo "Attempting to stop existing processes..."
        return 0  # Found processes
    else
        echo "No existing SysManage processes found"
        return 1  # No processes found
    fi
}

# Stop any existing processes
if check_existing_processes; then
    ./stop.sh
    sleep 2
    
    # Verify they were stopped
    if check_existing_processes >/dev/null 2>&1; then
        echo "❌ ERROR: Failed to stop existing processes. Please manually stop them before continuing."
        exit 1
    else
        echo "✅ Successfully stopped existing processes"
    fi
fi

# Start the backend API server
echo "Starting backend API server..."
if [ -f "backend/main.py" ]; then
    # Check if virtual environment exists and activate it
    if [ -d ".venv" ]; then
        echo "Activating virtual environment..."
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        echo "Activating virtual environment..."
        source venv/bin/activate
    fi
    
    # Get backend port from configuration
    BACKEND_PORT=$(get_config_value "api.port")
    if [ $? -ne 0 ] || [ -z "$BACKEND_PORT" ]; then
        echo "WARNING: Could not read api.port from /etc/sysmanage.yaml or sysmanage-dev.yaml, using default 8080"
        BACKEND_PORT=8080
    fi
    
    # Start the backend using the main.py configuration
    nohup python -m backend.main > logs/backend.log 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > logs/backend.pid
    
    # Wait for backend to be ready (using the configured port)
    if ! wait_for_service $BACKEND_PORT "Backend API"; then
        echo "ERROR: Backend API failed to start"
        exit 1
    fi
else
    echo "ERROR: backend/main.py not found"
    exit 1
fi

# Start the frontend web UI
echo "Starting frontend web UI..."
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    cd frontend
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "Installing frontend dependencies..."
        npm install
    fi
    
    # Start the React development server in background with HTTP forced
    nohup env FORCE_HTTP=true npm start > ../logs/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > ../logs/frontend.pid
    
    cd ..
    
    # Get frontend port from configuration
    FRONTEND_PORT=$(get_config_value "webui.port")
    if [ $? -ne 0 ] || [ -z "$FRONTEND_PORT" ]; then
        echo "WARNING: Could not read webui.port from /etc/sysmanage.yaml or sysmanage-dev.yaml, using default 3000"
        FRONTEND_PORT=3000
    fi
    
    # Wait for frontend to be ready
    if ! wait_for_service $FRONTEND_PORT "Frontend Web UI"; then
        echo "WARNING: Frontend Web UI may not have started properly"
    fi
else
    echo "ERROR: frontend directory or package.json not found"
    # Don't exit - backend can still run without frontend
fi

# Save all PIDs for stop script
echo "BACKEND_PID=$BACKEND_PID" > logs/processes.env
if [ -n "$FRONTEND_PID" ]; then
    echo "FRONTEND_PID=$FRONTEND_PID" >> logs/processes.env
fi

echo ""
echo "✅ SysManage Server is successfully running!"
echo ""
echo "Services:"
echo "  🔧 Backend API:    http://localhost:$BACKEND_PORT (WebSocket agent endpoint: ws://localhost:$BACKEND_PORT/agent/connect)"
echo "  🌐 Frontend UI:    http://localhost:$FRONTEND_PORT"
echo "  📋 API Docs:      http://localhost:$BACKEND_PORT/docs"
echo ""
echo "Logs:"
echo "  📄 Backend:       tail -f logs/backend.log"
echo "  📄 Frontend:      tail -f logs/frontend.log"
echo ""
echo "To stop the server: ./stop.sh"
echo ""