@echo off
rem SysManage Server Startup Script - CMD Version
rem Starts both the backend API server and frontend web UI

echo Starting SysManage Server...
echo DEBUG: Script started

rem Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
echo DEBUG: Script dir is %SCRIPT_DIR%
rem Change to the project root directory (parent of scripts directory)
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
echo DEBUG: Project root is %PROJECT_ROOT%
cd /d "%PROJECT_ROOT%"
echo DEBUG: Changed to project root directory

rem Create logs directory if it doesn't exist
if not exist "logs" mkdir logs
echo DEBUG: Created logs directory

rem Function to get configuration value using Python
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=3000"
set "WEBUI_HOST=localhost"
echo DEBUG: Set default ports

rem Try to read configuration from YAML files
echo DEBUG: About to read YAML config
python -c "import yaml; import sys; import os; config_file = '/etc/sysmanage.yaml' if os.path.exists('/etc/sysmanage.yaml') else 'sysmanage-dev.yaml' if os.path.exists('sysmanage-dev.yaml') else None; config = yaml.safe_load(open(config_file)) if config_file else {}; print(config.get('api', {}).get('port', 8080))" > temp_port.txt
echo DEBUG: Python command returned errorlevel %errorlevel%
if exist temp_port.txt (
    echo DEBUG: temp_port.txt exists
    echo DEBUG: Contents of temp_port.txt:
    type temp_port.txt
    for /f %%i in (temp_port.txt) do (
        echo DEBUG: Setting BACKEND_PORT to %%i
        set "BACKEND_PORT=%%i"
    )
    echo DEBUG: BACKEND_PORT is now %BACKEND_PORT%
    del temp_port.txt
) else (
    echo DEBUG: temp_port.txt does not exist
)

echo DEBUG: About to read frontend port
python -c "import yaml; import sys; import os; config_file = '/etc/sysmanage.yaml' if os.path.exists('/etc/sysmanage.yaml') else 'sysmanage-dev.yaml' if os.path.exists('sysmanage-dev.yaml') else None; config = yaml.safe_load(open(config_file)) if config_file else {}; print(config.get('webui', {}).get('port', 3000))" > temp_frontend_port.txt
echo DEBUG: Frontend Python command returned errorlevel %errorlevel%
if exist temp_frontend_port.txt (
    echo DEBUG: temp_frontend_port.txt exists  
    for /f %%i in (temp_frontend_port.txt) do set "FRONTEND_PORT=%%i"
    del temp_frontend_port.txt
    echo DEBUG: Set FRONTEND_PORT to %FRONTEND_PORT%
) else (
    echo DEBUG: temp_frontend_port.txt does not exist
)

echo DEBUG: About to read webui host
python -c "import yaml; import sys; import os; config_file = '/etc/sysmanage.yaml' if os.path.exists('/etc/sysmanage.yaml') else 'sysmanage-dev.yaml' if os.path.exists('sysmanage-dev.yaml') else None; config = yaml.safe_load(open(config_file)) if config_file else {}; print(config.get('webui', {}).get('host', 'localhost'))" > temp_host.txt
echo DEBUG: Host Python command returned errorlevel %errorlevel%
if exist temp_host.txt (
    echo DEBUG: temp_host.txt exists  
    for /f %%i in (temp_host.txt) do set "WEBUI_HOST=%%i"
    del temp_host.txt
    echo DEBUG: Set WEBUI_HOST to %WEBUI_HOST%
) else (
    echo DEBUG: temp_host.txt does not exist
)
echo DEBUG: Finished reading config, continuing...

rem Skip function definitions during normal execution
goto main

rem Function to check if a port is in use
:check_port
netstat -an | findstr ":%1" | findstr "LISTENING" >NUL 2>&1
exit /b %errorlevel%

rem Function to wait for service to be ready
:wait_for_service
set "port=%1"
set "service_name=%2"
set "max_attempts=30"
set "attempt=0"

echo Waiting for %service_name% to start on port %port%...
:wait_loop
if %attempt% geq %max_attempts% (
    echo.
    echo WARNING: %service_name% may not have started within 30 seconds
    echo    But it might actually be running. Check logs: type logs\backend.log
    exit /b 1
)

call :check_port %port%
if %errorlevel% equ 0 (
    echo.
    echo [OK] %service_name% is ready on port %port%!
    exit /b 0
)

timeout /t 1 >NUL
set /a attempt+=1
set /p "=." <NUL

rem Show debug info every 10 attempts
set /a "debug_check=%attempt% %% 10"
if %debug_check% equ 0 (
    echo.
    echo WARNING: Still waiting... (attempt %attempt%/%max_attempts%)
)

goto wait_loop

