# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# remove-canary.ps1 -- run by the sysmanage-canary MSI (Phase 22.9) before its
# files are removed: stops and deletes the SysManageCanary service and the
# Python it unpacked.  The configuration in ProgramData is kept.
#
# -Upgrading carries [UPGRADINGPRODUCTCODE], which is set only when a newer
# version is replacing this one.  Then the service's start type and whether
# it was running are written down, so the new install can restore them.

param([string]$Upgrading = "")

$ErrorActionPreference = "Continue"

$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $env:ProgramData "SysManage"
$StateFile = Join-Path $DataDir "canary-service-state.txt"
$ServiceName = "SysManageCanary"
$Nssm = Join-Path $InstallDir "nssm.exe"

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service) {
    if ($Upgrading) {
        "$($service.StartType) $($service.Status)" | Out-File -FilePath $StateFile -Encoding ASCII
    }
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    }
    if (Test-Path $Nssm) {
        & $Nssm remove $ServiceName confirm 2>&1 | Out-Null
    } else {
        sc.exe delete $ServiceName | Out-Null
    }
}

# Unpacked by install-canary.ps1, so the MSI does not know about them.
foreach ($item in @("python", "lib", "sysmanage-canary.cmd")) {
    $path = Join-Path $InstallDir $item
    if (Test-Path $path) { Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue }
}
exit 0
