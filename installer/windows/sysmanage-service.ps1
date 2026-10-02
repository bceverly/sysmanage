# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

# Run the server through backend.main (not uvicorn directly): it binds
# api.host/api.port from sysmanage.yaml and sizes the workers for this
# machine (Phase 22.2).
& $VenvPython -m backend.main
