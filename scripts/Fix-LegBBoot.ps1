#Requires -RunAsAdministrator
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

# Diagnose and repair the Leg B (UEFI / Gen 2) PXE client.
#
# Symptom this addresses: the VM shows "no install media" and never sends a
# DHCPDISCOVER -- nothing reaches dnsmasq at all.  That is a firmware/boot-order
# problem on the client, not a proxyDHCP problem on the server.
#
# Run from an elevated PowerShell:
#   .\scripts\Fix-LegBBoot.ps1

$ErrorActionPreference = "Stop"

$VMName     = "pxe-client-uefi"
$SwitchName = "SysManage PXE Test"
$StaticMAC  = "00155DA10102"

$vm = Get-VM -Name $VMName -ErrorAction SilentlyContinue
if (-not $vm) { Write-Host "VM '$VMName' not found." -ForegroundColor Red; exit 1 }

Write-Host "`n=== BEFORE ===" -ForegroundColor Cyan
Write-Host "  State                : $($vm.State)"
Write-Host "  Generation           : $($vm.Generation)"

$fw = Get-VMFirmware -VMName $VMName
Write-Host "  SecureBoot           : $($fw.SecureBoot)"
Write-Host "  SecureBootTemplate   : $($fw.SecureBootTemplate)"
# If this is IPv6, the firmware does DHCPv6 -- which our IPv4 proxyDHCP never
# sees, and which looks exactly like "no PXE attempt" from the server side.
Write-Host "  NetworkBootProtocol  : $($fw.PreferredNetworkBootProtocol)"
Write-Host "  BootOrder:"
if ($fw.BootOrder.Count -eq 0) {
    Write-Host "    (EMPTY - nothing to boot, this alone explains the symptom)" -ForegroundColor Red
}
foreach ($e in $fw.BootOrder) {
    Write-Host "    $($e.BootType) - $($e.Device)"
}

foreach ($n in (Get-VMNetworkAdapter -VMName $VMName)) {
    Write-Host "  NIC: switch='$($n.SwitchName)' MAC=$($n.MacAddress) status=$($n.Status) connected=$($n.Connected)"
}

$snaps = Get-VMSnapshot -VMName $VMName -ErrorAction SilentlyContinue
if ($snaps) {
    Write-Host "  Checkpoints (can restore stale firmware state):" -ForegroundColor Yellow
    foreach ($s in $snaps) { Write-Host "    $($s.Name) ($($s.CreationTime))" }
} else {
    Write-Host "  Checkpoints          : none"
}

# --- repair ---------------------------------------------------------------
Write-Host "`n=== REPAIR ===" -ForegroundColor Yellow

if ($vm.State -ne "Off") { Write-Host "  Stopping VM..."; Stop-VM -Name $VMName -Force -TurnOff; Start-Sleep -Seconds 2 }

Set-VM -Name $VMName -AutomaticCheckpointsEnabled $false
if ($snaps) { Write-Host "  Removing checkpoints..."; $snaps | Remove-VMSnapshot -Confirm:$false; Start-Sleep -Seconds 3 }

Write-Host "  Secure Boot -> Off (our sysmanage-ipxe.efi is not MS-CA signed)"
Set-VMFirmware -VMName $VMName -EnableSecureBoot Off

Write-Host "  Network boot protocol -> IPv4"
Set-VMFirmware -VMName $VMName -PreferredNetworkBootProtocol IPv4

$nic = Get-VMNetworkAdapter -VMName $VMName | Select-Object -First 1
if ($nic.SwitchName -ne $SwitchName) {
    Write-Host "  Reconnecting NIC to '$SwitchName' (was '$($nic.SwitchName)')" -ForegroundColor Yellow
    Connect-VMNetworkAdapter -VMName $VMName -Name $nic.Name -SwitchName $SwitchName
}
$nic = Get-VMNetworkAdapter -VMName $VMName | Select-Object -First 1
if (($nic.MacAddress -replace '[-:]','') -ne $StaticMAC) {
    Write-Host "  Setting static MAC $StaticMAC (was $($nic.MacAddress))" -ForegroundColor Yellow
    Set-VMNetworkAdapter -VMName $VMName -Name $nic.Name -StaticMacAddress $StaticMAC
}

Write-Host "  Setting the network adapter as FirstBootDevice"
$nic = Get-VMNetworkAdapter -VMName $VMName | Select-Object -First 1
Set-VMFirmware -VMName $VMName -FirstBootDevice $nic

Write-Host "`n=== AFTER ===" -ForegroundColor Green
$fw2 = Get-VMFirmware -VMName $VMName
Write-Host "  SecureBoot           : $($fw2.SecureBoot)"
Write-Host "  NetworkBootProtocol  : $($fw2.PreferredNetworkBootProtocol)"
Write-Host "  BootOrder:"
foreach ($e in $fw2.BootOrder) { Write-Host "    $($e.BootType) - $($e.Device)" }
$n2 = Get-VMNetworkAdapter -VMName $VMName | Select-Object -First 1
Write-Host "  NIC: switch='$($n2.SwitchName)' MAC=$($n2.MacAddress)"

Write-Host "`n  Starting VM..."
Start-VM -Name $VMName
Start-Sleep -Seconds 2
try { Start-Process "vmconnect.exe" -ArgumentList "localhost", $VMName } catch {
    Write-Host "  Could not launch vmconnect - open it from Hyper-V Manager." -ForegroundColor Yellow
}
Write-Host "  Done.`n" -ForegroundColor Green
