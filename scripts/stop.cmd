@echo off
rem SysManage Server Stop Script - CMD Version
rem Stops both the backend API server and frontend web UI

echo Stopping SysManage Server...

rem Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
rem Change to the project root directory (parent of scripts directory)
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

rem Function to get configuration value using Python
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=3000"

rem Try to read configuration from YAML files
python -c "import yaml; import sys; import os; config_file = '/etc/sysmanage.yaml' if os.path.exists('/etc/sysmanage.yaml') else 'sysmanage-dev.yaml' if os.path.exists('sysmanage-dev.yaml') else None; config = yaml.safe_load(open(config_file)) if config_file else {}; print(config.get('api', {}).get('port', 8080))" > temp_stop_port.txt 2>nul
if exist temp_stop_port.txt (
    for /f %%i in (temp_stop_port.txt) do set "BACKEND_PORT=%%i"
    del temp_stop_port.txt
)

python -c "import yaml; import sys; import os; config_file = '/etc/sysmanage.yaml' if os.path.exists('/etc/sysmanage.yaml') else 'sysmanage-dev.yaml' if os.path.exists('sysmanage-dev.yaml') else None; config = yaml.safe_load(open(config_file)) if config_file else {}; print(config.get('webui', {}).get('port', 3000))" > temp_stop_frontend.txt 2>nul
if exist temp_stop_frontend.txt (
    for /f %%i in (temp_stop_frontend.txt) do set "FRONTEND_PORT=%%i"
    del temp_stop_frontend.txt
)

rem Skip function definitions during normal execution
goto main

rem Function to kill process by PID file
:kill_by_pidfile
set "pidfile=%1"
set "service_name=%2"
if exist "%pidfile%" (
    set /p pid=<"%pidfile%"
    if defined pid (
        echo Stopping %service_name% (PID: %pid%)...
        taskkill /PID %pid% /F >nul 2>&1
        timeout /t 2 >nul
    )
    del "%pidfile%" >nul 2>&1
)
goto :eof

rem Function to kill processes by name pattern
:kill_by_pattern
set "pattern=%1"
set "service_name=%2"
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq %pattern%" /NH 2^>nul ^| findstr /V "INFO:"') do (
    if defined %%i (
        echo Stopping %service_name% (PID: %%i)...
        taskkill /PID %%i /F >nul 2>&1
    )
)
goto :eof

rem Function to kill processes by port
:kill_by_port
set "port=%1"
set "service_name=%2"
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":%port% " ^| findstr "LISTENING"') do (
    if defined %%i (
        echo Killing process on port %port% (PID: %%i)...
        taskkill /PID %%i /F >nul 2>&1
    )
)
goto :eof

:main
rem Stop using PID files if they exist
if exist "logs" (
    call :kill_by_pidfile "logs\backend.pid" "Backend API"
    call :kill_by_pidfile "logs\frontend.pid" "Frontend Web UI"
)

rem Fallback: kill by process patterns
call :kill_by_pattern "python.exe" "Backend API (Python)"
call :kill_by_pattern "node.exe" "Frontend Web UI (Node)"

rem Kill any processes on the specific ports
echo Checking for processes on SysManage ports...
call :kill_by_port %BACKEND_PORT% "Backend API"
call :kill_by_port %FRONTEND_PORT% "Frontend Web UI"

rem Clean up PID files and process environment
if exist "logs" (
    del "logs\backend.pid" >nul 2>&1
    del "logs\frontend.pid" >nul 2>&1
    del "logs\processes.env" >nul 2>&1
)

rem Verify everything is stopped
timeout /t 1 >nul
netstat -ano | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul 2>&1
set "backend_running=%errorlevel%"
netstat -ano | findstr ":%FRONTEND_PORT% " | findstr "LISTENING" >nul 2>&1
set "frontend_running=%errorlevel%"

if %backend_running% neq 0 if %frontend_running% neq 0 (
    echo.
    echo [OK] SysManage Server stopped successfully!
) else (
    echo.
    echo WARNING: Some processes may still be running
    if %backend_running% equ 0 (
        echo    Backend still running on port %BACKEND_PORT%
    )
    if %frontend_running% equ 0 (
        echo    Frontend still running on port %FRONTEND_PORT%
    )
    echo    You may need to manually kill these processes
)

echo DEBUG: stop.cmd completed