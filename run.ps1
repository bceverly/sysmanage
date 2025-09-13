# SysManage Server Startup Script - PowerShell Version
# Starts both the backend API server and frontend web UI

Write-Host "Starting SysManage Server..." -ForegroundColor Green

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Create logs directory if it doesn't exist
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

# Function to get configuration value
function Get-ConfigValue {
    param([string]$Key)
    
    $configFile = $null
    if (Test-Path "/etc/sysmanage.yaml") {
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
if (Test-Path "stop.ps1") {
    & ".\stop.ps1"
    Start-Sleep -Seconds 2
} else {
    Write-Host "WARNING: stop.ps1 not found, continuing anyway..." -ForegroundColor Yellow
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
    $backendJob = Start-Job -ScriptBlock {
        param($scriptDir, $venvPath)
        Set-Location $scriptDir
        if ($venvPath) { & $venvPath }
        python -m backend.main *>&1 | Out-File -FilePath "logs\backend.log" -Append -Encoding utf8
    } -ArgumentList $ScriptDir, $venvPath
    
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
    $env:FORCE_HTTP = "true"
    $env:VITE_HOST = $webuiHost
    $env:VITE_PORT = $frontendPort
    
    $frontendJob = Start-Job -ScriptBlock {
        param($frontendDir, $webuiHost, $frontendPort)
        Set-Location $frontendDir
        $env:FORCE_HTTP = "true"
        $env:VITE_HOST = $webuiHost
        $env:VITE_PORT = $frontendPort
        npm start *>&1 | Out-File -FilePath "..\logs\frontend.log" -Append -Encoding utf8
    } -ArgumentList (Join-Path $ScriptDir "frontend"), $webuiHost, $frontendPort
    
    Set-Location $ScriptDir
    
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
$wsUrl = ($backendUrl -replace "http://", "ws://") + "/api/agent/connect"
Write-Host "  Backend API:      $backendUrl" -ForegroundColor Cyan
Write-Host "  Agent WebSocket:  $wsUrl" -ForegroundColor Cyan

if ($frontendJob) {
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
Write-Host "To stop the server: .\stop.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Services are now running in the background." -ForegroundColor Green
