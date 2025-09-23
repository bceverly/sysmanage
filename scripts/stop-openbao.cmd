@echo off
REM OpenBAO Development Server Stop Script (CMD)
REM Stops the OpenBAO development server

setlocal enabledelayedexpansion

if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help
if "%1"=="/?" goto :show_help

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "PID_FILE=%PROJECT_DIR%\.openbao.pid"

REM Check if PID file exists
if not exist "%PID_FILE%" (
    echo OpenBAO is not running (no PID file found)
    exit /b 0
)

REM Read PID
set /p PID=<"%PID_FILE%"

REM Check if process is actually running
tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul
if !errorlevel! neq 0 (
    echo OpenBAO process (PID %PID%) is not running, cleaning up PID file
    del "%PID_FILE%" 2>nul
    exit /b 0
)

echo Stopping OpenBAO (PID %PID%)...

REM Try graceful shutdown first using taskkill
taskkill /pid %PID% >nul 2>&1
if !errorlevel! equ 0 (
    REM Wait up to 10 seconds for graceful shutdown
    set /a WAIT_COUNT=0
    :wait_loop
    if !WAIT_COUNT! geq 10 goto :force_kill

    timeout /t 1 /nobreak >nul
    tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul
    if !errorlevel! neq 0 (
        echo OpenBAO stopped gracefully
        del "%PID_FILE%" 2>nul
        exit /b 0
    )

    set /a WAIT_COUNT+=1
    goto :wait_loop

    :force_kill
    REM If still running, force kill
    echo Graceful shutdown timed out, force killing...
    taskkill /f /pid %PID% >nul 2>&1
    if !errorlevel! equ 0 (
        echo OpenBAO force stopped
    ) else (
        echo Failed to stop OpenBAO process
        exit /b 1
    )
) else (
    echo Failed to send stop signal to OpenBAO process
    exit /b 1
)

REM Clean up PID file
del "%PID_FILE%" 2>nul
echo OpenBAO stopped

exit /b 0

:show_help
echo OpenBAO Development Server Stop Script
echo Usage: stop-openbao.cmd
echo.
echo Stops the OpenBAO development server
exit /b 0