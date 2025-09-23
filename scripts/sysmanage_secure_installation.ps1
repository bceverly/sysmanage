# SysManage Secure Installation Wrapper (PowerShell)
# Handles privilege elevation and virtual environment setup on Windows
# Usage: scripts\sysmanage_secure_installation.ps1

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AdditionalArgs
)

# Function to check if running as Administrator
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Function to find the Python interpreter
function Find-Python {
    $scriptDir = Split-Path -Parent $PSCommandPath
    $projectRoot = Split-Path -Parent $scriptDir

    # First, try the virtual environment
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    Write-Error "Error: Virtual environment not found at $projectRoot\.venv"
    Write-Error "Please run 'make install-dev' first to set up the environment."
    exit 1
}

# Function to get the Python script path
function Get-PythonScriptPath {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return Join-Path $scriptDir "_sysmanage_secure_installation.py"
}

# Main execution
try {
    # Get script and project paths
    $scriptDir = Split-Path -Parent $PSCommandPath
    $projectRoot = Split-Path -Parent $scriptDir
    $pythonScript = Get-PythonScriptPath

    # Verify the Python script exists
    if (-not (Test-Path $pythonScript)) {
        Write-Error "Error: Python script not found at $pythonScript"
        exit 1
    }

    # Check if we're running as Administrator
    if (-not (Test-Administrator)) {
        Write-Host ""
        Write-Host "ERROR: Administrator Privileges Required" -ForegroundColor Red
        Write-Host "=======================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "This script requires Administrator privileges to run properly." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To run as Administrator:" -ForegroundColor Cyan
        Write-Host "  1. Right-click on PowerShell" -ForegroundColor White
        Write-Host "  2. Select 'Run as Administrator'" -ForegroundColor White
        Write-Host "  3. Navigate to your project directory:" -ForegroundColor White
        Write-Host "     cd `"$projectRoot`"" -ForegroundColor Gray
        Write-Host "  4. Run the script:" -ForegroundColor White
        Write-Host "     scripts\sysmanage_secure_installation.ps1" -ForegroundColor Gray
        Write-Host ""
        exit 1
    }

    # Find the Python interpreter
    $pythonBin = Find-Python

    Write-Host "Running SysManage secure installation with Administrator privileges..."
    Write-Host "Python: $pythonBin"
    Write-Host "Script: $pythonScript"
    Write-Host ""

    # Execute the Python script with any additional arguments
    if ($AdditionalArgs) {
        & $pythonBin $pythonScript @AdditionalArgs
    } else {
        & $pythonBin $pythonScript
    }

    # Check the exit code
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Python script exited with code $LASTEXITCODE"
        exit $LASTEXITCODE
    }

} catch {
    Write-Error "An error occurred: $($_.Exception.Message)"
    exit 1
}