:main
echo DEBUG: Starting main execution
rem Stop any existing processes first
echo DEBUG: About to stop existing processes
echo Stopping any existing SysManage processes...
if exist "stop_simple.cmd" (
    echo DEBUG: Calling stop_simple.cmd
    call stop_simple.cmd
    echo DEBUG: stop_simple.cmd completed with errorlevel %errorlevel%
    timeout /t 2 >NUL
) else if exist "scripts\stop.cmd" (
    echo DEBUG: Calling scripts\stop.cmd
    call scripts\stop.cmd
    echo DEBUG: scripts\stop.cmd completed with errorlevel %errorlevel%
    timeout /t 2 >NUL
) else (
    echo WARNING: No stop script found, continuing anyway...
)
echo DEBUG: Finished stopping processes

rem Start the backend API server
echo DEBUG: About to start backend
echo Starting backend API server...
echo DEBUG: Checking if backend\main.py exists
if exist "backend\main.py" (
    echo DEBUG: backend\main.py found
    rem Check if virtual environment exists and activate it
    echo DEBUG: Checking for virtual environment
    if exist ".venv\Scripts\activate.bat" (
        echo DEBUG: Found .venv, activating
        echo Activating virtual environment...
        call .venv\Scripts\activate.bat
    ) else if exist "venv\Scripts\activate.bat" (
        echo DEBUG: Found venv, activating
        echo Activating virtual environment...
        call venv\Scripts\activate.bat
    ) else (
        echo DEBUG: No virtual environment found
    )
    
    rem Start the backend using the main.py configuration
    echo DEBUG: About to start backend process
    echo Starting backend on port %BACKEND_PORT%...
    start /b "" python -m backend.main > logs\backend.log 2>&1
    echo DEBUG: Backend process started
    
    rem Wait for backend to be ready
    echo DEBUG: About to wait for backend service
    call :wait_for_service %BACKEND_PORT% "Backend API"
    echo DEBUG: wait_for_service returned %errorlevel%
    if %errorlevel% neq 0 (
        echo WARNING: Backend API detection failed, but continuing...
        echo    The backend may actually be running. Check logs: type logs\backend.log
        echo    Continuing with frontend startup...
    )
    echo DEBUG: Backend wait completed
) else (
    echo DEBUG: backend\main.py not found
    echo ERROR: backend\main.py not found
    pause
    exit /b 1
)

rem Start the frontend web UI
echo DEBUG: About to start frontend
echo Starting frontend web UI...
echo DEBUG: Checking if frontend directory exists
if exist "frontend" (
    echo DEBUG: frontend directory found
    echo DEBUG: Checking if package.json exists
    if exist "frontend\package.json" (
        echo DEBUG: package.json found
        echo DEBUG: Changing to frontend directory
        cd frontend
        
        rem Install dependencies if node_modules doesn't exist
        echo DEBUG: Checking if node_modules exists
        if not exist "node_modules" (
            echo DEBUG: node_modules not found, installing
            echo Installing frontend dependencies...
            call npm install
            echo DEBUG: npm install completed with errorlevel %errorlevel%
        ) else (
            echo DEBUG: node_modules already exists
        )
        
        rem Start the React development server
        echo DEBUG: Setting environment variables
        echo Starting frontend on port %FRONTEND_PORT%...
        set "FORCE_HTTP=true"
        set "VITE_HOST=%WEBUI_HOST%"
        set "VITE_PORT=%FRONTEND_PORT%"
        echo DEBUG: About to start npm start
        start /b "" npm start > ..\logs\frontend.log 2>&1
        echo DEBUG: npm start command issued
        
        echo DEBUG: Returning to main directory
        cd ..
        echo DEBUG: Back in main directory
        
        rem Wait for frontend to be ready
        echo DEBUG: About to wait for frontend service
        call :wait_for_service %FRONTEND_PORT% "Frontend Web UI"
        echo DEBUG: frontend wait_for_service returned %errorlevel%
        if %errorlevel% neq 0 (
            echo WARNING: Frontend Web UI may not have started properly
        )
        echo DEBUG: Frontend wait completed
    ) else (
        echo DEBUG: package.json not found
        echo ERROR: frontend\package.json not found
    )
) else (
    echo DEBUG: frontend directory not found
    echo ERROR: frontend directory not found
)

echo DEBUG: Starting final output
echo.
echo [OK] SysManage Server is successfully running!
echo.
echo Services:

rem Generate URLs based on configured host
set "BACKEND_URL=http://localhost:%BACKEND_PORT%"
set "FRONTEND_URL=http://%WEBUI_HOST%:%FRONTEND_PORT%"
set "WS_URL=ws://localhost:%BACKEND_PORT%/agent/connect"
set "API_DOCS_URL=http://localhost:%BACKEND_PORT%/docs"

echo   Backend API:      %BACKEND_URL%
echo   Agent WebSocket:  %WS_URL%
echo   Frontend UI:      %FRONTEND_URL%
echo   API Docs:        %API_DOCS_URL%

echo.
echo Logs:
echo   Backend:       type logs\backend.log
echo   Frontend:      type logs\frontend.log
echo.
echo To stop the server: scripts\stop.cmd
echo.
echo Services are now running in the background.