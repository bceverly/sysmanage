@echo off
echo Running SysManage Security Configuration Migration...
echo.
python "%~dp0migrate-security-config.py" --jwt-only
echo.
echo Migration completed. Press any key to close this window...
pause >nul