# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

#
# Create Windows Service for SysManage Server using NSSM
#

# Top-level trap -- see sysmanage-agent's create-service.ps1 for the
# full rationale (PR #375773 winget-pkgs validation burn, 2026-05-17).
trap {
    Write-Host "WARNING: unhandled exception trapped at top level: $_"
    Write-Host "Service NOT registered but MSI install will still complete."
    exit 0
}

$ErrorActionPreference = "Continue"

# Service details
$ServiceName = "SysManageServer"
$DisplayName = "SysManage Server"
$Description = "System management and monitoring server with web interface"
$InstallDir = "C:\Program Files\SysManage Server"

# Log files
$LogPath = "C:\ProgramData\SysManage\logs"
$LogFile = Join-Path $LogPath "install.log"
$TranscriptFile = Join-Path $LogPath "create-service-transcript.log"

Start-Transcript -Path $TranscriptFile -Append

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}

$ServiceCreated = $false

Write-Log "=== Creating Windows Service using NSSM ==="

try {
    # Find Python executable in venv
    $VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        # Soft-fail: same rationale as install.ps1 / check-python.ps1.
        # When Python isn't available at MSI-install time (e.g., the
        # winget-pkgs sandboxed validation environment, where
        # check-python.ps1 can't reach python.org to install Python),
        # install.ps1 skipped the venv create.  Without a venv we
        # can't register the service to point at one -- so log the
        # situation and exit 0 cleanly rather than failing the MSI
        # with the misleading 1722/1603 chain.  The operator can
        # install Python and re-run the MSI to register the service
        # at that point.
        Write-Log ""
        Write-Log "WARNING: Virtual environment not found at $VenvPython"
        Write-Log "WARNING: install.ps1 likely soft-failed because Python 3.9+"
        Write-Log "WARNING: was not on PATH at install time."
        Write-Log "WARNING: Skipping Windows service registration."
        Write-Log ""
        Write-Log "To complete setup:"
        Write-Log "  1. Install Python 3.9+ from https://www.python.org/downloads/"
        Write-Log "  2. Re-run the SysManage Server MSI installer"
        Write-Log ""
        try { Stop-Transcript } catch { Write-Host "Stop-Transcript error swallowed: $_" }
        Write-Host ""
        Write-Host "=====================================" -ForegroundColor Yellow
        Write-Host "Service NOT registered -- Python missing" -ForegroundColor Yellow
        Write-Host "See $LogFile for recovery steps." -ForegroundColor Yellow
        Write-Host "=====================================" -ForegroundColor Yellow
        Write-Host ""
        exit 0
    }
    Write-Log "Found Python: $VenvPython"

    # Check if uvicorn is installed
    $VenvPip = Join-Path $InstallDir ".venv\Scripts\pip.exe"
    # Actually verify, don't just log and assert success.  This previously piped
    # the grep output to the log and then printed "Uvicorn verified"
    # unconditionally -- so a venv with NO dependencies installed still reported
    # verified, and we went on to register a service that restart-looped forever
    # on "No module named uvicorn" while the MSI reported a successful install.
    Write-Log "Verifying uvicorn installation..."
    $uvicornCheck = & $VenvPip list 2>&1 | Select-String -Pattern "^uvicorn\s"
    if (-not $uvicornCheck) {
        Write-Log "ERROR: uvicorn is NOT installed in the venv."
        Write-Log "  The dependency install did not complete - see the earlier"
        Write-Log "  'Failed to install dependencies' error in this log."
        Write-Log "  Refusing to register a service that cannot start."
        throw "uvicorn missing from venv - dependency installation failed"
    }
    Write-Log "Uvicorn verified: $($uvicornCheck.ToString().Trim())"

    # Check if service already exists
    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

    if ($existingService) {
        Write-Log "Service already exists, stopping and removing it..."
        if ($existingService.Status -eq 'Running') {
            Stop-Service -Name $ServiceName -Force
            Write-Log "Service stopped"
        }

        # Use NSSM to remove service
        $nssmPath = Join-Path $InstallDir "nssm.exe"
        if (Test-Path $nssmPath) {
            & $nssmPath remove $ServiceName confirm | Out-File -FilePath $LogFile -Append
        } else {
            sc.exe delete $ServiceName | Out-Null
        }

        # Wait for service deletion
        Write-Log "Waiting for service deletion to complete..."
        $maxWait = 30
        $waited = 0
        while ((Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) -and ($waited -lt $maxWait)) {
            Start-Sleep -Seconds 1
            $waited++
        }

        if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
            Write-Log "WARNING: Service still exists after $maxWait seconds"
        } else {
            Write-Log "Old service removed successfully"
        }
    }

    # Check if NSSM is present
    $nssmPath = Join-Path $InstallDir "nssm.exe"
    if (-not (Test-Path $nssmPath)) {
        Write-Log "ERROR: NSSM not found at: $nssmPath"
        throw "NSSM not found"
    }
    Write-Log "Found NSSM at: $nssmPath"

    # Get 8.3 short paths
    function Get-ShortPath {
        param([string]$LongPath)
        try {
            $fso = New-Object -ComObject Scripting.FileSystemObject
            $file = $fso.GetFile($LongPath)
            return $file.ShortPath
        } catch {
            Write-Log "WARNING: Could not get short path for $LongPath"
            return $LongPath
        }
    }

    $VenvPythonShort = Get-ShortPath $VenvPython
    $InstallDirShort = Get-ShortPath $InstallDir

    Write-Log "Using 8.3 short paths:"
    Write-Log "  Python: $VenvPythonShort"
    Write-Log "  WorkDir: $InstallDirShort"

    # Create the service using NSSM
    Write-Log "Creating service: $ServiceName"

    $ConfigPath = "C:\ProgramData\SysManage\sysmanage.yaml"

    # Install service - run backend.main (not uvicorn directly): it binds
    # api.host/api.port from sysmanage.yaml and sizes the workers for this
    # machine (Phase 22.2).
    & $nssmPath install $ServiceName $VenvPythonShort -m backend.main 2>&1 | Out-File -FilePath $LogFile -Append

    if ($LASTEXITCODE -ne 0) {
        throw "NSSM install command failed with exit code $LASTEXITCODE"
    }

    Write-Log "Service installed with NSSM successfully"

    # Configure service
    Write-Log "Configuring service parameters..."

    # Set working directory
    & $nssmPath set $ServiceName AppDirectory $InstallDirShort | Out-File -FilePath $LogFile -Append

    # Set display name and description
    & $nssmPath set $ServiceName DisplayName "$DisplayName" | Out-File -FilePath $LogFile -Append
    & $nssmPath set $ServiceName Description "$Description" | Out-File -FilePath $LogFile -Append

    # Set environment variables
    & $nssmPath set $ServiceName AppEnvironmentExtra "SYSMANAGE_CONFIG=$ConfigPath" | Out-File -FilePath $LogFile -Append

    # Configure logging
    $StdoutLog = Join-Path $LogPath "server-stdout.log"
    $StderrLog = Join-Path $LogPath "server-stderr.log"
    & $nssmPath set $ServiceName AppStdout "$StdoutLog" | Out-File -FilePath $LogFile -Append
    & $nssmPath set $ServiceName AppStderr "$StderrLog" | Out-File -FilePath $LogFile -Append

    # Rotate logs (10MB, keep 5 files)
    & $nssmPath set $ServiceName AppStdoutCreationDisposition 4 | Out-File -FilePath $LogFile -Append
    & $nssmPath set $ServiceName AppStderrCreationDisposition 4 | Out-File -FilePath $LogFile -Append
    & $nssmPath set $ServiceName AppRotateFiles 1 | Out-File -FilePath $LogFile -Append
    & $nssmPath set $ServiceName AppRotateBytes 10485760 | Out-File -FilePath $LogFile -Append

    # Set startup type to automatic
    & $nssmPath set $ServiceName Start SERVICE_AUTO_START | Out-File -FilePath $LogFile -Append

    # Configure failure recovery
    Write-Log "Configuring service failure recovery..."
    $failureCmd = "sc.exe failure `"$ServiceName`" reset= 86400 actions= restart/60000/restart/60000/restart/60000"
    cmd.exe /c $failureCmd 2>&1 | Out-File -FilePath $LogFile -Append

    $ServiceCreated = $true
    Write-Log "Service configured successfully"

    # NOT started here: whether to start, and whether to migrate first, is
    # decided after OpenBAO is up (see the end of this script).

} catch {
    Write-Log "ERROR: Exception during service creation: $_"
} finally {
    # Stop-Transcript wrapped so a terminating error here never escapes
    # finally (PR #375773 rationale -- see sysmanage-agent equivalent).
    try { Stop-Transcript } catch { Write-Host "Stop-Transcript error swallowed: $_" }

    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Yellow
    if ($ServiceCreated) {
        Write-Host "Service created successfully!" -ForegroundColor Green
        Write-Host "Service Name: $ServiceName" -ForegroundColor Cyan
    } else {
        Write-Host "Service creation FAILED" -ForegroundColor Red
    }
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host ""
}

# ---------------------------------------------------------------
# OpenBAO secrets broker (best-effort; never blocks the MSI).
# Provisions bao.exe, writes a Windows-path config, registers an NSSM
# service, and runs the init/unseal helper.  Wrapped so any failure is
# logged but never fails the install.
# ---------------------------------------------------------------
try {
    $BaoExe = Join-Path $InstallDir "bao.exe"
    if (-not (Test-Path $BaoExe)) {
        $OpenBaoVersion = "2.5.4"
        $Arch = if ([Environment]::Is64BitOperatingSystem) { "x86_64" } else { "386" }
        $BaoUrl = "https://github.com/openbao/openbao/releases/download/v$OpenBaoVersion/bao_${OpenBaoVersion}_Windows_${Arch}.zip"
        $BaoZip = Join-Path $env:TEMP "bao.zip"
        try {
            Invoke-WebRequest -Uri $BaoUrl -OutFile $BaoZip -UseBasicParsing -ErrorAction Stop
            Expand-Archive -Path $BaoZip -DestinationPath $InstallDir -Force
            Remove-Item $BaoZip -ErrorAction SilentlyContinue
        } catch {
            Write-Log "WARNING: could not download OpenBAO: $_"
        }
    }

    if (Test-Path $BaoExe) {
        $OpenBaoData = "C:\ProgramData\SysManage\openbao"
        $OpenBaoConfig = Join-Path $OpenBaoData "openbao.hcl"
        New-Item -ItemType Directory -Force -Path (Join-Path $OpenBaoData "data") | Out-Null
        # init.json (written below) holds the unseal keys and the root token,
        # and ProgramData is readable by every local user: SYSTEM (the
        # OpenBAO service) and Administrators only.
        icacls $OpenBaoData /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null

        # Windows-path config (the shared *.hcl uses Unix paths).
        $dataPath = (Join-Path $OpenBaoData "data").Replace('\','\\')
        @"
storage "file" {
  path = "$dataPath"
}
listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = "true"
}
api_addr      = "http://127.0.0.1:8200"
disable_mlock = true
ui            = false
"@ | Out-File -FilePath $OpenBaoConfig -Encoding ascii -Force

        $nssmPath = Join-Path $InstallDir "nssm.exe"
        if (Test-Path $nssmPath) {
            if (Get-Service -Name "SysManageOpenBAO" -ErrorAction SilentlyContinue) {
                & $nssmPath remove "SysManageOpenBAO" confirm | Out-Null
            }
            & $nssmPath install "SysManageOpenBAO" $BaoExe server "-config=$OpenBaoConfig" | Out-Null
            & $nssmPath set "SysManageOpenBAO" DisplayName "SysManage OpenBAO" | Out-Null
            & $nssmPath set "SysManageOpenBAO" Start SERVICE_AUTO_START | Out-Null
            & $nssmPath set "SysManageOpenBAO" AppStdout (Join-Path $LogPath "openbao.log") | Out-Null
            & $nssmPath set "SysManageOpenBAO" AppStderr (Join-Path $LogPath "openbao.log") | Out-Null
            Start-Service -Name "SysManageOpenBAO" -ErrorAction SilentlyContinue
            Write-Log "OpenBAO service registered."

            # Init/unseal (helper waits for the listener); needs the venv python.
            $VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
            $InitScript = Join-Path $InstallDir "scripts\openbao_init_unseal.py"
            if ((Test-Path $VenvPython) -and (Test-Path $InitScript)) {
                $KeyFile = Join-Path $OpenBaoData "init.json"
                & $VenvPython $InitScript --addr "http://127.0.0.1:8200" --keyfile $KeyFile 2>&1 | Out-File -FilePath $LogFile -Append
            }
        } else {
            Write-Log "WARNING: NSSM not found; OpenBAO service not registered."
        }
    } else {
        Write-Log "WARNING: OpenBAO (bao.exe) not available; set vault.enabled=false."
    }
} catch {
    Write-Log "WARNING: OpenBAO provisioning failed (non-fatal): $_"
}

# ---------------------------------------------------------------
# Start the server -- or, on a fresh install, deliberately don't.
#
# A fresh install has only the example configuration (install.ps1 leaves a
# .config-created marker when it copies it): no database settings, no schema,
# no certificate.  Starting the service then only produced a restart loop of
# failures that looked like a broken install.  So it is registered on MANUAL
# start and left stopped; GETTING-STARTED.txt (opened from the installer's
# Finish page) walks through configuring it, migrating and starting it.
#
# An upgrade keeps its configuration, so the schema is brought up to the new
# code first -- sysmanage_migrate.py, the same tool every other platform uses
# (registry, shared and tenant chains, then each tenant database, which is why
# this runs after OpenBAO is up) -- and the service is started.  A migration
# failure does not stop the start: the console then shows its pending-
# migration banner, and the failure goes to the log and the Event Log with
# the command to re-run.
# ---------------------------------------------------------------
if ($ServiceCreated) {
    $FreshMarker = Join-Path $LogPath ".config-created"
    $nssmPath = Join-Path $InstallDir "nssm.exe"
    if (Test-Path $FreshMarker) {
        Remove-Item $FreshMarker -Force -ErrorAction SilentlyContinue
        & $nssmPath set $ServiceName Start SERVICE_DEMAND_START | Out-File -FilePath $LogFile -Append
        Write-Log "Fresh install: $ServiceName is registered but NOT started (manual start)."
        Write-Log "Configure it first - see $(Join-Path $InstallDir 'GETTING-STARTED.txt')."
    } else {
        $VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
        $MigrateScript = Join-Path $InstallDir "scripts\sysmanage_migrate.py"
        $env:SYSMANAGE_CONFIG_PATH = "C:\ProgramData\SysManage\sysmanage.yaml"
        Write-Log "Upgrade: applying database migrations..."
        # "$_" per line: Windows PowerShell 5.1 turns each stderr line of a
        # native program (Alembic logs to stderr) into an ErrorRecord, and
        # Out-File then wrote every one as a "NativeCommandError" block.  An
        # ErrorRecord's string form is just the line.
        & $VenvPython $MigrateScript 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $LogFile -Append
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Database migrations applied."
        } else {
            $retry = "& `"$VenvPython`" `"$MigrateScript`""
            Write-Log "WARNING: database migration failed (exit $LASTEXITCODE). Fix the cause, then run:"
            Write-Log "  $retry"
            try {
                if (-not [System.Diagnostics.EventLog]::SourceExists("SysManage")) {
                    [System.Diagnostics.EventLog]::CreateEventSource("SysManage", "Application")
                }
                Write-EventLog -LogName Application -Source "SysManage" -EntryType Warning -EventId 1001 `
                    -Message "SysManage Server upgrade: database migration failed. See $LogFile, then run: $retry"
            } catch { }
        }
        try {
            Start-Service -Name $ServiceName -ErrorAction Stop
            Start-Sleep -Seconds 2
            Write-Log "Service status: $((Get-Service -Name $ServiceName).Status)"
            Write-Log "The console is served by nginx on https://localhost/ (port 8080 is the loopback-only API)."
        } catch {
            Write-Log "WARNING: Failed to start service: $_"
            Write-Log "Check $(Join-Path $LogPath 'server-stderr.log'), then: Start-Service $ServiceName"
        }
    }
    Write-Host "Windows Service creation complete"
} else {
    # NEVER exit non-zero -- the WiX CustomAction uses ``Return="check"``,
    # which would roll back the whole MSI install on any non-zero exit
    # from this script.  That cascades into ``Installation Verification:
    # Completed`` / ``##[error] Failed`` on the winget-pkgs pipeline
    # (PR #375773 burn, 2026-05-17), because the MSI rolls back, no ARP
    # entry is written, and the verifier sees nothing to verify.
    # Service registration is post-install ergonomics, not install-
    # blocking.  Land the MSI; tell the operator how to finish.
    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host "Service NOT registered -- MSI install will still complete." -ForegroundColor Yellow
    Write-Host "To register the service manually after installing Python 3.9+:" -ForegroundColor Yellow
    Write-Host "  1. Re-run the MSI (MajorUpgrade re-fires the custom actions)" -ForegroundColor Yellow
    Write-Host "  2. Or run create-service.ps1 directly as administrator" -ForegroundColor Yellow
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host ""
}
exit 0
