#!/bin/sh
#
# OpenBAO Development Server Start Script
# Starts OpenBAO in development mode for sysmanage integration
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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

# Find OpenBAO or Vault binary
# OPENBAO_BIN environment variable takes priority if set
BAO_CMD=""
if [ -n "$OPENBAO_BIN" ]; then
    if [ -x "$OPENBAO_BIN" ]; then
        BAO_CMD="$OPENBAO_BIN"
        echo "Using OPENBAO_BIN override: $BAO_CMD"
    else
        echo "Warning: OPENBAO_BIN is set to '$OPENBAO_BIN' but it is not executable"
        exit 1
    fi
elif command -v bao >/dev/null 2>&1; then
    BAO_CMD="bao"
elif [ -f "$HOME/.local/bin/bao" ]; then
    BAO_CMD="$HOME/.local/bin/bao"
elif command -v vault >/dev/null 2>&1; then
    echo "Note: Using 'vault' as fallback (OpenBAO not found)"
    BAO_CMD="vault"
else
    echo "Warning: OpenBAO/Vault not found in PATH or ~/.local/bin"
    echo "SysManage will run with vault.enabled=false in config"
    echo "To install OpenBAO, run: make install-dev"
    echo ""
    echo "Continuing without OpenBAO/Vault..."
    exit 0  # Exit gracefully so make start continues
fi

echo "Starting OpenBAO development server..."
echo "Log file: $LOG_FILE"
echo "PID file: $PID_FILE"

# Check if production config exists
VAULT_CONFIG="$PROJECT_DIR/openbao.hcl"
VAULT_CREDS="$PROJECT_DIR/.vault_credentials"

if [ -f "$VAULT_CONFIG" ] && [ -f "$VAULT_CREDS" ]; then
    echo "Starting OpenBAO in production mode with persistent storage..."
    # Start OpenBAO with production config
    nohup "$BAO_CMD" server -config="$VAULT_CONFIG" > "$LOG_FILE" 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > "$PID_FILE"

    # Wait for server startup
    sleep 3

    # Source credentials and unseal
    . "$VAULT_CREDS"
    export BAO_ADDR="http://127.0.0.1:8200"

    # Check if vault needs unsealing
    if "$BAO_CMD" status 2>&1 | grep -q "Sealed.*true"; then
        echo "Unsealing vault..."
        "$BAO_CMD" operator unseal "$UNSEAL_KEY"
    fi
else
    echo "Production config not found, starting in development mode..."
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
fi

# Save PID (only for dev mode, production mode already saved PID)
if [ ! -f "$VAULT_CONFIG" ] || [ ! -f "$VAULT_CREDS" ]; then
    echo $! > "$PID_FILE"
fi

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

# Display appropriate token message based on mode
if [ -f "$VAULT_CONFIG" ] && [ -f "$VAULT_CREDS" ]; then
    # Production mode - read actual token from credentials
    if [ -f "$VAULT_CREDS" ]; then
        PROD_TOKEN=$(grep "ROOT_TOKEN=" "$VAULT_CREDS" | cut -d'=' -f2)
        if [ -n "$PROD_TOKEN" ]; then
            echo "Root token: $PROD_TOKEN (production mode)"
        else
            echo "Root token: [check .vault_credentials file] (production mode)"
        fi
    else
        echo "Root token: [check .vault_credentials file] (production mode)"
    fi
else
    # Development mode
    echo "Root token: dev-only-token-change-me (development mode)"
fi

echo ""
echo "To stop OpenBAO: make stop-openbao"
echo "To check status: make status-openbao"