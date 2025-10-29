#
# SysManage Server - Post-Installation Script
# Sets up Python virtual environment and installs dependencies
#

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

    # Find Python executable
    Write-Log "Searching for Python 3.9+..."
    $PythonExe = $null
    $PythonCommands = @("python", "python3", "py")

    foreach ($cmd in $PythonCommands) {
        try {
            $testPath = (Get-Command $cmd -ErrorAction SilentlyContinue).Source
            if ($testPath) {
                $version = & $cmd --version 2>&1
                if ($version -match "Python 3\.([0-9]+)") {
                    $minor = [int]$Matches[1]
                    if ($minor -ge 9) {
                        $PythonExe = $cmd
                        Write-Log "Found Python: $testPath (version: $version)"
                        break
                    }
                }
            }
        } catch {
            continue
        }
    }

    if (-not $PythonExe) {
        Write-Log "ERROR: Python 3.9+ not found. Please install Python from https://www.python.org/downloads/"
        throw "Python 3.9+ not found"
    }

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

    # Install dependencies
    $VenvPython = Join-Path $VenvPath "Scripts\python.exe"
    $RequirementsFile = Join-Path $InstallDir "requirements.txt"

    if (-not (Test-Path $RequirementsFile)) {
        Write-Log "ERROR: requirements.txt not found at $RequirementsFile"
        throw "requirements.txt not found"
    }

    Write-Log "Installing Python dependencies..."
    Write-Log "Running: pip install -r requirements.txt"
    & $VenvPython -m pip install -r $RequirementsFile --disable-pip-version-check 2>&1 | Tee-Object -FilePath $LogFile -Append

    if ($LASTEXITCODE -eq 0) {
        Write-Log "Dependencies installed successfully"
    } else {
        Write-Log "ERROR: Failed to install dependencies (exit code $LASTEXITCODE)"
        throw "Failed to install dependencies"
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

    # Mark installation as successful
    $InstallSuccess = $true

    Write-Log ""
    Write-Log "=== Installation Complete ==="
    Write-Log ""
    Write-Log "Next steps:"
    Write-Log "1. Install and configure PostgreSQL"
    Write-Log "2. Edit configuration: $ConfigFile"
    Write-Log "3. Service will be created and started next"
    Write-Log ""
    Write-Log "After service starts, access the web interface at:"
    Write-Log "  http://localhost:8080"
    Write-Log ""

} catch {
    Write-Log ""
    Write-Log "=== INSTALLATION FAILED ==="
    Write-Log "Error: $_"
    Write-Log ""
} finally {
    Stop-Transcript

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
} else {
    exit 1
}
