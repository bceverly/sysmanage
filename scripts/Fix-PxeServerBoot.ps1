#Requires -RunAsAdministrator
# Diagnose and fix the pxe-server and pxe-router boot order.

$ErrorActionPreference = "Stop"

foreach ($vmName in @("pxe-server", "pxe-router")) {
    Write-Host "`n=== $vmName ===" -ForegroundColor Cyan

    $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
    if (-not $vm) {
        Write-Host "  VM not found, skipping."
        continue
    }

    # Show current state
    Write-Host "  State: $($vm.State)"
    Write-Host "  Generation: $($vm.Generation)"

    # Show firmware boot order
    $fw = Get-VMFirmware -VMName $vmName
    Write-Host "  Current boot order:"
    foreach ($entry in $fw.BootOrder) {
        Write-Host "    $($entry.BootType) - $($entry.Device)"
    }

    # Show all devices
    $dvds = Get-VMDvdDrive -VMName $vmName
    $nics = Get-VMNetworkAdapter -VMName $vmName
    $hdds = Get-VMHardDiskDrive -VMName $vmName

    Write-Host "  DVD drives:"
    foreach ($d in $dvds) {
        Write-Host "    Controller: $($d.ControllerType) Loc: $($d.ControllerLocation) Path: $($d.Path)"
    }
    Write-Host "  NICs:"
    foreach ($n in $nics) {
        Write-Host "    Switch: $($n.SwitchName) MAC: $($n.MacAddress)"
    }
    Write-Host "  HDDs:"
    foreach ($h in $hdds) {
        Write-Host "    Path: $($h.Path)"
    }

    # Fix: stop VM, set DVD as first boot device, restart
    if ($dvds -and $dvds[0].Path) {
        Write-Host ""
        Write-Host "  Fixing: setting DVD as first boot device..." -ForegroundColor Yellow

        if ($vm.State -ne "Off") {
            Write-Host "  Stopping VM..."
            Stop-VM -Name $vmName -Force -TurnOff
            Start-Sleep -Seconds 2
        }

        $dvd = $dvds[0]
        Set-VMFirmware -VMName $vmName -FirstBootDevice $dvd
        Write-Host "  FirstBootDevice set to DVD ($($dvd.Path))"

        # Verify
        $fw2 = Get-VMFirmware -VMName $vmName
        Write-Host "  New boot order:"
        foreach ($entry in $fw2.BootOrder) {
            Write-Host "    $($entry.BootType) - $($entry.Device)"
        }

        Write-Host "  Starting VM..."
        Start-VM -Name $vmName
        Start-Sleep -Seconds 2
        try {
            Start-Process "vmconnect.exe" -ArgumentList "localhost", $vmName
        } catch {
            Write-Host "  Could not launch vmconnect - open from Hyper-V Manager." -ForegroundColor Yellow
        }
        Write-Host "  Done." -ForegroundColor Green
    } else {
        Write-Host "  No DVD drive with media found!" -ForegroundColor Red
        Write-Host "  Attach an ISO first:"
        Write-Host "    Add-VMDvdDrive -VMName $vmName -Path <iso-path>"
    }
}

Write-Host ""
