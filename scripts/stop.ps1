# SysManage Server Stop Script - PowerShell Version
# Stops both the backend API server and frontend web UI

Write-Host "Stopping SysManage Server..." -ForegroundColor Yellow

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
# Change to the project root directory (parent of scripts directory)
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

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

# Function to kill process by PID file
function Kill-ByPidFile {
    param([string]$PidFile, [string]$ServiceName)
    
    if (Test-Path $PidFile) {
        $processId = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($processId -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            Write-Host "Stopping $ServiceName (PID: $processId)..." -ForegroundColor Cyan
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

# Function to kill processes by name pattern
function Kill-ByPattern {
    param([string]$Pattern, [string]$ServiceName)
    
    $processes = Get-Process | Where-Object { $_.ProcessName -like $Pattern } -ErrorAction SilentlyContinue
    if ($processes) {
        $count = ($processes | Measure-Object).Count
        Write-Host "Found $count $ServiceName process(es), stopping them..." -ForegroundColor Cyan
        foreach ($proc in $processes) {
            Write-Host "  Stopping PID $($proc.Id): $($proc.ProcessName)" -ForegroundColor Gray
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 2
        
        # Check for remaining processes
        $remaining = Get-Process | Where-Object { $_.ProcessName -like $Pattern } -ErrorAction SilentlyContinue
        if ($remaining) {
            $remainingCount = ($remaining | Measure-Object).Count
            Write-Host "WARNING: $remainingCount $ServiceName process(es) still running, force stopping..." -ForegroundColor Yellow
            foreach ($proc in $remaining) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# Function to kill process by port
function Kill-ByPort {
    param([int]$Port, [string]$ServiceName)
    
    $connections = netstat -ano | Select-String ":$Port\s" | Select-String "LISTENING"
    foreach ($connection in $connections) {
        $parts = $connection -split '\s+'
        $processId = $parts[-1]
        if ($processId -match '^\d+$') {
            Write-Host "Killing process on port $Port (PID: $processId)..." -ForegroundColor Cyan
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

# Stop using PID files if they exist
if (Test-Path "logs") {
    Kill-ByPidFile "logs\backend.pid" "Backend API"
    Kill-ByPidFile "logs\frontend.pid" "Frontend Web UI"
}

# Fallback: kill by process patterns
Kill-ByPattern "*uvicorn*" "Backend API (uvicorn)"
Kill-ByPattern "*python*" "Backend API (Python)"
Kill-ByPattern "*react-scripts*" "Frontend Web UI (React)"

# Kill any processes on the specific ports
Write-Host "Checking for processes on SysManage ports..." -ForegroundColor Cyan

# Get configured ports
$backendPort = Get-ConfigValue "api.port"
if (-not $backendPort) {
    $backendPort = 8080  # Default fallback
}

$frontendPort = Get-ConfigValue "webui.port"
if (-not $frontendPort) {
    $frontendPort = 3000  # Default fallback
}

# Kill processes on ports
Kill-ByPort $backendPort "Backend API"
Kill-ByPort $frontendPort "Frontend Web UI"

# Clean up PID files and process environment
if (Test-Path "logs") {
    Remove-Item "logs\backend.pid" -Force -ErrorAction SilentlyContinue
    Remove-Item "logs\frontend.pid" -Force -ErrorAction SilentlyContinue
    Remove-Item "logs\processes.env" -Force -ErrorAction SilentlyContinue
}

# Verify everything is stopped
Start-Sleep -Seconds 1
$backendCheck = netstat -ano | Select-String ":$backendPort\s" | Select-String "LISTENING"
$frontendCheck = netstat -ano | Select-String ":$frontendPort\s" | Select-String "LISTENING"

if (-not $backendCheck -and -not $frontendCheck) {
    Write-Host ""
    Write-Host "[OK] SysManage Server stopped successfully!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "WARNING: Some processes may still be running" -ForegroundColor Yellow
    if ($backendCheck) {
        Write-Host "   Backend still running on port $backendPort" -ForegroundColor Yellow
    }
    if ($frontendCheck) {
        Write-Host "   Frontend still running on port $frontendPort" -ForegroundColor Yellow
    }
    Write-Host "   You may need to manually kill these processes" -ForegroundColor Yellow
}

Write-Host ""