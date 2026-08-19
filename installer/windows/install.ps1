# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

#
# SysManage Server - Post-Installation Script
# Sets up Python virtual environment and installs dependencies
#

# Top-level trap -- see sysmanage-agent's install.ps1 for the full
# rationale (PR #375773 winget-pkgs validation burn, 2026-05-17).
# Catches any unhandled exception escaping any scope below and exits
# 0 so the MSI engine doesn't trigger Error 1722 + rollback.
trap {
    Write-Host "WARNING: unhandled exception trapped at top level: $_"
    # Honour the same soft/hard split as the exit policy at the bottom of this
    # script.  The operator-fixable "no suitable Python" case is raised inside the
    # main try/catch and never reaches here, so an exception that DOES reach this
    # trap is unexpected -- fail hard rather than landing a broken install that
    # reports success.  ($SoftFailure may not be initialised yet if something
    # throws very early, hence the null-safe test.)
    if ($script:SoftFailure -eq $true) {
        Write-Host "Install step had errors but MSI install will still complete."
        exit 0
    }
    Write-Host "INSTALLATION FAILED - rolling back."
    exit 1
}

$ErrorActionPreference = "Continue"

# Get the installation directory
$InstallDir = "C:\Program Files\SysManage Server"

# Log file
$LogPath = "C:\ProgramData\SysManage\logs"
$LogFile = Join-Path $LogPath "install.log"
$TranscriptFile = Join-Path $LogPath "install-transcript.log"

# Create log directory if it doesn't exist
if (-not (Test-Path $LogPath)) {
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
}

# Start transcript to capture ALL output
Start-Transcript -Path $TranscriptFile -Append

# Function to write log messages
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}

# Track if installation succeeded
$InstallSuccess = $false

# Distinguishes "this machine lacks a suitable Python" (operator-fixable, MSI is
# allowed to land) from every other failure (hard, rolls the MSI back).  See the
# exit policy at the bottom of this script.
$script:SoftFailure = $false

Write-Log "=== SysManage Server Installation ==="
Write-Log "Installation Directory: $InstallDir"
Write-Log "Configuration Directory: C:\ProgramData\SysManage"

