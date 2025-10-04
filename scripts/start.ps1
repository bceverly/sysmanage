# SysManage Server Startup Script - PowerShell Version
# Starts both the backend API server and frontend web UI

Write-Host "Starting SysManage Server..." -ForegroundColor Green

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
# Change to the project root directory (parent of scripts directory)
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Create logs directory if it doesn't exist
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

# Function to get configuration value
function Get-ConfigValue {
    param([string]$Key)
    
    $configFile = $null
    if (Test-Path "C:\ProgramData\SysManage\sysmanage.yaml") {
        $configFile = "C:\ProgramData\SysManage\sysmanage.yaml"
    } elseif (Test-Path "/etc/sysmanage.yaml") {
        $configFile = "/etc/sysmanage.yaml"
    } elseif (Test-Path "sysmanage-dev.yaml") {
        $configFile = "sysmanage-dev.yaml"
    } else {
        return $null
    }
    
    try {
        $pythonCode = @"
import yaml
import sys
try:
    with open('$configFile', 'r') as f:
        config = yaml.safe_load(f)
    keys = '$Key'.split('.')
    value = config
    for k in keys:
        value = value[k]
    print(value)
except:
    sys.exit(1)
"@
        $result = python -c $pythonCode 2>$null
        return $result
    } catch {
        return $null
    }
}

# Function to generate user-friendly URLs
function Get-ServiceUrl {
    param([string]$ServiceType, [int]$Port)
    
    $configHost = $null
    if ($ServiceType -eq "api") {
        $configHost = Get-ConfigValue "api.host"
    } else {
        $configHost = Get-ConfigValue "webui.host"
    }
    
    if (-not $configHost) {
        $configHost = "localhost"
    }
    
    if ($configHost -eq "0.0.0.0") {
        # When bound to 0.0.0.0, prefer FQDN, fallback to hostname, then localhost
        try {
            $fqdn = [System.Net.Dns]::GetHostByName($env:COMPUTERNAME).HostName
            if ($fqdn -and $fqdn -ne "localhost" -and $fqdn.Contains(".")) {
                return "http://${fqdn}:${Port}"
            }
        } catch {}
        
        try {
            $hostname = $env:COMPUTERNAME
            if ($hostname -and $hostname -ne "localhost") {
                return "http://${hostname}:${Port}"
            }
        } catch {}
        
        return "http://localhost:${Port}"
    } else {
        return "http://${configHost}:${Port}"
    }
}

# Function to check if a port is in use
function Test-Port {
    param([int]$Port)
    
    $connections = netstat -an | Select-String ":$Port\s" | Select-String "LISTENING"
    return ($connections.Count -gt 0)
}

# Function to wait for service to be ready
function Wait-ForService {
    param([int]$Port, [string]$ServiceName)
    
    $maxAttempts = 30
    $attempt = 0
    
    Write-Host "Waiting for $ServiceName to start on port $Port..." -ForegroundColor Cyan
    
    while ($attempt -lt $maxAttempts) {
        if (Test-Port -Port $Port) {
            Write-Host ""
            Write-Host "[OK] $ServiceName is ready on port $Port!" -ForegroundColor Green
            return $true
        }
        
        # Also try a simple HTTP test for web services
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$Port" -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($response) {
                Write-Host ""
                Write-Host "[OK] $ServiceName is ready on port $Port! (detected via HTTP)" -ForegroundColor Green
                return $true
            }
        } catch {}
        
        Start-Sleep -Seconds 1
        $attempt++
        Write-Host -NoNewline "."
        
        # Show debug info every 10 attempts
        if ($attempt % 10 -eq 0) {
            Write-Host ""
            Write-Host "WARNING: Still waiting... (attempt $attempt/$maxAttempts)" -ForegroundColor Yellow
            Write-Host "Current LISTENING ports:" -ForegroundColor Gray
            netstat -an | Select-String "LISTENING" | Select-Object -First 5 | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
        }
    }
    
    Write-Host ""
    Write-Host "WARNING: $ServiceName may not have started within 30 seconds" -ForegroundColor Yellow
    Write-Host "   But it might actually be running. Check logs: Get-Content logs\backend.log -Tail 10" -ForegroundColor Yellow
    return $false
}

# Stop any existing processes first
Write-Host "Stopping any existing SysManage processes..." -ForegroundColor Cyan
if (Test-Path "scripts\stop.ps1") {
    & ".\scripts\stop.ps1"
    Start-Sleep -Seconds 2
} else {
    Write-Host "WARNING: scripts\stop.ps1 not found, continuing anyway..." -ForegroundColor Yellow
}

# Get configuration values
$backendPort = Get-ConfigValue "api.port"
if (-not $backendPort) {
    Write-Host "WARNING: Could not read api.port from configuration, using default 8080" -ForegroundColor Yellow
    $backendPort = 8080
}

$frontendPort = Get-ConfigValue "webui.port"
if (-not $frontendPort) {
    Write-Host "WARNING: Could not read webui.port from configuration, using default 3000" -ForegroundColor Yellow
    $frontendPort = 3000
}

$webuiHost = Get-ConfigValue "webui.host"
if (-not $webuiHost) {
    $webuiHost = "localhost"
}

