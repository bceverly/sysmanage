#
# SysManage Server Service Wrapper Script
# This is not used directly - NSSM launches Python with uvicorn
# This file exists for reference only
#

$ErrorActionPreference = "Stop"

# Get installation directory
$InstallDir = "C:\Program Files\SysManage Server"
$ConfigFile = "C:\ProgramData\SysManage\sysmanage.yaml"

# Set working directory
Set-Location $InstallDir

# Find Python in venv
$VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Python not found in virtual environment"
    exit 1
}

# Set config path environment variable
$env:SYSMANAGE_CONFIG = $ConfigFile

# Run uvicorn server
& $VenvPython -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
