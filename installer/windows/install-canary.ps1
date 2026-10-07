# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# install-canary.ps1 -- run by the sysmanage-canary MSI (Phase 22.9) as
# SYSTEM after the files are copied.  Unpacks the bundled Python, installs the
# bundled wheels into it (offline), unpacks the canary library, creates the
# configuration from the example if there is none, and registers the
# SysManageCanary service through NSSM, running as LOCAL SERVICE.
#
# The Python is the canary's OWN copy, never the server's virtualenv: the
# watcher has to keep working when the thing it watches is broken.

# Continue, with every cmdlet below on -ErrorAction Stop and every native
# command checked by exit code: under "Stop", Windows PowerShell 5.1 turns
# anything a native program writes to stderr (pip's warnings, nssm's notes)
# into a fatal error.
$ErrorActionPreference = "Continue"

$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $env:ProgramData "SysManage"
$LogDir = Join-Path $DataDir "canary"
$Config = Join-Path $DataDir "sysmanage-canary.yaml"
$StateFile = Join-Path $DataDir "canary-service-state.txt"
$ServiceName = "SysManageCanary"
$Nssm = Join-Path $InstallDir "nssm.exe"
$PyDir = Join-Path $InstallDir "python"
$LibDir = Join-Path $InstallDir "lib"
$Python = Join-Path $PyDir "python.exe"

New-Item -ItemType Directory -Force -Path $DataDir, $LogDir -ErrorAction Stop | Out-Null
$InstallLog = Join-Path $LogDir "install.log"

function Write-Log {
    param([string]$Message)
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $Message" | Out-File -FilePath $InstallLog -Append
    Write-Host $Message
}

# Well-known SIDs, not names: "LOCAL SERVICE" and "Administrators" are
# translated on non-English Windows, and icacls fails on the English name there.
$SidSystem = "*S-1-5-18"
$SidAdmins = "*S-1-5-32-544"
$SidLocalService = "*S-1-5-19"

