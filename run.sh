#!/bin/bash

# SysManage Server Startup Script
# Starts both the backend API server and frontend web UI

echo "Starting SysManage Server..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

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

# Stop any existing processes
echo "Stopping any existing SysManage processes..."
./stop.sh >/dev/null 2>&1

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
    
    # Start uvicorn server in background
    nohup uvicorn backend.main:app --host 0.0.0.0 --port 6443 --ssl-keyfile ~/dev/certs/sysmanage.org/privkey.pem --ssl-certfile ~/dev/certs/sysmanage.org/cert.pem > logs/backend.log 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > logs/backend.pid
    
    # Wait for backend to be ready
    if ! wait_for_service 6443 "Backend API"; then
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
    
    # Start the React development server in background
    nohup npm start > ../logs/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > ../logs/frontend.pid
    
    cd ..
    
    # Wait for frontend to be ready
    if ! wait_for_service 7443 "Frontend Web UI"; then
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
echo "  🔧 Backend API:    https://localhost:6443 (WebSocket agent endpoint: wss://localhost:6443/agent/connect)"
echo "  🌐 Frontend UI:    https://localhost:7443"
echo "  📋 API Docs:      https://localhost:6443/docs"
echo ""
echo "Logs:"
echo "  📄 Backend:       tail -f logs/backend.log"
echo "  📄 Frontend:      tail -f logs/frontend.log"
echo ""
echo "To stop the server: ./stop.sh"
echo ""