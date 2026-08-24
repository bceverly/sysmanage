#Requires -RunAsAdministrator
# Diagnose why the DVD is being skipped despite being first in boot order.

$ErrorActionPreference = "Stop"

foreach ($vmName in @("pxe-server", "pxe-router")) {
    Write-Host "`n=== $vmName ===" -ForegroundColor Cyan

    $vm = Get-VM -Name $vmName -ErrorAction SilentlyContinue
    if (-not $vm) {
        Write-Host "  VM not found, skipping."
        continue
    }

    # Stop if running
    if ($vm.State -ne "Off") {
        Write-Host "  Stopping VM..."
        Stop-VM -Name $vmName -Force -TurnOff
        Start-Sleep -Seconds 2
    }

    # Check Secure Boot state and template
    $fw = Get-VMFirmware -VMName $vmName
    Write-Host "  SecureBoot         : $($fw.SecureBoot)"
    Write-Host "  SecureBootTemplate : $($fw.SecureBootTemplate)"
    Write-Host "  PreferredMachineGen: $($fw.PreferredNetworkBootProtocol)"

    # Check DVD details
    $dvd = Get-VMDvdDrive -VMName $vmName
    Write-Host "  DVD Path           : $($dvd.Path)"
    Write-Host "  DVD ControllerType : $($dvd.ControllerType)"
    Write-Host "  DVD ControllerNum  : $($dvd.ControllerNumber)"
    Write-Host "  DVD ControllerLoc  : $($dvd.ControllerLocation)"

    # Try fix 1: Set Secure Boot template to MicrosoftUEFICertificateAuthority
    # (the default is MicrosoftWindows which may reject non-Windows bootloaders)
    Write-Host ""
    Write-Host "  Fix: Setting SecureBootTemplate to MicrosoftUEFICertificateAuthority..." -ForegroundColor Yellow
    Set-VMFirmware -VMName $vmName -SecureBootTemplate "MicrosoftUEFICertificateAuthority"

    # Verify
    $fw2 = Get-VMFirmware -VMName $vmName
    Write-Host "  SecureBoot         : $($fw2.SecureBoot)"
    Write-Host "  SecureBootTemplate : $($fw2.SecureBootTemplate)"

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