# Start the backend API server
Write-Host "Starting backend API server..." -ForegroundColor Cyan
if (Test-Path "backend\main.py") {
    # Check if virtual environment exists and activate it
    $venvPath = $null
    if (Test-Path ".venv\Scripts\Activate.ps1") {
        Write-Host "Activating virtual environment..." -ForegroundColor Gray
        $venvPath = ".venv\Scripts\Activate.ps1"
    } elseif (Test-Path "venv\Scripts\Activate.ps1") {
        Write-Host "Activating virtual environment..." -ForegroundColor Gray
        $venvPath = "venv\Scripts\Activate.ps1"
    }
    
    if ($venvPath) {
        & $venvPath
    }
    
    # Start the backend using the main.py configuration
    Write-Host "Starting backend on port $backendPort..." -ForegroundColor Gray

    # Build the command to run based on virtual environment availability
    if ($venvPath) {
        $pythonExe = ".venv\Scripts\python.exe"
    } else {
        $pythonExe = "python"
    }

    # Set up environment for backend
    $env:PYTHONPATH = $ProjectRoot

    # Create a batch file to run the backend with proper logging
    $backendBatchContent = @"
@echo off
set PYTHONPATH=$ProjectRoot
cd /d "$ProjectRoot"
$pythonExe -m backend.main >> "$ProjectRoot\logs\backend.log" 2>&1
"@

    $backendBatchFile = "logs\start_backend.bat"
    $backendBatchContent | Out-File $backendBatchFile -Encoding ascii

    # Start backend process in new window
    $backendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $backendBatchFile -PassThru -WorkingDirectory $ProjectRoot

    # Store process ID for later cleanup
    if ($backendProcess) {
        $backendProcess.Id | Out-File "logs\backend.pid" -Encoding ascii
        Write-Host "Backend process started with PID: $($backendProcess.Id)" -ForegroundColor Gray
    } else {
        Write-Host "ERROR: Failed to start backend process" -ForegroundColor Red
    }
    
    # Wait for backend to be ready
    if (-not (Wait-ForService -Port $backendPort -ServiceName "Backend API")) {
        Write-Host "WARNING: Backend API detection failed, but continuing..." -ForegroundColor Yellow
        Write-Host "   The backend may actually be running. Check logs: Get-Content logs\backend.log -Tail 10" -ForegroundColor Yellow
        Write-Host "   Continuing with frontend startup..." -ForegroundColor Yellow
    }
} else {
    Write-Host "ERROR: backend\main.py not found" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Start the frontend web UI
Write-Host "Starting frontend web UI..." -ForegroundColor Cyan
if ((Test-Path "frontend") -and (Test-Path "frontend\package.json")) {
    Set-Location "frontend"
    
    # Install dependencies if node_modules doesn't exist
    if (-not (Test-Path "node_modules")) {
        Write-Host "Installing frontend dependencies..." -ForegroundColor Gray
        npm install
    }
    
    # Start the React development server
    Write-Host "Starting frontend on port $frontendPort..." -ForegroundColor Gray

    # Start npm directly with PowerShell without batch file
    Write-Host "Starting npm directly from PowerShell..." -ForegroundColor Gray

    # Change to frontend directory and start npm with output redirection
    Push-Location "$ProjectRoot\frontend"

    # Create null input file for process redirection
    $nullInputFile = "$ProjectRoot\logs\null_input.txt"
    if (-not (Test-Path $nullInputFile)) {
        New-Item -ItemType File -Path $nullInputFile -Force | Out-Null
    }

    # Start npm as background process in new window
    # Use npm.cmd on Windows
    try {
        $frontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList "start" `
            -WorkingDirectory "$ProjectRoot\frontend" `
            -PassThru

        Pop-Location

        # Store process ID for later cleanup
        if ($frontendProcess -and $frontendProcess.Id) {
            $frontendProcess.Id | Out-File "$ProjectRoot\logs\frontend.pid" -Encoding ascii
            Write-Host "Frontend process started with PID: $($frontendProcess.Id)" -ForegroundColor Gray
        } else {
            Write-Host "ERROR: Failed to start frontend process - no process ID returned" -ForegroundColor Red
        }
    } catch {
        Pop-Location
        Write-Host "ERROR: Failed to start frontend process - $($_.Exception.Message)" -ForegroundColor Red
    }
    
    Set-Location $ProjectRoot
    
    # Wait for frontend to be ready
    if (-not (Wait-ForService -Port $frontendPort -ServiceName "Frontend Web UI")) {
        Write-Host "WARNING: Frontend Web UI may not have started properly" -ForegroundColor Yellow
    }
} else {
    Write-Host "ERROR: frontend directory or package.json not found" -ForegroundColor Red
    # Don't exit - backend can still run without frontend
}

Write-Host ""
Write-Host "[OK] SysManage Server is successfully running!" -ForegroundColor Green
Write-Host ""
Write-Host "Services:" -ForegroundColor White

# Generate URLs
$backendUrl = Get-ServiceUrl -ServiceType "api" -Port $backendPort
# nosemgrep: javascript.lang.security.detect-insecure-websocket.detect-insecure-websocket
$wsUrl = ($backendUrl -replace "http://", "ws://" -replace "https://", "wss://") + "/api/agent/connect"
Write-Host "  Backend API:      $backendUrl" -ForegroundColor Cyan
Write-Host "  Agent WebSocket:  $wsUrl" -ForegroundColor Cyan

if ($frontendProcess) {
    $frontendUrl = Get-ServiceUrl -ServiceType "webui" -Port $frontendPort
    Write-Host "  Frontend UI:      $frontendUrl" -ForegroundColor Cyan
}

$apiDocsUrl = "$backendUrl/docs"
Write-Host "  API Docs:        $apiDocsUrl" -ForegroundColor Cyan

Write-Host ""
Write-Host "Logs:" -ForegroundColor White
Write-Host "  Backend:       Get-Content logs\backend.log -Tail 20 -Wait" -ForegroundColor Gray
Write-Host "  Frontend:      Get-Content logs\frontend.log -Tail 20 -Wait" -ForegroundColor Gray
Write-Host ""
Write-Host "To stop the server: .\scripts\stop.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Services are now running in the background." -ForegroundColor Green
