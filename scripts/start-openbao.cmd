@echo off
REM OpenBAO Development Server Start Script (CMD)
REM Starts OpenBAO in development mode for sysmanage integration

setlocal enabledelayedexpansion

if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help
if "%1"=="/?" goto :show_help

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "PID_FILE=%PROJECT_DIR%\.openbao.pid"
set "LOG_FILE=%PROJECT_DIR%\logs\openbao.log"

REM Ensure logs directory exists
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

REM Check if OpenBAO is already running
if exist "%PID_FILE%" (
    set /p PID=<"%PID_FILE%"
    tasklist /fi "PID eq !PID!" 2>nul | find "!PID!" >nul
    if !errorlevel! equ 0 (
        echo OpenBAO is already running with PID !PID!
        exit /b 0
    ) else (
        echo Stale PID file found, removing...
        del "%PID_FILE%" 2>nul
    )
)

REM Find OpenBAO or Vault binary
set "BAO_CMD="

REM Check for bao in PATH
where bao >nul 2>&1
if !errorlevel! equ 0 (
    set "BAO_CMD=bao"
    echo Found OpenBAO in PATH
    goto :start_server
)

REM Check for bao.exe in common locations
if exist "%USERPROFILE%\AppData\Local\bin\bao.exe" (
    set "BAO_CMD=%USERPROFILE%\AppData\Local\bin\bao.exe"
    echo Found OpenBAO at: %USERPROFILE%\AppData\Local\bin\bao.exe
    goto :start_server
)

if exist "%PROGRAMFILES%\OpenBAO\bao.exe" (
    set "BAO_CMD=%PROGRAMFILES%\OpenBAO\bao.exe"
    echo Found OpenBAO at: %PROGRAMFILES%\OpenBAO\bao.exe
    goto :start_server
)

if defined ProgramFiles(x86) (
    if exist "%ProgramFiles(x86)%\OpenBAO\bao.exe" (
        set "BAO_CMD=%ProgramFiles(x86)%\OpenBAO\bao.exe"
        echo Found OpenBAO at: %ProgramFiles(x86)%\OpenBAO\bao.exe
        goto :start_server
    )
)

REM Try vault as fallback
where vault >nul 2>&1
if !errorlevel! equ 0 (
    set "BAO_CMD=vault"
    echo Note: Using 'vault' as fallback (OpenBAO not found)
    goto :start_server
)

echo Warning: OpenBAO/Vault not found in PATH or common locations
echo SysManage will run with vault.enabled=false in config
echo To install OpenBAO, run: make install-dev
echo.
echo Continuing without OpenBAO/Vault...
exit /b 0

:start_server
echo Starting OpenBAO server...
echo Log file: %LOG_FILE%
echo PID file: %PID_FILE%

REM Check if production config exists
set "VAULT_CONFIG=%PROJECT_DIR%\openbao.hcl"
set "VAULT_CREDS=%PROJECT_DIR%\.vault_credentials"

if exist "%VAULT_CONFIG%" if exist "%VAULT_CREDS%" (
    echo Starting OpenBAO in production mode with persistent storage...
    set "BAO_ARGS=server -config=%VAULT_CONFIG%"
    set "PRODUCTION_MODE=1"
) else (
    echo Production config not found, starting in development mode...
    set "BAO_ARGS=server -dev -dev-root-token-id=dev-only-token-change-me -dev-listen-address=127.0.0.1:8200 -log-level=info"
    set "PRODUCTION_MODE=0"
)

REM Start OpenBAO using PowerShell with proper hidden background execution and capture PID
for /f %%i in ('powershell -WindowStyle Hidden -Command "& { $processInfo = New-Object System.Diagnostics.ProcessStartInfo; $processInfo.FileName = '%BAO_CMD%'; $processInfo.Arguments = '%BAO_ARGS%'; $processInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden; $processInfo.CreateNoWindow = $true; $processInfo.UseShellExecute = $false; $processInfo.RedirectStandardOutput = $true; $processInfo.RedirectStandardError = $true; $process = New-Object System.Diagnostics.Process; $process.StartInfo = $processInfo; $process.Start(); Start-Sleep 1; if (-not $process.HasExited) { $process.Id } }"') do set "NEW_PID=%%i"

if defined NEW_PID (
    echo !NEW_PID! > "%PID_FILE%"
    echo OpenBAO started successfully with PID !NEW_PID!
) else (
    echo Warning: Could not determine PID of started process
    echo Process started but PID tracking may not work
)

echo Server URL: http://127.0.0.1:8200

REM Display appropriate token message based on mode
if "%PRODUCTION_MODE%"=="1" (
    REM Wait for server to be ready
    timeout /t 3 /nobreak >nul

    REM Set environment for unsealing
    set "BAO_ADDR=http://127.0.0.1:8200"

    REM Read credentials and unseal if needed
    if exist "%VAULT_CREDS%" (
        for /f "tokens=2 delims==" %%a in ('findstr "^UNSEAL_KEY=" "%VAULT_CREDS%"') do set "UNSEAL_KEY=%%a"
        for /f "tokens=2 delims==" %%a in ('findstr "^ROOT_TOKEN=" "%VAULT_CREDS%"') do set "ROOT_TOKEN=%%a"

        REM Check if vault needs unsealing
        "%BAO_CMD%" status 2>&1 | findstr /C:"Sealed" | findstr /C:"true" >nul
        if !errorlevel! equ 0 (
            echo Unsealing vault...
            "%BAO_CMD%" operator unseal !UNSEAL_KEY! >nul
        )

        echo Root token: !ROOT_TOKEN! (production mode)
    ) else (
        echo Root token: [check .vault_credentials file] (production mode)
    )
) else (
    echo Root token: dev-only-token-change-me (development mode)
)
echo.
echo To stop OpenBAO: make stop-openbao
echo To check status: make status-openbao

exit /b 0

:show_help
echo OpenBAO Development Server Start Script
echo Usage: start-openbao.cmd
echo.
echo Starts OpenBAO in development mode for SysManage integration
exit /b 0