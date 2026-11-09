# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

#
# SysManage Server Service Launcher
#
# NSSM runs this (create-service.ps1) as the SysManage service, as
# LocalSystem.  It is the Windows form of the Linux sysmanage-openbao-init
# unit, which runs before the server on every boot: OpenBAO starts sealed
# after a restart, so this unseals it -- and rewrites the server's OpenBAO
# token -- before the server starts, so the API never starts against a
# sealed OpenBAO.  A failed unseal does not hold the server down; the
# helper's output goes to openbao-unseal.log.
#

$ErrorActionPreference = "Stop"

$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigFile = "C:\ProgramData\SysManage\sysmanage.yaml"
$OpenBaoData = "C:\ProgramData\SysManage\openbao"
$LogPath = "C:\ProgramData\SysManage\logs"

Set-Location $InstallDir

$VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Python not found in virtual environment"
    exit 1
}

$env:SYSMANAGE_CONFIG = $ConfigFile

# Only where the installer set OpenBAO up: the helper would otherwise wait
# for a listener that never comes.
$InitScript = Join-Path $InstallDir "scripts\openbao_init_unseal.py"
if ((Get-Service -Name "SysManageOpenBAO" -ErrorAction SilentlyContinue) -and (Test-Path $InitScript)) {
    $UnsealLog = Join-Path $LogPath "openbao-unseal.log"
    # "Continue" here: Windows PowerShell 5.1 turns each stderr line of a
    # native program into an ErrorRecord, which "Stop" would make fatal.
    $ErrorActionPreference = "Continue"
    try {
        Start-Service -Name "SysManageOpenBAO" -ErrorAction SilentlyContinue
        & $VenvPython $InitScript --addr "http://127.0.0.1:8200" `
            --keyfile (Join-Path $OpenBaoData "init.json") `
            --app-token-file (Join-Path $OpenBaoData "openbao-token") 2>&1 |
            ForEach-Object { "$_" } | Out-File -FilePath $UnsealLog -Append
    } catch {
        "$(Get-Date -Format o) unseal failed: $_" | Out-File -FilePath $UnsealLog -Append
    } finally {
        $ErrorActionPreference = "Stop"
    }
}

# Run the server through backend.main (not uvicorn directly): it binds
# api.host/api.port from sysmanage.yaml and sizes the workers for this
# machine (Phase 22.2).
& $VenvPython -m backend.main
exit $LASTEXITCODE
