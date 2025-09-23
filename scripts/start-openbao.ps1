# OpenBAO Development Server Start Script (PowerShell)
# Starts OpenBAO in development mode for sysmanage integration

param(
    [switch]$Help
)

if ($Help) {
    Write-Host "OpenBAO Development Server Start Script"
    Write-Host "Usage: .\start-openbao.ps1"
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
    if ($ExistingPid -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
        Write-Host "OpenBAO is already running with PID $ExistingPid" -ForegroundColor Yellow
        exit 0
    } else {
        Write-Host "Stale PID file found, removing..." -ForegroundColor Yellow
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
}

# Find OpenBAO or Vault binary
$BaoCmd = $null
$BaoCmdPath = $null

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

Write-Host "Starting OpenBAO development server..." -ForegroundColor Cyan
Write-Host "Log file: $LogFile" -ForegroundColor Gray
Write-Host "PID file: $PidFile" -ForegroundColor Gray

# Prepare arguments for OpenBAO
$BaoArgs = @(
    "server",
    "-dev",
    "-dev-root-token-id=dev-only-token-change-me",
    "-dev-listen-address=127.0.0.1:8200",
    "-log-level=info"
)

try {
    # Start OpenBAO using proper background execution (similar to sysmanage-agent approach)
    $ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
    $ProcessInfo.FileName = $BaoCmd
    $ProcessInfo.Arguments = $BaoArgs -join ' '
    $ProcessInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $ProcessInfo.CreateNoWindow = $true
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.RedirectStandardOutput = $true
    $ProcessInfo.RedirectStandardError = $true

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $ProcessInfo

    # Register event handlers for output redirection
    $OutputHandler = {
        if ($EventArgs.Data) {
            Add-Content -Path $LogFile -Value $EventArgs.Data
        }
    }

    $ErrorHandler = {
        if ($EventArgs.Data) {
            Add-Content -Path "${LogFile}.err" -Value $EventArgs.Data
        }
    }

    Register-ObjectEvent -InputObject $Process -EventName OutputDataReceived -Action $OutputHandler | Out-Null
    Register-ObjectEvent -InputObject $Process -EventName ErrorDataReceived -Action $ErrorHandler | Out-Null

    # Start the process
    $Process.Start() | Out-Null
    $Process.BeginOutputReadLine()
    $Process.BeginErrorReadLine()

    # Save PID
    $Process.Id | Out-File -FilePath $PidFile -Encoding ascii

    # Wait a moment for startup
    Start-Sleep -Seconds 2

    # Check if it started successfully
    if ($Process.HasExited) {
        Write-Host "Error: OpenBAO failed to start" -ForegroundColor Red
        Write-Host "Check log file: $LogFile" -ForegroundColor Yellow
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        exit 1
    }

    Write-Host "OpenBAO started successfully with PID $($Process.Id)" -ForegroundColor Green
    Write-Host "Server URL: http://127.0.0.1:8200" -ForegroundColor Cyan
    Write-Host "Root token: dev-only-token-change-me" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To stop OpenBAO: make stop-openbao" -ForegroundColor Gray
    Write-Host "To check status: make status-openbao" -ForegroundColor Gray

} catch {
    Write-Host "Error starting OpenBAO: $($_.Exception.Message)" -ForegroundColor Red
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    exit 1
}