try {
    Write-Log "=== Installing sysmanage-canary into $InstallDir ==="

    # A service left by an interrupted install holds python.exe open.
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        Write-Log "Removing the existing $ServiceName service first"
        & $Nssm stop $ServiceName 2>&1 | Out-Null
        & $Nssm remove $ServiceName confirm 2>&1 | Out-Null
    }

    $ProgressPreference = 'SilentlyContinue'
    foreach ($dir in @($PyDir, $LibDir)) {
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir -ErrorAction Stop }
    }
    Expand-Archive -Path (Join-Path $InstallDir "canary-python.zip") -DestinationPath $PyDir -Force -ErrorAction Stop
    Expand-Archive -Path (Join-Path $InstallDir "canary.zip") -DestinationPath $LibDir -Force -ErrorAction Stop
    $WheelDir = Join-Path $env:TEMP "sysmanage-canary-wheels"
    if (Test-Path $WheelDir) { Remove-Item -Recurse -Force $WheelDir -ErrorAction Stop }
    Expand-Archive -Path (Join-Path $InstallDir "canary-wheels.zip") -DestinationPath $WheelDir -Force -ErrorAction Stop
    $ProgressPreference = 'Continue'
    if (-not (Test-Path $Python)) { throw "python.exe missing after extracting canary-python.zip" }

    $wheels = @(Get-ChildItem (Join-Path $WheelDir "*.whl") | ForEach-Object { $_.FullName })
    Write-Log "Installing $($wheels.Count) bundled wheels (offline)"
    & $Python -m pip install --no-index --no-cache-dir --disable-pip-version-check `
        --find-links $WheelDir @wheels 2>&1 | Out-File -FilePath $InstallLog -Append
    if ($LASTEXITCODE -ne 0) { throw "pip could not install the bundled wheels (see $InstallLog)" }
    Remove-Item -Recurse -Force $WheelDir

    # Nothing under Program Files is writable by the service; the import cache
    # is not wanted anyway (the service runs python -B).
    $env:PYTHONPATH = $LibDir
    $version = & $Python -B -m sysmanage_canary --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "the canary does not start: $version" }
    Write-Log "sysmanage-canary $version unpacked"

    # The command line for operators (--check-config, --test-email, --once).
    $Cmd = Join-Path $InstallDir "sysmanage-canary.cmd"
    @(
        "@echo off",
        "set `"PYTHONPATH=$LibDir`"",
        "`"$Python`" -B -m sysmanage_canary %*"
    ) | Set-Content -Path $Cmd -Encoding ASCII -ErrorAction Stop

    if (-not (Test-Path $Config)) {
        Copy-Item (Join-Path $InstallDir "sysmanage-canary.yaml.example") $Config -ErrorAction Stop
        Write-Log "Created $Config from the example"
    }
    # It holds the database and mail passwords: SYSTEM, Administrators, and
    # the service (read) only.
    icacls $Config /inheritance:r /grant:r "${SidSystem}:F" "${SidAdmins}:F" "${SidLocalService}:R" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls could not restrict $Config" }
    icacls $LogDir /grant "${SidLocalService}:(OI)(CI)M" | Out-Null

    # PATH is set for the service, not inherited: on ARM64 pure-Python psycopg
    # finds libpq.dll by searching PATH.
    $LibpqDir = Join-Path $InstallDir "libpq"
    $servicePath = "$PyDir;$LibpqDir;$env:SystemRoot\System32;$env:SystemRoot"

    Write-Log "Registering the $ServiceName service"
    & $Nssm install $ServiceName $Python "-B -m sysmanage_canary --config `"$Config`"" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "nssm install failed" }
    & $Nssm set $ServiceName DisplayName "SysManage Canary" | Out-Null
    & $Nssm set $ServiceName Description "Watches a SysManage server from the outside and emails when something stops working." | Out-Null
    & $Nssm set $ServiceName AppDirectory $LibDir | Out-Null
    & $Nssm set $ServiceName AppEnvironmentExtra "PYTHONPATH=$LibDir" "PATH=$servicePath" | Out-Null
    & $Nssm set $ServiceName ObjectName "NT AUTHORITY\LocalService" "" | Out-Null
    & $Nssm set $ServiceName AppStdout (Join-Path $LogDir "canary.log") | Out-Null
    & $Nssm set $ServiceName AppStderr (Join-Path $LogDir "canary.log") | Out-Null
    & $Nssm set $ServiceName AppRotateFiles 1 | Out-Null
    & $Nssm set $ServiceName AppRotateOnline 1 | Out-Null
    & $Nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
    & $Nssm set $ServiceName AppExit Default Restart | Out-Null
    & $Nssm set $ServiceName AppRestartDelay 30000 | Out-Null

    # An upgrade restores what the operator had; a fresh install stays on
    # manual until the configuration is filled in.
    $state = if (Test-Path $StateFile) { (Get-Content $StateFile -Raw).Trim() } else { "" }
    if ($state -like "Automatic*") {
        & $Nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
    } else {
        & $Nssm set $ServiceName Start SERVICE_DEMAND_START | Out-Null
    }
    if ($state -like "*Running") {
        Start-Service -Name $ServiceName -ErrorAction Stop
        Write-Log "Upgrade: the service was running before, started it again"
    } else {
        Write-Log "Edit $Config, then check it:"
        Write-Log "  `"$Cmd`" --config `"$Config`" --check-config"
        Write-Log "and start it: Set-Service $ServiceName -StartupType Automatic; Start-Service $ServiceName"
    }
    if (Test-Path $StateFile) { Remove-Item -Force $StateFile -ErrorAction SilentlyContinue }
    Write-Log "=== sysmanage-canary installed ==="
    exit 0
} catch {
    Write-Log "ERROR: $_"
    exit 1
}