try {
    # Change to installation directory
    Set-Location $InstallDir

    # Extract source files from ZIP archives
    Write-Log "Extracting source files..."
    
    $BackendZip = Join-Path $InstallDir "backend.zip"
    $FrontendZip = Join-Path $InstallDir "frontend.zip"
    $AlembicZip = Join-Path $InstallDir "alembic.zip"
    
    $BackendDir = Join-Path $InstallDir "backend"
    $FrontendDir = Join-Path $InstallDir "frontend"
    $AlembicDir = Join-Path $InstallDir "alembic"

    # Extract backend
    if (Test-Path $BackendZip) {
        if (Test-Path $BackendDir) {
            Remove-Item -Path $BackendDir -Recurse -Force
        }
        $ProgressPreference = 'SilentlyContinue'
        Expand-Archive -Path $BackendZip -DestinationPath $BackendDir -Force
        $ProgressPreference = 'Continue'
        Write-Log "Backend files extracted successfully"
    } else {
        Write-Log "ERROR: backend.zip not found at $BackendZip"
        throw "backend.zip not found"
    }

    # Extract frontend
    if (Test-Path $FrontendZip) {
        if (Test-Path $FrontendDir) {
            Remove-Item -Path $FrontendDir -Recurse -Force
        }
        $ProgressPreference = 'SilentlyContinue'
        Expand-Archive -Path $FrontendZip -DestinationPath $FrontendDir -Force
        $ProgressPreference = 'Continue'
        Write-Log "Frontend files extracted successfully"
    } else {
        Write-Log "ERROR: frontend.zip not found at $FrontendZip"
        throw "frontend.zip not found"
    }

    # Extract alembic
    if (Test-Path $AlembicZip) {
        if (Test-Path $AlembicDir) {
            Remove-Item -Path $AlembicDir -Recurse -Force
        }
        $ProgressPreference = 'SilentlyContinue'
        Expand-Archive -Path $AlembicZip -DestinationPath $AlembicDir -Force
        $ProgressPreference = 'Continue'
        Write-Log "Alembic files extracted successfully"
    } else {
        Write-Log "ERROR: alembic.zip not found at $AlembicZip"
        throw "alembic.zip not found"
    }

    # Bundled Python runtime.
    #
    # The MSI ships a relocatable CPython (python-build-standalone) that includes
    # pip and venv, so the install depends on no system Python at all and the
    # bundled wheels are guaranteed to match the interpreter installing them --
    # they are built against this exact version at MSI build time.
    $PythonExe = $null
    $PythonZip = Join-Path $InstallDir "python.zip"
    $PythonDir = Join-Path $InstallDir "python"
    if (Test-Path $PythonZip) {
        Write-Log "Extracting bundled Python runtime..."
        if (Test-Path $PythonDir) { Remove-Item $PythonDir -Recurse -Force -ErrorAction SilentlyContinue }
        $ProgressPreference = 'SilentlyContinue'
        Expand-Archive -Path $PythonZip -DestinationPath $PythonDir -Force
        $ProgressPreference = 'Continue'
        $bundled = Join-Path $PythonDir "python.exe"
        if (Test-Path $bundled) {
            $PythonExe = $bundled
            $bv = & $bundled --version 2>&1
            Write-Log "Using bundled Python: $bundled ($bv)"
        } else {
            Write-Log "WARNING: python.zip extracted but python.exe is missing - falling back to a system Python"
        }
    }

    # Fallback: no bundled runtime in this package (older MSI or a partial dev
    # build).  Selection is pinned to the wheels' ABI tag -- see below.
    if (-not $PythonExe) {
    # Find Python executable.
    #
    # The bundled wheel set is installed with --no-index, and its compiled wheels
    # (aiohttp, psycopg, cryptography, ...) carry a cpXY ABI tag that matches
    # exactly ONE Python minor version.  Accepting "any Python >= 3.9" therefore
    # picks an interpreter the wheels cannot satisfy whenever the box has a newer
    # Python than the wheels were built against -- pip then fails on the first
    # compiled package ("No matching distribution found for aiohttp") and the whole
    # dependency install dies.  So: read the required tag out of the bundled wheels
    # and select an interpreter that matches it.
    $RequiredPyMinor = $null
    $WheelsZipProbe = Join-Path $InstallDir "wheels.zip"
    if (Test-Path $WheelsZipProbe) {
        try {
            Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
            $zip = [System.IO.Compression.ZipFile]::OpenRead($WheelsZipProbe)
            try {
                # Pure-python wheels are py3-none-any and constrain nothing; only
                # the cpXY-tagged (compiled) ones pin the interpreter.
                $tags = $zip.Entries.Name |
                        Where-Object { $_ -match '-cp3(\d+)-' } |
                        ForEach-Object { if ($_ -match '-cp3(\d+)-') { [int]$Matches[1] } } |
                        Sort-Object -Unique
            } finally { $zip.Dispose() }

            if ($tags.Count -eq 1) {
                $RequiredPyMinor = $tags[0]
                Write-Log "Bundled wheels require Python 3.$RequiredPyMinor (from their cp3$RequiredPyMinor ABI tag)"
            } elseif ($tags.Count -gt 1) {
                Write-Log "WARNING: bundled wheels carry mixed ABI tags (3.$($tags -join ', 3.')) - not pinning"
            } else {
                Write-Log "Bundled wheels are all pure-python; any supported Python will do"
            }
        } catch {
            Write-Log "WARNING: could not read ABI tags from $WheelsZipProbe ($_) - not pinning"
        }
    }

    if ($RequiredPyMinor) {
        Write-Log "Searching for Python 3.$RequiredPyMinor..."
    } else {
        Write-Log "Searching for Python 3.9+..."
    }

    # Enumerate every interpreter we can see, not just the first one on PATH:
    # the required version is often installed alongside a newer default.
    $Candidates = @()
    foreach ($cmd in @("python", "python3", "py")) {
        $src = (Get-Command $cmd -ErrorAction SilentlyContinue).Source
        if ($src) { $Candidates += $src }
    }
    # The py launcher knows about installs that are not on PATH at all.
    try {
        $launcher = (Get-Command "py" -ErrorAction SilentlyContinue).Source
        if ($launcher) {
            & $launcher -0p 2>$null | ForEach-Object {
                if ($_ -match '([A-Za-z]:\\[^\s].*python\.exe)') { $Candidates += $Matches[1] }
            }
        }
    } catch { }
    foreach ($root in @("C:\Python3*", "$env:LOCALAPPDATA\Programs\Python\Python3*", "$env:ProgramFiles\Python3*")) {
        Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $p = Join-Path $_.FullName "python.exe"
            if (Test-Path $p) { $Candidates += $p }
        }
    }
    $Candidates = $Candidates | Select-Object -Unique

    $PythonExe = $null
    $Seen = @()
    foreach ($cand in $Candidates) {
        try {
            $version = & $cand --version 2>&1
            if ($version -match "Python 3\.([0-9]+)") {
                $minor = [int]$Matches[1]
                $Seen += "3.$minor ($cand)"
                $ok = if ($RequiredPyMinor) { $minor -eq $RequiredPyMinor } else { $minor -ge 9 }
                if ($ok) {
                    $PythonExe = $cand
                    Write-Log "Found Python: $cand (version: $version)"
                    break
                }
            }
        } catch { continue }
    }

    if (-not $PythonExe -and $RequiredPyMinor) {
        # Be specific about what is needed.  "Install Python 3.9+" is actively
        # misleading here -- a 3.9+ Python is what the box already has.
        Write-Log "ERROR: no Python 3.$RequiredPyMinor found."
        Write-Log "  The bundled offline wheels are built for Python 3.$RequiredPyMinor and"
        Write-Log "  cannot be installed under any other version."
        if ($Seen.Count -gt 0) {
            Write-Log "  Interpreters found on this machine: $($Seen -join '; ')"
        } else {
            Write-Log "  No Python interpreter was found on this machine at all."
        }
        Write-Log "  Install Python 3.$RequiredPyMinor from https://www.python.org/downloads/"
        Write-Log "  then repair this installation to retry."
        # Soft failure: "this machine has no suitable Python" is an environment
        # problem the operator can fix and re-run, and it is exactly the condition
        # a winget-pkgs validation sandbox hits.  Rolling the MSI back here is what
        # burned PR #375773.  Everything ELSE is a hard failure (see the exit
        # policy at the end of this script).
        $script:SoftFailure = $true
        throw "Python 3.$RequiredPyMinor is required by the bundled wheels but is not installed"
    }
    }  # end fallback: no bundled Python runtime in this package

    if ($PythonExe) {
        # Create virtual environment
        Write-Log "Creating Python virtual environment..."
        $VenvPath = Join-Path $InstallDir ".venv"

        if (Test-Path $VenvPath) {
            Write-Log "Removing existing virtual environment..."

            # Stop service if running
            $ServiceName = "SysManageServer"
            $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
            if ($service -and $service.Status -eq 'Running') {
                Write-Log "Stopping service..."
                Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 3
            }

            # Stop any Python processes from venv
            $VenvPython = Join-Path $VenvPath "Scripts\python.exe"
            if (Test-Path $VenvPython) {
                Get-Process | Where-Object { $_.Path -eq $VenvPython } | Stop-Process -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 3
            }

            # Remove venv
            $retries = 3
            $removed = $false
            for ($i = 1; $i -le $retries; $i++) {
                try {
                    Remove-Item -Path $VenvPath -Recurse -Force -ErrorAction Stop
                    $removed = $true
                    break
                } catch {
                    Write-Log "Attempt $i failed to remove venv: $_"
                    if ($i -lt $retries) {
                        Start-Sleep -Seconds 3
                    }
                }
            }

            if (-not $removed) {
                Write-Log "ERROR: Could not remove existing virtual environment"
                throw "Failed to remove existing virtual environment"
            }
        }

        & $PythonExe -m venv $VenvPath 2>&1 | Out-File -FilePath $LogFile -Append
        if ($LASTEXITCODE -ne 0) {
            Write-Log "ERROR: Failed to create virtual environment (exit code $LASTEXITCODE)"
            throw "Failed to create virtual environment"
        }
        Write-Log "Virtual environment created successfully"

        # Native ARM64 uses pure-Python psycopg, which loads libpq at runtime. The
        # arm64 MSI ships libpq (+ deps) under <InstallDir>\libpq; copy them next to
        # the venv python.exe so the OS DLL loader finds them. (x64 uses
        # psycopg[binary] with libpq bundled, so this dir is absent and this no-ops.)
        $LibpqDir = Join-Path $InstallDir "libpq"
        if (Test-Path $LibpqDir) {
            Write-Log "Bundling libpq DLLs into venv (native ARM64 psycopg)..."
            Copy-Item -Path (Join-Path $LibpqDir "*.dll") -Destination (Join-Path $VenvPath "Scripts") -Force
        }

        # Install dependencies
        $VenvPython = Join-Path $VenvPath "Scripts\python.exe"
        # Prefer the runtime-only requirements (matches the air-gap wheel
        # set; the full requirements.txt carries dev tooling like astroid/
        # pylint/pytest that the server does not need to run).  Fall back to
        # the full list only if the prod file isn't present.
        $ProdRequirements = Join-Path $InstallDir "requirements-prod.txt"
        $RequirementsFile = if (Test-Path $ProdRequirements) { $ProdRequirements } else { Join-Path $InstallDir "requirements.txt" }

        if (-not (Test-Path $RequirementsFile)) {
            Write-Log "ERROR: requirements file not found at $RequirementsFile"
            throw "requirements file not found"
        }

        Write-Log "Installing Python dependencies..."
        # Prefer a bundled offline wheel set when the MSI ships one. The arm64 MSI
        # does, because several deps have no arm64 wheels on PyPI and the target
        # machine has no build toolchain; install from the wheels with no network.
        # Falls back to an online PyPI install when no wheel set is bundled (x64).
        $WheelsZip = Join-Path $InstallDir "wheels.zip"
        $PipSourceArgs = @()
        if (Test-Path $WheelsZip) {
            $WheelsDir = Join-Path $InstallDir "wheels"
            Write-Log "Extracting bundled wheels..."
            if (Test-Path $WheelsDir) { Remove-Item $WheelsDir -Recurse -Force -ErrorAction SilentlyContinue }
            Expand-Archive -Path $WheelsZip -DestinationPath $WheelsDir -Force
            $PipSourceArgs = @("--no-index", "--find-links", $WheelsDir)
            Write-Log "Installing dependencies from bundled wheels (offline): $WheelsDir"
        } else {
            Write-Log "Installing dependencies from PyPI..."
        }
        Write-Log "Running: pip install $($PipSourceArgs -join ' ') -r $RequirementsFile"
        & $VenvPython -m pip install @PipSourceArgs -r $RequirementsFile --disable-pip-version-check 2>&1 | Tee-Object -FilePath $LogFile -Append

        if ($LASTEXITCODE -eq 0) {
            Write-Log "Dependencies installed successfully"
        } else {
            Write-Log "ERROR: Failed to install dependencies (exit code $LASTEXITCODE)"
            throw "Failed to install dependencies"
        }
    } else {
        # Soft-fail: same rationale as check-python.ps1's matching
        # block.  Without Python on PATH we cannot build the venv
        # or install Python dependencies, but the MSI install
        # itself must still complete cleanly so:
        #   * winget-pkgs sandboxed validation passes (sandbox has
        #     no internet access to python.org for check-python.ps1
        #     to install Python)
        #   * offline / air-gapped installs proceed and the
        #     operator installs Python afterwards
        # After installing Python 3.9+, the operator re-runs the
        # MSI; the MajorUpgrade element detects the existing
        # install, the custom actions fire again, and Python is
        # now on PATH so venv + pip install succeed.
        Write-Log "WARNING: Python 3.9+ not found on PATH."
        Write-Log "WARNING: Skipping virtual-env and dependency install."
        Write-Log "WARNING: Install Python 3.9+ from https://www.python.org/downloads/"
        Write-Log "WARNING: then re-run the SysManage Server MSI to finish setup."
    }

    # Create configuration file if it doesn't exist
    $ConfigDir = "C:\ProgramData\SysManage"
    $ConfigFile = Join-Path $ConfigDir "sysmanage.yaml"
    $ExampleConfig = Join-Path $ConfigDir "sysmanage.yaml.example"

    if (-not (Test-Path $ConfigFile)) {
        if (Test-Path $ExampleConfig) {
            Write-Log "Creating default configuration from example..."
            Copy-Item $ExampleConfig $ConfigFile
            Write-Log ""
            Write-Log "IMPORTANT: Please edit the configuration file:"
            Write-Log "  $ConfigFile"
            Write-Log ""
            Write-Log "You must configure:"
            Write-Log "  - database.url: PostgreSQL connection string"
            Write-Log "  - server.port: Port for web interface (default: 8080)"
            Write-Log "  - security settings"
            Write-Log ""
        } else {
            Write-Log "WARNING: No example configuration file found"
        }
    } else {
        Write-Log "Configuration file already exists: $ConfigFile"
    }

    # Create database directory
    $DbDir = "C:\ProgramData\SysManage\db"
    if (-not (Test-Path $DbDir)) {
        Write-Log "Creating database directory..."
        New-Item -ItemType Directory -Path $DbDir -Force | Out-Null
    }

    # nginx - REQUIRED, not optional.  The backend has no static-file mount, so
    # without nginx the frontend extracted above is never served and there is no
    # console at all (this used to be exactly the Windows situation).  nginx also
    # terminates TLS on 443 and adds the security headers every other platform
    # gets.
    $NginxScript = Join-Path $InstallDir "install-nginx.ps1"
    if (Test-Path $NginxScript) {
        Write-Log "Setting up nginx (required - it serves the web console)..."
        try {
            & powershell.exe -ExecutionPolicy Bypass -File $NginxScript -InstallDir $InstallDir 2>&1 |
                Out-File -FilePath $LogFile -Append
            if ($LASTEXITCODE -ne 0) { throw "install-nginx.ps1 exited $LASTEXITCODE" }
            Write-Log "nginx configured"
        } catch {
            # Loud, and NOT silently swallowed: an install that skips this
            # produces a server with no reachable console, which previously
            # reported success and left the operator to discover it.
            Write-Log ""
            Write-Log "ERROR: nginx setup failed: $_"
            Write-Log "  SysManage serves its web console THROUGH nginx - without it"
            Write-Log "  the console is unreachable (the API on 8080 does not serve the UI)."
            Write-Log "  Fix the error above and re-run:"
            Write-Log "    powershell -ExecutionPolicy Bypass -File `"$NginxScript`""
            Write-Log ""
            throw
        }
    } else {
        Write-Log "ERROR: install-nginx.ps1 not found at $NginxScript"
        Write-Log "  The web console cannot be served without nginx."
        throw "install-nginx.ps1 missing"
    }

    # Mark installation as successful
    $InstallSuccess = $true

    Write-Log ""
    Write-Log "=== Installation Complete ==="
    Write-Log ""
    Write-Log "Next steps:"
    Write-Log "1. Install and configure PostgreSQL"
    Write-Log "2. Edit configuration: $ConfigFile"
    Write-Log "3. Install a TLS certificate (see below) - nginx will not start without it"
    Write-Log "4. Service will be created and started next"
    Write-Log ""
    Write-Log "The web console is served by nginx on port 443:"
    Write-Log "  https://localhost/"
    Write-Log ""
    Write-Log "The API on 127.0.0.1:8080 is loopback-only and does NOT serve the"
    Write-Log "console - nginx serves the UI and proxies /api/ and /ws to it."
    Write-Log ""

} catch {
    Write-Log ""
    Write-Log "=== INSTALLATION FAILED ==="
    Write-Log "Error: $_"
    Write-Log ""
} finally {
    # Stop-Transcript wrapped so a terminating error here never escapes
    # finally (would make script exit 1 -> MSI Error 1722 -> rollback).
    try { Stop-Transcript } catch { Write-Host "Stop-Transcript error swallowed: $_" }

    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Yellow
    if ($InstallSuccess) {
        Write-Host "Installation completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "Installation FAILED - see errors above" -ForegroundColor Red
    }
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host ""
}

if ($InstallSuccess) {
    exit 0
}

# Exit policy.  The WiX CustomAction uses ``Return="check"``, so a non-zero exit
# rolls back the entire MSI.  There are two failure classes and they must not be
# treated alike:
#
#   SOFT (exit 0, MSI lands) -- the machine lacks a suitable Python.  This is an
#     environment problem the operator fixes and re-runs, and it is the condition
#     a winget-pkgs validation sandbox hits.  Rolling back here burned PR #375773
#     (2026-05-17); see the matching block in sysmanage-agent's install.ps1.
#
#   HARD (exit 1, MSI rolls back) -- anything else: the required Python was
#     present and the install still broke (dependency install failed, payload
#     extraction failed, nginx setup failed).  These previously exited 0 too,
#     which is how a completely non-functional install came to report
#     "Installation completed successfully" while its service restart-looped on
#     "No module named uvicorn" and no web console was ever served.  A broken
#     install that claims success is worse than a failed one: nothing tells the
#     operator to look.
if ($InstallSuccess) {
    exit 0
}

if ($script:SoftFailure) {
    Write-Host ""
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host "Install step could not complete -- MSI install will still land." -ForegroundColor Yellow
    Write-Host "Install the required Python, then repair this installation." -ForegroundColor Yellow
    Write-Host "See $LogFile for the failure and recovery steps." -ForegroundColor Yellow
    Write-Host "=====================================" -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

# Hard failure: make it visible in the event log as well, because the MSI runs
# this custom action with -WindowStyle Hidden and nobody sees stdout.
try {
    if (-not [System.Diagnostics.EventLog]::SourceExists("SysManage")) {
        [System.Diagnostics.EventLog]::CreateEventSource("SysManage", "Application")
    }
    Write-EventLog -LogName Application -Source "SysManage" -EntryType Error -EventId 1000 `
        -Message "SysManage Server installation failed. See $LogFile for details."
} catch { }

Write-Host ""
Write-Host "=====================================" -ForegroundColor Red
Write-Host "INSTALLATION FAILED - rolling back." -ForegroundColor Red
Write-Host "See $LogFile for the failure and recovery steps." -ForegroundColor Red
Write-Host "=====================================" -ForegroundColor Red
Write-Host ""
exit 1
