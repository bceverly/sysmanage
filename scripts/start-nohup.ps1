# SysManage Server Startup Script - Background mode (like Unix nohup)
# Replicates start.sh behavior on Windows

Write-Host "Starting SysManage Server..." -ForegroundColor Green

# Get script and project directories
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Create logs directory if it doesn't exist
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

# Activate virtual environment if it exists
$venvPath = $null
if (Test-Path ".venv\Scripts\pythonw.exe") {
    Write-Host "Using virtual environment..." -ForegroundColor Gray
    $pythonExe = ".venv\Scripts\pythonw.exe"
} elseif (Test-Path "venv\Scripts\pythonw.exe") {
    Write-Host "Using virtual environment..." -ForegroundColor Gray
    $pythonExe = "venv\Scripts\pythonw.exe"
} else {
    # Fall back to pythonw.exe (no console window) or python.exe
    if (Get-Command "pythonw.exe" -ErrorAction SilentlyContinue) {
        $pythonExe = "pythonw.exe"
    } else {
        $pythonExe = "python.exe"
    }
}

# Start backend using pythonw.exe (no console window)
Write-Host "Starting backend API server..." -ForegroundColor Cyan
$env:PYTHONPATH = $ProjectRoot

# Create a simple wrapper batch that runs pythonw
$backendBatch = @"
@echo off
cd /d "$ProjectRoot"
set PYTHONPATH=$ProjectRoot
"$pythonExe" -m backend.main
"@
$backendBatch | Out-File "$ProjectRoot\logs\start_backend.bat" -Encoding ASCII

# Start the batch file with Start-Process - pythonw won't show a window
$backendProcess = Start-Process -FilePath "$pythonExe" `
    -ArgumentList "-m", "backend.main" `
    -WorkingDirectory "$ProjectRoot" `
    -RedirectStandardOutput "$ProjectRoot\logs\backend.log" `
    -RedirectStandardError "$ProjectRoot\logs\backend.err" `
    -PassThru

Write-Host "Backend started (PID: $($backendProcess.Id))" -ForegroundColor Gray
$backendProcess.Id | Out-File "$ProjectRoot\logs\backend.pid" -Encoding ASCII

# Wait a bit for backend
Start-Sleep -Seconds 3

# Start frontend in background (like nohup)
Write-Host "Starting frontend web UI..." -ForegroundColor Cyan
if ((Test-Path "frontend") -and (Test-Path "frontend\package.json")) {
    # Check for npm dependencies
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "Installing frontend dependencies..." -ForegroundColor Gray
        Set-Location "$ProjectRoot\frontend"
        npm install | Out-Null
        Set-Location $ProjectRoot
    }

    # Start npm in a new minimized window (visible but out of the way)
    # Npm needs an interactive console to stay running on Windows
    $frontendProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "start" `
        -WorkingDirectory "$ProjectRoot\frontend" `
        -WindowStyle Minimized `
        -PassThru

    Write-Host "Frontend started in minimized window (PID: $($frontendProcess.Id))" -ForegroundColor Gray
    $frontendProcess.Id | Out-File "$ProjectRoot\logs\frontend.pid" -Encoding ASCII

    # Wait a bit for frontend
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "✅ SysManage Server is running in background!" -ForegroundColor Green
Write-Host ""
Write-Host "Services:" -ForegroundColor White
Write-Host "  Backend API:      http://localhost:8080" -ForegroundColor Cyan
Write-Host "  Frontend UI:      http://localhost:3000" -ForegroundColor Cyan
Write-Host "  API Docs:         http://localhost:8080/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs:" -ForegroundColor White
Write-Host "  Backend:       Get-Content logs\backend.log -Tail 20 -Wait" -ForegroundColor Gray
Write-Host "  Frontend:      Get-Content logs\frontend.log -Tail 20 -Wait" -ForegroundColor Gray
Write-Host ""
Write-Host "Background jobs:" -ForegroundColor White
Write-Host "  List jobs:     Get-Job" -ForegroundColor Gray
Write-Host "  Stop jobs:     Get-Job | Stop-Job; Get-Job | Remove-Job" -ForegroundColor Gray
Write-Host ""
Write-Host "Services are running in PowerShell background jobs." -ForegroundColor Green
Write-Host "Your window will NOT be affected." -ForegroundColor Green
Write-Host ""
