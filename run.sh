#!/bin/sh

# SysManage Server Startup Script
# Starts both the backend API server and frontend web UI

echo "Starting SysManage Server..."

# Get the directory where this script is located (POSIX compatible)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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

# Function to generate user-friendly URLs
generate_urls() {
    local service_type=$1
    local port=$2
    
    # Get host from config
    local config_host=""
    if [ "$service_type" = "api" ]; then
        config_host=$(get_config_value "api.host")
    else
        config_host=$(get_config_value "webui.host")
    fi
    
    if [ $? -ne 0 ] || [ -z "$config_host" ]; then
        config_host="localhost"
    fi
    
    # Generate URLs based on config host
    if [ "$config_host" = "0.0.0.0" ]; then
        # When bound to 0.0.0.0, prefer FQDN, fallback to hostname, then localhost
        local fqdn=$(hostname -f 2>/dev/null)
        local shortname=$(hostname 2>/dev/null)
        
        # Check which one looks like a real FQDN (contains dots)
        if [ -n "$fqdn" ] && echo "$fqdn" | grep -q '\.' && [ "$fqdn" != "localhost" ]; then
            # Use FQDN if available and contains domain suffix
            echo "http://$fqdn:$port"
        elif [ -n "$shortname" ] && echo "$shortname" | grep -q '\.' && [ "$shortname" != "localhost" ]; then
            # Use shortname if it's actually an FQDN
            echo "http://$shortname:$port"
        elif [ -n "$fqdn" ] && [ "$fqdn" != "localhost" ]; then
            # Fall back to whatever hostname -f returned
            echo "http://$fqdn:$port"
        elif [ -n "$shortname" ] && [ "$shortname" != "localhost" ]; then
            # Fall back to what hostname returned
            echo "http://$shortname:$port"
        else
            # Fall back to localhost
            echo "http://localhost:$port"
        fi
    else
        # Use the configured host directly
        echo "http://$config_host:$port"
    fi
}

# Function to check if a port is in use
check_port() {
    local port=$1
    # Try multiple approaches for different systems
    if command -v lsof >/dev/null 2>&1; then
        lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1
    else
        # OpenBSD/BSD netstat format: try multiple patterns
        netstat -an | grep -E "(\.${port}[[:space:]].*LISTEN|:${port}[[:space:]].*LISTEN|\*\.${port}[[:space:]].*LISTEN|\*:${port}[[:space:]].*LISTEN)" >/dev/null 2>&1 || \
        netstat -an | grep "LISTEN" | grep ":${port}" >/dev/null 2>&1 || \
        netstat -an | grep "LISTEN" | grep "\.${port}" >/dev/null 2>&1
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
        # Try to check port
        if check_port $port; then
            echo
            echo "✅ $service_name is ready on port $port!"
            return 0
        fi
        
        # Also try a simple HTTP test for web services
        if command -v curl >/dev/null 2>&1; then
            if curl -s --connect-timeout 1 "http://localhost:$port" >/dev/null 2>&1; then
                echo
                echo "✅ $service_name is ready on port $port! (detected via HTTP)"
                return 0
            fi
        fi
        
        sleep 1
        attempt=$((attempt + 1))
        echo -n "."
        
        # Show debug info every 10 attempts
        if [ $((attempt % 10)) -eq 0 ]; then
            echo
            echo "⚠️  Still waiting... (attempt $attempt/$max_attempts)"
            if command -v netstat >/dev/null 2>&1; then
                echo "Current LISTEN ports:"
                netstat -an | grep LISTEN | head -5
            fi
        fi
    done
    echo
    echo "⚠️  WARNING: $service_name may not have started within 30 seconds"
    echo "   But it might actually be running. Check logs: tail -f logs/backend.log"
    return 1
}

