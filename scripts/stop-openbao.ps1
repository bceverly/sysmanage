# OpenBAO Development Server Stop Script (PowerShell)
# Stops the OpenBAO development server

param(
    [switch]$Help
)

if ($Help) {
    Write-Host "OpenBAO Development Server Stop Script"
    Write-Host "Usage: .\stop-openbao.ps1"
    Write-Host ""
    Write-Host "Stops the OpenBAO development server"
    exit 0
}

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$PidFile = Join-Path $ProjectDir ".openbao.pid"

# Check if PID file exists
if (-not (Test-Path $PidFile)) {
    Write-Host "OpenBAO is not running (no PID file found)" -ForegroundColor Yellow
    exit 0
}

# Read PID
try {
    $OpenBaoPid = Get-Content $PidFile -ErrorAction Stop
    $OpenBaoPid = [int]$OpenBaoPid.Trim()
} catch {
    Write-Host "Error reading PID file: $($_.Exception.Message)" -ForegroundColor Red
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    exit 1
}

# Check if process is actually running
try {
    $Process = Get-Process -Id $OpenBaoPid -ErrorAction Stop
} catch {
    Write-Host "OpenBAO process (PID $OpenBaoPid) is not running, cleaning up PID file" -ForegroundColor Yellow
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    exit 0
}

Write-Host "Stopping OpenBAO (PID $OpenBaoPid)..." -ForegroundColor Cyan

try {
    # Try graceful shutdown first
    $Process.CloseMainWindow() | Out-Null

    # Wait up to 10 seconds for graceful shutdown
    $MaxWait = 10
    $WaitCount = 0

    while ($WaitCount -lt $MaxWait) {
        try {
            $Process = Get-Process -Id $OpenBaoPid -ErrorAction Stop
            Start-Sleep -Seconds 1
            $WaitCount++
        } catch {
            # Process has exited
            Write-Host "OpenBAO stopped gracefully" -ForegroundColor Green
            Remove-Item $PidFile -ErrorAction SilentlyContinue
            exit 0
        }
    }

    # If still running, force kill
    Write-Host "Graceful shutdown timed out, force killing..." -ForegroundColor Yellow
    try {
        $Process = Get-Process -Id $OpenBaoPid -ErrorAction Stop
        $Process.Kill()
        $Process.WaitForExit(5000)  # Wait up to 5 seconds for kill to complete
        Write-Host "OpenBAO force stopped" -ForegroundColor Green
    } catch {
        Write-Host "Failed to stop OpenBAO process: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }

} catch {
    Write-Host "Failed to stop OpenBAO process: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Clean up PID file
Remove-Item $PidFile -ErrorAction SilentlyContinue
Write-Host "OpenBAO stopped" -ForegroundColor Green