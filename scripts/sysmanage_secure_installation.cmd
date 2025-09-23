@echo off
:: SysManage Secure Installation Wrapper (Batch)
:: Handles privilege elevation and virtual environment setup on Windows
:: Usage: scripts\sysmanage_secure_installation.cmd

setlocal enabledelayedexpansion

:: Function to check if running as Administrator
:: Uses fsutil which requires admin privileges - if it fails, we're not admin
fsutil dirty query %systemdrive% >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo =======================================
    echo ERROR: Administrator Privileges Required
    echo =======================================
    echo.
    echo This script requires Administrator privileges to run properly.
    echo.
    echo To run as Administrator:
    echo   1. Right-click on Command Prompt
    echo   2. Select 'Run as Administrator'
    echo   3. Navigate to your project directory:
    echo      cd "%PROJECT_ROOT%"
    echo   4. Run the script:
    echo      scripts\sysmanage_secure_installation.cmd
    echo.
    exit /b 1
)

:: Get script directory and project root
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\"
set "PYTHON_SCRIPT=%SCRIPT_DIR%_sysmanage_secure_installation.py"

:: Function to find the Python interpreter
set "VENV_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    set "PYTHON_BIN=%VENV_PYTHON%"
) else (
    echo Error: Virtual environment not found at %PROJECT_ROOT%.venv
    echo Please run 'make install-dev' first to set up the environment.
    exit /b 1
)

:: Verify the Python script exists
if not exist "%PYTHON_SCRIPT%" (
    echo Error: Python script not found at %PYTHON_SCRIPT%
    exit /b 1
)

echo Running SysManage secure installation with Administrator privileges...
echo Python: %PYTHON_BIN%
echo Script: %PYTHON_SCRIPT%
echo.

:: Execute the Python script with any additional arguments
"%PYTHON_BIN%" "%PYTHON_SCRIPT%" %*

:: Check the exit code
if %errorlevel% neq 0 (
    echo Python script exited with code %errorlevel%
    exit /b %errorlevel%
)

endlocal