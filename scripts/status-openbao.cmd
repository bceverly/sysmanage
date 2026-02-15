@echo off
REM OpenBAO Development Server Status Script (CMD)
REM Checks the status of the OpenBAO development server

setlocal enabledelayedexpansion

if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help
if "%1"=="/?" goto :show_help

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "PID_FILE=%PROJECT_DIR%\.openbao.pid"
set "LOG_FILE=%PROJECT_DIR%\logs\openbao.log"

echo OpenBAO Status Check
echo ====================

REM Check if PID file exists
if not exist "%PID_FILE%" (
    echo Status: Not running (no PID file)
    exit /b 0
)

REM Read PID
set /p PID=<"%PID_FILE%"

REM Check if process is running
tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul
if !errorlevel! equ 0 (
    echo Status: Running (PID %PID%)
    echo Server URL: http://127.0.0.1:8200

    REM Try to get server status if bao command is available
    REM OPENBAO_BIN environment variable takes priority if set
    set "BAO_CMD="

    if defined OPENBAO_BIN (
        if exist "%OPENBAO_BIN%" (
            set "BAO_CMD=%OPENBAO_BIN%"
            goto :check_status
        )
    )

    REM Check for bao in PATH
    where bao >nul 2>&1
    if !errorlevel! equ 0 (
        set "BAO_CMD=bao"
        goto :check_status
    )

    REM Check for bao.exe in common locations
    if exist "%USERPROFILE%\AppData\Local\bin\bao.exe" (
        set "BAO_CMD=%USERPROFILE%\AppData\Local\bin\bao.exe"
        goto :check_status
    )

    if exist "%PROGRAMFILES%\OpenBAO\bao.exe" (
        set "BAO_CMD=%PROGRAMFILES%\OpenBAO\bao.exe"
        goto :check_status
    )

    if defined ProgramFiles(x86) (
        if exist "%ProgramFiles(x86)%\OpenBAO\bao.exe" (
            set "BAO_CMD=%ProgramFiles(x86)%\OpenBAO\bao.exe"
            goto :check_status
        )
    )

    :check_status
    if defined BAO_CMD (
        echo.
        echo Server Status:

        REM Set environment variables for BAO client
        set "BAO_ADDR=http://127.0.0.1:8200"
        set "BAO_TOKEN=dev-only-token-change-me"

        "!BAO_CMD!" status >nul 2>&1
        if !errorlevel! equ 0 (
            "!BAO_CMD!" status
            echo.
            echo Health Check: OK
        ) else (
            echo Health Check: Server not responding to API calls
        )
    )

    REM Show recent log entries
    if exist "%LOG_FILE%" (
        echo.
        echo Recent log entries:
        echo -------------------
        REM Show last 5 lines of log file (simplified approach)
        for /f "skip=1 delims=" %%i in ('wc -l "%LOG_FILE%" 2^>nul') do set "TOTAL_LINES=%%i"
        if defined TOTAL_LINES (
            set /a START_LINE=!TOTAL_LINES!-4
            if !START_LINE! lss 1 set START_LINE=1
            more +!START_LINE! "%LOG_FILE%" 2>nul
        ) else (
            REM Fallback: show last few lines using more
            echo Showing recent log entries...
            more "%LOG_FILE%" | find /v "" | more +20
        )
    )
) else (
    echo Status: Not running (process %PID% not found)
    echo Cleaning up stale PID file...
    del "%PID_FILE%" 2>nul
)

exit /b 0

:show_help
echo OpenBAO Development Server Status Script
echo Usage: status-openbao.cmd
echo.
echo Checks the status of the OpenBAO development server
exit /b 0