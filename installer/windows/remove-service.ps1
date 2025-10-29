#
# Remove Windows Service for SysManage Server
#

$ErrorActionPreference = "Continue"

$ServiceName = "SysManageServer"
$LogPath = "C:\ProgramData\SysManage\logs"
$LogFile = Join-Path $LogPath "install.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host $Message
}

Write-Log "=== Removing SysManage Server Service ==="

try {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    
    if ($service) {
        Write-Log "Service found, removing..."
        
        # Stop service if running
        if ($service.Status -eq 'Running') {
            Write-Log "Stopping service..."
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 3
        }
        
        # Try NSSM first
        $InstallDir = "C:\Program Files\SysManage Server"
        $nssmPath = Join-Path $InstallDir "nssm.exe"
        
        if (Test-Path $nssmPath) {
            Write-Log "Using NSSM to remove service..."
            & $nssmPath remove $ServiceName confirm 2>&1 | Out-File -FilePath $LogFile -Append
        } else {
            Write-Log "Using sc.exe to remove service..."
            sc.exe delete $ServiceName 2>&1 | Out-File -FilePath $LogFile -Append
        }
        
        Write-Log "Service removed successfully"
    } else {
        Write-Log "Service not found, nothing to remove"
    }
    
    exit 0
    
} catch {
    Write-Log "ERROR during service removal: $_"
    exit 0  # Don't fail uninstall if service removal fails
}
