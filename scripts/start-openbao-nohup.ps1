# OpenBAO Development Server Start Script (Background mode - like nohup)
# Uses PowerShell jobs instead of Start-Process to avoid window issues

param(
    [switch]$Help
)

if ($Help) {
    Write-Host "OpenBAO Development Server Start Script"
    Write-Host "Usage: .\start-openbao-nohup.ps1"
    Write-Host ""
    Write-Host "Starts OpenBAO in development mode for SysManage integration"
    exit 0
}

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$PidFile = Join-Path $ProjectDir ".openbao.pid"
$LogFile = Join-Path $ProjectDir "logs\openbao.log"

# Ensure logs directory exists
$LogsDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

# Check if OpenBAO is already running
if (Test-Path $PidFile) {
    $ExistingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($ExistingPid -and ($ExistingPid -match '^\d+$') -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
        Write-Host "OpenBAO is already running with PID $ExistingPid" -ForegroundColor Yellow
        exit 0
    } else {
        Write-Host "Stale PID file found, removing..." -ForegroundColor Yellow
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
}

# Find OpenBAO or Vault binary
$BaoCmd = $null

# Check for bao in PATH
try {
    $BaoCmdPath = Get-Command "bao" -ErrorAction Stop
    $BaoCmd = "bao"
    Write-Host "Found OpenBAO in PATH: $($BaoCmdPath.Source)" -ForegroundColor Green
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
            Write-Host "Found OpenBAO at: $BaoCmd" -ForegroundColor Green
            break
        }
    }

    if (-not $BaoCmd) {
        # Try vault as fallback
        try {
            $VaultCmdPath = Get-Command "vault" -ErrorAction Stop
            $BaoCmd = "vault"
            Write-Host "Note: Using 'vault' as fallback (OpenBAO not found)" -ForegroundColor Yellow
            Write-Host "Found Vault in PATH: $($VaultCmdPath.Source)" -ForegroundColor Yellow
        } catch {
            Write-Host "Warning: OpenBAO/Vault not found in PATH or common locations" -ForegroundColor Red
            Write-Host "SysManage will run with vault.enabled=false in config" -ForegroundColor Yellow
            Write-Host "To install OpenBAO, run: make install-dev" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Continuing without OpenBAO/Vault..." -ForegroundColor Yellow
            exit 0  # Exit gracefully so make start continues
        }
    }
}

Write-Host "Starting OpenBAO server..." -ForegroundColor Cyan
Write-Host "Log file: $LogFile" -ForegroundColor Gray

# Check if production config exists
$VaultConfig = Join-Path $ProjectDir "openbao.hcl"
$VaultCreds = Join-Path $ProjectDir ".vault_credentials"

if ((Test-Path $VaultConfig) -and (Test-Path $VaultCreds)) {
    Write-Host "Starting OpenBAO in production mode with persistent storage..." -ForegroundColor Green
    # Don't embed path in the arg, pass it separately
    $BaoArgs = @("server", "-config=`"$VaultConfig`"")
    $ProductionMode = $true
} else {
    Write-Host "Production config not found, starting in development mode..." -ForegroundColor Yellow
    $BaoArgs = @(
        "server",
        "-dev",
        "-dev-root-token-id=dev-only-token-change-me",
        "-dev-listen-address=127.0.0.1:8200",
        "-log-level=info"
    )
    $ProductionMode = $false
}

try {
    # For production mode with config file, we need special handling for the path
    if ($ProductionMode) {
        # Create a batch file to handle the complex quoting
        $batchFile = "$ProjectDir\logs\start_openbao.bat"
        $batchContent = @"
@echo off
cd /d "$ProjectDir"
"$BaoCmd" server "-config=$VaultConfig" > "$LogFile" 2>&1
"@
        $batchContent | Out-File $batchFile -Encoding ASCII

        # Run the batch file
        $Process = Start-Process -FilePath $batchFile `
            -WindowStyle Minimized `
            -PassThru
    } else {
        # Dev mode - no config file path with spaces
        $Process = Start-Process -FilePath $BaoCmd `
            -ArgumentList $BaoArgs `
            -WindowStyle Minimized `
            -RedirectStandardOutput $LogFile `
            -RedirectStandardError "${LogFile}.err" `
            -PassThru
    }

    # Save PID
    if ($Process -and $Process.Id) {
        $Process.Id | Out-File -FilePath $PidFile -Encoding ascii
    } else {
        Write-Host "Error: Failed to get process ID" -ForegroundColor Red
        exit 1
    }

    # Wait a moment for startup
    Start-Sleep -Seconds 2

    Write-Host "OpenBAO started successfully via VBScript wrapper" -ForegroundColor Green
    Write-Host "Server URL: http://127.0.0.1:8200" -ForegroundColor Cyan

    # Display appropriate token message based on mode
    if ($ProductionMode) {
        if (Test-Path $VaultCreds) {
            $CredsContent = Get-Content $VaultCreds
            $RootToken = ($CredsContent | Select-String "^ROOT_TOKEN=(.+)").Matches.Groups[1].Value
            Write-Host "Root token: $RootToken (production mode)" -ForegroundColor Cyan
        } else {
            Write-Host "Root token: [check .vault_credentials file] (production mode)" -ForegroundColor Cyan
        }
    } else {
        Write-Host "Root token: dev-only-token-change-me (development mode)" -ForegroundColor Cyan
    }

    Write-Host ""
    Write-Host "To stop OpenBAO: use make stop-openbao" -ForegroundColor Gray

} catch {
    Write-Host "Error starting OpenBAO: $($_.Exception.Message)" -ForegroundColor Red
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    exit 1
}
