#Requires -RunAsAdministrator
# Try disabling Secure Boot entirely and check if the ISO is actually readable.

$ErrorActionPreference = "Stop"

foreach ($vmName in @("pxe-server", "pxe-router")) {
    Write-Host "`n=== $vmName ===" -ForegroundColor Cyan

    $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
    if (-not $vm) {
        Write-Host "  VM not found, skipping."
        continue
    }

    if ($vm.State -ne "Off") {
        Write-Host "  Stopping VM..."
        Stop-VM -Name $vmName -Force -TurnOff
        Start-Sleep -Seconds 2
    }

    # Check if the ISO file is actually accessible
    $dvd = Get-VMDvdDrive -VMName $vmName
    $isoPath = $dvd.Path
    Write-Host "  DVD Path: $isoPath"
    if ($isoPath) {
        if (Test-Path $isoPath) {
            $isoSize = (Get-Item $isoPath).Length
            Write-Host "  ISO exists: yes ($([math]::Round($isoSize / 1MB)) MB)"
        } else {
            Write-Host "  ISO exists: NO - FILE NOT FOUND!" -ForegroundColor Red
        }
    } else {
        Write-Host "  DVD Path is empty - no ISO attached!" -ForegroundColor Red
    }

    # Disable Secure Boot entirely
    $fw = Get-VMFirmware -VMName $vmName
    Write-Host "  SecureBoot before: $($fw.SecureBoot)"
    Write-Host "  Disabling Secure Boot..."
    Set-VMFirmware -VMName $vmName -EnableSecureBoot Off

    # Remove the DVD and re-add it to force a clean attachment
    Write-Host "  Removing and re-attaching DVD drive..."
    $path = $dvd.Path
    Remove-VMDvdDrive -VMName $vmName -ControllerNumber $dvd.ControllerNumber -ControllerLocation $dvd.ControllerLocation
    Add-VMDvdDrive -VMName $vmName -Path $path

    # Set the fresh DVD as first boot device
    $newDvd = Get-VMDvdDrive -VMName $vmName
    Set-VMFirmware -VMName $vmName -FirstBootDevice $newDvd

    # Final state dump
    $fw2 = Get-VMFirmware -VMName $vmName
    Write-Host "  SecureBoot after: $($fw2.SecureBoot)"
    Write-Host "  Boot order:"
    foreach ($entry in $fw2.BootOrder) {
        Write-Host "    $($entry.BootType) - $($entry.Device)"
    }

    # Also check: does the VM have checkpoints that might be interfering?
    $snaps = Get-VMSnapshot -VMName $vmName -ErrorAction SilentlyContinue
    if ($snaps) {
        Write-Host "  WARNING: VM has checkpoints - these can interfere!" -ForegroundColor Red
        foreach ($s in $snaps) {
            Write-Host "    $($s.Name) ($($s.CreationTime))"
        }
    } else {
        Write-Host "  Checkpoints: none"
    }

    # Check if VM has automatic checkpoints enabled (creates one at every start)
    $autoCP = (Get-VM -Name $vmName).AutomaticCheckpointsEnabled
    Write-Host "  AutomaticCheckpoints: $autoCP"
    if ($autoCP) {
        Write-Host "  Disabling automatic checkpoints (they restore old state on boot)..." -ForegroundColor Yellow
        Set-VM -Name $vmName -AutomaticCheckpointsEnabled $false
        # Remove any auto-created checkpoints
        $snaps2 = Get-VMSnapshot -VMName $vmName -ErrorAction SilentlyContinue
        if ($snaps2) {
            Write-Host "  Removing existing checkpoints..."
            $snaps2 | Remove-VMSnapshot -Confirm:$false
            Start-Sleep -Seconds 3
        }
    }

    Write-Host "  Starting VM..."
    Start-VM -Name $vmName
    Start-Sleep -Seconds 2
    try {
        Start-Process "vmconnect.exe" -ArgumentList "localhost", $vmName
    } catch {
        Write-Host "  Could not launch vmconnect." -ForegroundColor Yellow
    }
    Write-Host "  Done." -ForegroundColor Green
}

Write-Host ""