# Function to check for running server processes
check_existing_processes() {
    local found_processes=false
    
    # Check for backend processes
    local backend_pids
    if command -v pgrep >/dev/null 2>&1; then
        backend_pids=$(pgrep -f "backend.main" 2>/dev/null)
    else
        backend_pids=$(ps -ax | grep "backend.main" | grep -v grep | awk '{print $1}')
    fi
    if [ -n "$backend_pids" ]; then
        echo "⚠️  Found existing backend processes:"
        echo "$backend_pids" | while read pid; do
            if [ -n "$pid" ]; then
                local cmd=$(ps -p "$pid" -o command= 2>/dev/null | cut -c 1-80)
                echo "   PID $pid: $cmd"
            fi
        done
        found_processes=true
    fi
    
    # Check for frontend processes
    local frontend_pids
    if command -v pgrep >/dev/null 2>&1; then
        frontend_pids=$(pgrep -f "react-scripts start" 2>/dev/null)
    else
        frontend_pids=$(ps -ax | grep "react-scripts start" | grep -v grep | awk '{print $1}')
    fi
    if [ -n "$frontend_pids" ]; then
        echo "⚠️  Found existing frontend processes:"
        echo "$frontend_pids" | while read pid; do
            if [ -n "$pid" ]; then
                local cmd=$(ps -p "$pid" -o command= 2>/dev/null | cut -c 1-80)
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
    
    local backend_port_pid
    if command -v lsof >/dev/null 2>&1; then
        backend_port_pid=$(lsof -ti:$BACKEND_PORT 2>/dev/null)
    else
        backend_port_pid=$(fstat | awk "\$9 ~ /:$BACKEND_PORT\$/ {print \$3}" | head -1 2>/dev/null)
    fi
    if [ -n "$backend_port_pid" ]; then
        echo "⚠️  Found process using backend port $BACKEND_PORT (PID: $backend_port_pid)"
        found_processes=true
    fi
    
    FRONTEND_PORT=$(get_config_value "webui.port")
    if [ $? -ne 0 ] || [ -z "$FRONTEND_PORT" ]; then
        FRONTEND_PORT=3000
    fi
    
    local frontend_port_pid
    if command -v lsof >/dev/null 2>&1; then
        frontend_port_pid=$(lsof -ti:$FRONTEND_PORT 2>/dev/null)
    else
        frontend_port_pid=$(fstat | awk "\$9 ~ /:$FRONTEND_PORT\$/ {print \$3}" | head -1 2>/dev/null)
    fi
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
    
    # Verify they were stopped by checking ports directly
    BACKEND_PORT=$(get_config_value "api.port")
    if [ $? -ne 0 ] || [ -z "$BACKEND_PORT" ]; then
        BACKEND_PORT=8080
    fi
    
    FRONTEND_PORT=$(get_config_value "webui.port")
    if [ $? -ne 0 ] || [ -z "$FRONTEND_PORT" ]; then
        FRONTEND_PORT=3000
    fi
    
    # Check if ports are still in use
    backend_still_running=false
    frontend_still_running=false
    
    if check_port $BACKEND_PORT; then
        backend_still_running=true
    fi
    
    if check_port $FRONTEND_PORT; then
        frontend_still_running=true
    fi
    
    if [ "$backend_still_running" = true ] || [ "$frontend_still_running" = true ]; then
        echo "❌ ERROR: Failed to stop existing processes. Please manually stop them before continuing."
        if [ "$backend_still_running" = true ]; then
            echo "   Backend still running on port $BACKEND_PORT"
        fi
        if [ "$frontend_still_running" = true ]; then
            echo "   Frontend still running on port $FRONTEND_PORT"
        fi
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
        . .venv/bin/activate
    elif [ -d "venv" ]; then
        echo "Activating virtual environment..."
        . venv/bin/activate
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
        echo "⚠️  WARNING: Backend API detection failed, but continuing..."
        echo "   The backend may actually be running. Check logs: tail -f logs/backend.log"
        echo "   Continuing with frontend startup..."
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
    
    # Get webui host and port from configuration  
    WEBUI_HOST=$(get_config_value "webui.host")
    if [ $? -ne 0 ] || [ -z "$WEBUI_HOST" ]; then
        WEBUI_HOST="localhost"
    fi
    
    WEBUI_PORT=$(get_config_value "webui.port")
    if [ $? -ne 0 ] || [ -z "$WEBUI_PORT" ]; then
        WEBUI_PORT="3000"
    fi
    
    # Start the React development server in background with config-driven host/port
    nohup env FORCE_HTTP=true VITE_HOST="$WEBUI_HOST" VITE_PORT="$WEBUI_PORT" npm start > ../logs/frontend.log 2>&1 &
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

# Backend API URL
backend_url=$(generate_urls "api" "$BACKEND_PORT")
ws_url=$(echo "$backend_url" | sed 's|http://|ws://|')/agent/connect
echo "  🔧 Backend API:      $backend_url"
echo "  📡 Agent WebSocket:  $ws_url"

# Frontend UI URL
if [ -n "$FRONTEND_PID" ]; then
    frontend_url=$(generate_urls "webui" "$FRONTEND_PORT")
    echo "  🌐 Frontend UI:      $frontend_url"
fi

# API Documentation URL
api_docs_url="$backend_url/docs"
echo "  📋 API Docs:        $api_docs_url"

echo ""
echo "Logs:"
echo "  📄 Backend:       tail -f logs/backend.log"
echo "  📄 Frontend:      tail -f logs/frontend.log"
echo ""
echo "To stop the server: ./stop.sh"
echo ""