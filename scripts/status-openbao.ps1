# OpenBAO Development Server Status Script (PowerShell)
# Checks the status of the OpenBAO development server

param(
    [switch]$Help
)

if ($Help) {
    Write-Host "OpenBAO Development Server Status Script"
    Write-Host "Usage: .\status-openbao.ps1"
    Write-Host ""
    Write-Host "Checks the status of the OpenBAO development server"
    exit 0
}

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$PidFile = Join-Path $ProjectDir ".openbao.pid"
$LogFile = Join-Path $ProjectDir "logs\openbao.log"

Write-Host "OpenBAO Status Check" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan

# Check if PID file exists
if (-not (Test-Path $PidFile)) {
    Write-Host "Status: Not running (no PID file)" -ForegroundColor Yellow
    exit 0
}

# Read PID
try {
    $OpenBaoPid = Get-Content $PidFile -ErrorAction Stop
    $OpenBaoPid = [int]$OpenBaoPid.Trim()
} catch {
    Write-Host "Status: Error reading PID file" -ForegroundColor Red
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    exit 1
}

# Check if process is running
try {
    $Process = Get-Process -Id $OpenBaoPid -ErrorAction Stop
    Write-Host "Status: Running (PID $OpenBaoPid)" -ForegroundColor Green
    Write-Host "Server URL: http://127.0.0.1:8200" -ForegroundColor Cyan

    # Try to get server status if bao command is available
    $BaoCmd = $null

    # Check for bao in PATH
    try {
        $BaoCmdPath = Get-Command "bao" -ErrorAction Stop
        $BaoCmd = "bao"
    } catch {
        # Check for bao.exe in common locations
        $CommonPaths = @(
            "$env:USERPROFILE\AppData\Local\bin\bao.exe",
            "$env:PROGRAMFILES\OpenBAO\bao.exe",
            "${env:PROGRAMFILES(X86)}\OpenBAO\bao.exe"
        )

        foreach ($Path in $CommonPaths) {
            if (Test-Path $Path) {
                $BaoCmd = $Path
                break
            }
        }
    }

    if ($BaoCmd) {
        Write-Host ""
        Write-Host "Server Status:" -ForegroundColor Yellow

        # Set environment variables for BAO client
        $env:BAO_ADDR = "http://127.0.0.1:8200"
        $env:BAO_TOKEN = "dev-only-token-change-me"

        try {
            $StatusOutput = & $BaoCmd status 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host $StatusOutput -ForegroundColor Green
                Write-Host ""
                Write-Host "Health Check: OK" -ForegroundColor Green
            } else {
                Write-Host "Health Check: Server not responding to API calls" -ForegroundColor Red
                Write-Host "Output: $StatusOutput" -ForegroundColor Gray
            }
        } catch {
            Write-Host "Health Check: Error connecting to server" -ForegroundColor Red
            Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Gray
        }
    }

    # Show recent log entries
    if (Test-Path $LogFile) {
        Write-Host ""
        Write-Host "Recent log entries:" -ForegroundColor Yellow
        Write-Host "-------------------" -ForegroundColor Yellow
        try {
            $LogContent = Get-Content $LogFile -Tail 5 -ErrorAction SilentlyContinue
            if ($LogContent) {
                $LogContent | ForEach-Object { Write-Host $_ -ForegroundColor Gray }
            } else {
                Write-Host "No recent log entries" -ForegroundColor Gray
            }
        } catch {
            Write-Host "No recent log entries" -ForegroundColor Gray
        }
    }

} catch {
    Write-Host "Status: Not running (process $OpenBaoPid not found)" -ForegroundColor Yellow
    Write-Host "Cleaning up stale PID file..." -ForegroundColor Gray
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}