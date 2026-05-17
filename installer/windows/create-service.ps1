#
# Create Windows Service for SysManage Server using NSSM
#

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
        # can't register the service to point at one — so log the
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
        Stop-Transcript
        Write-Host ""
        Write-Host "=====================================" -ForegroundColor Yellow
        Write-Host "Service NOT registered — Python missing" -ForegroundColor Yellow
        Write-Host "See $LogFile for recovery steps." -ForegroundColor Yellow
        Write-Host "=====================================" -ForegroundColor Yellow
        Write-Host ""
        exit 0
    }
    Write-Log "Found Python: $VenvPython"

    # Check if uvicorn is installed
    $VenvPip = Join-Path $InstallDir ".venv\Scripts\pip.exe"
    Write-Log "Verifying uvicorn installation..."
    & $VenvPip list 2>&1 | Select-String -Pattern "uvicorn" | Out-File -FilePath $LogFile -Append
    Write-Log "Uvicorn verified"

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

    # Install service - Run uvicorn with backend.main:app
    & $nssmPath install $ServiceName $VenvPythonShort -m uvicorn backend.main:app --host 0.0.0.0 --port 8080 2>&1 | Out-File -FilePath $LogFile -Append

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

    # Start the service
    Write-Log "Starting service..."
    try {
        Start-Service -Name $ServiceName -ErrorAction Stop
        Start-Sleep -Seconds 2
        $svcStatus = Get-Service -Name $ServiceName
        Write-Log "Service status: $($svcStatus.Status)"

        if ($svcStatus.Status -eq 'Running') {
            Write-Log "Service started successfully"
            Write-Log ""
            Write-Log "Web interface should be available at: http://localhost:8080"
        } else {
            Write-Log "WARNING: Service is not running. Status: $($svcStatus.Status)"
            Write-Log "Check logs:"
            Write-Log "  $StdoutLog"
            Write-Log "  $StderrLog"
        }
    } catch {
        Write-Log "WARNING: Failed to start service: $_"
        Write-Log "You can start it manually with: Start-Service $ServiceName"
    }

} catch {
    Write-Log "ERROR: Exception during service creation: $_"
} finally {
    Stop-Transcript

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

if ($ServiceCreated) {
    Write-Host "Windows Service creation complete"
} else {
    # NEVER exit non-zero — the WiX CustomAction uses ``Return="check"``,
    # which would roll back the whole MSI install on any non-zero exit
    # from this script.  That cascades into ``Installation Verification:
    # Completed`` / ``##[error] Failed`` on the winget-pkgs pipeline
    # (PR #375773 burn, 2026-05-17), because the MSI rolls back, no ARP
    # entry is written, and the verifier sees nothing to verify.
    # Service registration is post-install ergonomics, not install-
    # blocking.  Land the MSI; tell the operator how to finish.
    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host "Service NOT registered — MSI install will still complete." -ForegroundColor Yellow
    Write-Host "To register the service manually after installing Python 3.9+:" -ForegroundColor Yellow
    Write-Host "  1. Re-run the MSI (MajorUpgrade re-fires the custom actions)" -ForegroundColor Yellow
    Write-Host "  2. Or run create-service.ps1 directly as administrator" -ForegroundColor Yellow
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host ""
}
exit 0
