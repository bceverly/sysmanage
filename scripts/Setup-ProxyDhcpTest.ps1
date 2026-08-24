# Copyright (c) 2024-2026 Bryan Everly. All rights reserved.
# Licensed under the AGPLv3. See the LICENSE file in the project root.
#
# Setup-ProxyDhcpTest.ps1
#
# Automates the Hyper-V test rig described in docs/planning/PROXYDHCP-HARDWARE-TEST.md.
# Creates an all-virtual environment on an Internal vSwitch so no physical Ethernet
# cable is required.  The "someone else's DHCP" role is played by a small Linux VM
# instead of the home router.
#
# What this script creates:
#
#   1. An Internal vSwitch ("SysManage PXE Test")
#   2. A "router" Linux VM   - plays the role of the existing DHCP server
#   3. A "pxeserver" Linux VM - runs dnsmasq in proxyDHCP mode + TFTP + sysmanage
#   4. A Gen 1 client VM      - Leg A (BIOS, Legacy NIC, Microsoft PXE ROM)
#   5. A Gen 2 client VM      - Leg B (UEFI, Secure Boot off)
#   6. A Gen 1 control VM     - negative control (no MAC assignment)
#
# After running this script:
#   - Install Linux on the router and pxeserver VMs (attach an ISO first)
#   - Run the generated setup scripts inside each Linux VM
#   - Follow the test procedure in PROXYDHCP-HARDWARE-TEST.md
#
# Usage (elevated PowerShell):
#   .\scripts\Setup-ProxyDhcpTest.ps1
#   .\scripts\Setup-ProxyDhcpTest.ps1 -IsoPath "C:\ISOs\ubuntu-24.04-live-server-amd64.iso"
#   .\scripts\Setup-ProxyDhcpTest.ps1 -Destroy   # tear everything down
#
# All VM disks and generated configs land under $BasePath (default: C:\Hyper-V\PXE-Test).

#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    # Path to a Linux installer ISO.  Attached to the router and pxeserver VMs.
    [string]$IsoPath,

    # Root directory for VM disks and generated config files.
    [string]$BasePath = "C:\Hyper-V\PXE-Test",

    # Subnet prefix (first three octets).  .1 = router, .50 = pxeserver.
    [string]$Subnet = "10.99.0",

    # Name of the Internal vSwitch.
    [string]$SwitchName = "SysManage PXE Test",

    # Tear down everything this script created.
    [switch]$Destroy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
$RouterVMName     = "pxe-router"
$PxeServerVMName  = "pxe-server"
$LegAVMName       = "pxe-client-bios"
$LegBVMName       = "pxe-client-uefi"
$ControlVMName    = "pxe-client-control"

$RouterIP         = "$Subnet.1"
$PxeServerIP      = "$Subnet.50"
$DhcpRangeStart   = "$Subnet.100"
$DhcpRangeEnd     = "$Subnet.200"
$NetMask          = "255.255.255.0"

# Static MACs - Hyper-V requires them in the 00:15:5D:xx:xx:xx range.
$LegAMAC          = "00155DA10101"
$LegBMAC          = "00155DA10102"
$ControlMAC       = "00155DA10199"

$ConfigDir        = Join-Path $BasePath "configs"

# ---------------------------------------------------------------------------
# Destroy mode
# ---------------------------------------------------------------------------
if ($Destroy) {
    Write-Host "`n=== Tearing down PXE test rig ===" -ForegroundColor Yellow

    foreach ($vm in @($ControlVMName, $LegBVMName, $LegAVMName, $PxeServerVMName, $RouterVMName)) {
        $existing = Get-VM -Name $vm -ErrorAction SilentlyContinue
        if ($existing) {
            if ($existing.State -ne "Off") {
                Write-Host "  Stopping $vm..."
                Stop-VM -Name $vm -Force -TurnOff
            }
            Write-Host "  Removing $vm..."
            Remove-VM -Name $vm -Force
        }
    }

    $sw = Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue
    if ($sw) {
        Write-Host "  Removing vSwitch '$SwitchName'..."
        Remove-VMSwitch -Name $SwitchName -Force
    }

    if (Test-Path $BasePath) {
        Write-Host "  Removing $BasePath..."
        Remove-Item -Path $BasePath -Recurse -Force
    }

    Write-Host "`nDone.  All PXE test resources removed.`n" -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
Write-Host "`n=== SysManage proxyDHCP test rig setup ===" -ForegroundColor Cyan
Write-Host "  Base path : $BasePath"
Write-Host "  Subnet    : $Subnet.0/24"
Write-Host "  Switch    : $SwitchName"
if ($IsoPath) {
    if (-not (Test-Path $IsoPath)) {
        Write-Error "ISO not found: $IsoPath"
    }
    Write-Host "  ISO       : $IsoPath"
} else {
    Write-Host '  ISO       : (none - attach one manually before installing Linux)' -ForegroundColor Yellow
}
Write-Host ""

# Create directories
foreach ($dir in @($BasePath, $ConfigDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# ---------------------------------------------------------------------------
# 1. Internal vSwitch
# ---------------------------------------------------------------------------
Write-Host '[vSwitch]' -ForegroundColor Cyan
$sw = Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue
if ($sw) {
    Write-Host "  '$SwitchName' already exists - reusing."
} else {
    Write-Host "  Creating Internal vSwitch '$SwitchName'..."
    New-VMSwitch -Name $SwitchName -SwitchType Internal | Out-Null
    Write-Host "  Done."
}

# Assign an IP to the host's virtual adapter for this switch so we can reach
# the VMs from the host if needed (useful for SCP-ing files in).
$adapter = Get-NetAdapter | Where-Object { $_.Name -like "*$SwitchName*" }
if ($adapter) {
    $existingIP = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -like "$Subnet.*" }
    if (-not $existingIP) {
        Write-Host "  Assigning $Subnet.254/24 to host adapter for file transfer access..."
        New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress "$Subnet.254" -PrefixLength 24 | Out-Null
    }
}

# ---------------------------------------------------------------------------
# Helper: create a VM
# ---------------------------------------------------------------------------
function New-PxeTestVM {
    param(
        [string]$Name,
        [int]$Generation,
        [int64]$MemoryMB = 2048,
        [int64]$DiskGB = 20,
        [int]$CPUCount = 2,
        [string]$StaticMAC,
        [switch]$LegacyNIC,
        [switch]$DisableSecureBoot,
        [switch]$AttachISO
    )

    $existing = Get-VM -Name $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "  $Name already exists - skipping creation."
        return
    }

    $vhdPath = Join-Path $BasePath "$Name.vhdx"
    Write-Host "  Creating $Name (Gen $Generation, ${MemoryMB}MB RAM, ${DiskGB}GB disk)..."

    New-VM -Name $Name `
        -MemoryStartupBytes ($MemoryMB * 1MB) `
        -Generation $Generation `
        -NewVHDPath $vhdPath `
        -NewVHDSizeBytes ($DiskGB * 1GB) `
        -SwitchName $SwitchName | Out-Null

    Set-VMProcessor -VMName $Name -Count $CPUCount

    # Disable automatic checkpoints - they silently snapshot at every start,
    # causing the VM to restore old (pre-DVD) state instead of booting the ISO.
    Set-VM -Name $Name -AutomaticCheckpointsEnabled $false

    # Gen 2 server VMs need Secure Boot off to reliably boot Linux ISOs, and
    # client VMs need it off for unsigned iPXE EFI.  Just disable it for all
    # Gen 2 VMs in this test rig.
    if ($Generation -eq 2) {
        Set-VMFirmware -VMName $Name -EnableSecureBoot Off
    }

    # Gen 1 + Legacy NIC: the default synthetic NIC cannot PXE boot in Gen 1.
    # Add a Legacy NIC on the test switch and remove the synthetic one.
    if ($LegacyNIC) {
        # Remove the synthetic adapter that New-VM created.
        Get-VMNetworkAdapter -VMName $Name | Remove-VMNetworkAdapter
        Add-VMNetworkAdapter -VMName $Name -IsLegacy $true -SwitchName $SwitchName
    }

    if ($StaticMAC) {
        Get-VMNetworkAdapter -VMName $Name | Set-VMNetworkAdapter -StaticMacAddress $StaticMAC
    }

    if ($DisableSecureBoot) {
        Set-VMFirmware -VMName $Name -EnableSecureBoot Off
    }

    # Attach ISO for Linux installation.
    if ($AttachISO -and $IsoPath) {
        if ($Generation -eq 1) {
            Set-VMDvdDrive -VMName $Name -Path $IsoPath
        } else {
            Add-VMDvdDrive -VMName $Name -Path $IsoPath
        }
    }

    # Give Linux server VMs a second NIC on Default Switch for internet access
    # during package installation.  Add it BEFORE setting boot order so all
    # devices are present when the firmware order is written.
    if ($AttachISO) {
        $defaultSwitch = Get-VMSwitch -Name "Default Switch" -ErrorAction SilentlyContinue
        if ($defaultSwitch) {
            Add-VMNetworkAdapter -VMName $Name -SwitchName "Default Switch"
            Write-Host "    Added second NIC on Default Switch (internet access for apt/dnf)."
        }
    }

    # Boot order - set LAST, after all devices are attached.
    if ($Generation -eq 1) {
        if ($AttachISO -and $IsoPath) {
            Set-VMBios -VMName $Name -StartupOrder @("CD", "LegacyNetworkAdapter", "IDE", "Floppy")
        } else {
            Set-VMBios -VMName $Name -StartupOrder @("LegacyNetworkAdapter", "IDE", "CD", "Floppy")
        }
    } else {
        if ($AttachISO -and $IsoPath) {
            # Server VMs: DVD first so the Linux installer boots.
            $dvd = Get-VMDvdDrive -VMName $Name
            Set-VMFirmware -VMName $Name -FirstBootDevice $dvd
        } else {
            # Client VMs: network first (PXE boot).
            $nic = Get-VMNetworkAdapter -VMName $Name | Select-Object -First 1
            Set-VMFirmware -VMName $Name -FirstBootDevice $nic
        }
    }

    Write-Host "    Done."
}

# ---------------------------------------------------------------------------
# 2. Router VM - the "someone else's DHCP server"
# ---------------------------------------------------------------------------
Write-Host "`n[Router VM - plays the existing DHCP server]" -ForegroundColor Cyan
New-PxeTestVM -Name $RouterVMName -Generation 2 -MemoryMB 1024 -DiskGB 10 -CPUCount 1 -AttachISO

# ---------------------------------------------------------------------------
# 3. PXE Server VM - runs dnsmasq proxyDHCP + TFTP + sysmanage
# ---------------------------------------------------------------------------
Write-Host "`n[PXE Server VM - dnsmasq proxyDHCP + TFTP + sysmanage]" -ForegroundColor Cyan
New-PxeTestVM -Name $PxeServerVMName -Generation 2 -MemoryMB 4096 -DiskGB 40 -CPUCount 2 -AttachISO

# ---------------------------------------------------------------------------
# 4. Leg A client - Gen 1, BIOS, Legacy NIC (Microsoft PXE ROM)
# ---------------------------------------------------------------------------
Write-Host "`n[Leg A: BIOS client - Gen 1, Legacy NIC]" -ForegroundColor Cyan
New-PxeTestVM -Name $LegAVMName -Generation 1 -MemoryMB 2048 -DiskGB 10 -CPUCount 1 `
    -LegacyNIC -StaticMAC $LegAMAC

# ---------------------------------------------------------------------------
# 5. Leg B client - Gen 2, UEFI, Secure Boot off
# ---------------------------------------------------------------------------
Write-Host "`n[Leg B: UEFI client - Gen 2, Secure Boot off]" -ForegroundColor Cyan
New-PxeTestVM -Name $LegBVMName -Generation 2 -MemoryMB 2048 -DiskGB 10 -CPUCount 1 `
    -StaticMAC $LegBMAC -DisableSecureBoot

# ---------------------------------------------------------------------------
# 6. Negative control - Gen 1, Legacy NIC, different MAC, no assignment
# ---------------------------------------------------------------------------
Write-Host "`n[Negative control - Gen 1, no MAC assignment]" -ForegroundColor Cyan
New-PxeTestVM -Name $ControlVMName -Generation 1 -MemoryMB 2048 -DiskGB 10 -CPUCount 1 `
    -LegacyNIC -StaticMAC $ControlMAC

# ---------------------------------------------------------------------------
# 7. Generate config files for the Linux VMs
# ---------------------------------------------------------------------------
Write-Host "`n[Generating config files]" -ForegroundColor Cyan

# Format MACs with colons for display and dnsmasq configs.
$LegAMACFmt    = ($LegAMAC    -replace '(.{2})', '$1:').TrimEnd(':')
$LegBMACFmt    = ($LegBMAC    -replace '(.{2})', '$1:').TrimEnd(':')
$ControlMACFmt = ($ControlMAC -replace '(.{2})', '$1:').TrimEnd(':')

# --- Router dnsmasq.conf ---
$routerConf = @"
# Router VM - acts as the existing DHCP server for the proxyDHCP test.
# This is a plain DHCP server.  It hands out leases; it knows nothing about PXE.
# Drop this into /etc/dnsmasq.d/pxe-test.conf and restart dnsmasq, or run:
#   sudo dnsmasq --no-daemon --conf-file=/path/to/router-dnsmasq.conf
interface=eth0
bind-interfaces
dhcp-range=${DhcpRangeStart},${DhcpRangeEnd},${NetMask},12h
dhcp-option=option:router,${RouterIP}
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
port=0
"@
$routerConfPath = Join-Path $ConfigDir "router-dnsmasq.conf"
Set-Content -Path $routerConfPath -Value $routerConf -Encoding ASCII
Write-Host "  $routerConfPath"

# --- Router setup script ---
$routerSetup = @"
#!/usr/bin/env bash
# Setup script for the ROUTER VM (the "someone else's DHCP" role).
# Run this after installing Linux on the router VM.
set -euo pipefail

echo "=== Router VM setup ==="

# Install dnsmasq
if command -v apt-get &>/dev/null; then
    sudo apt-get update && sudo apt-get install -y dnsmasq
elif command -v dnf &>/dev/null; then
    sudo dnf install -y dnsmasq
elif command -v apk &>/dev/null; then
    sudo apk add dnsmasq
fi

# Configure static IP on the test network interface.
# Find the interface on the PXE test switch (not the Default Switch).
# After Linux installation, identify which interface is on the Internal switch
# (it will NOT have a DHCP lease).  Set it manually:
echo ""
echo "Configure a static IP on the Internal switch interface:"
echo "  sudo ip addr add ${RouterIP}/24 dev <interface>"
echo "  sudo ip link set <interface> up"
echo ""
echo "Then copy router-dnsmasq.conf to this VM and run:"
echo "  sudo dnsmasq --no-daemon --log-dhcp --conf-file=/path/to/router-dnsmasq.conf"
echo ""
echo "The router VM is ready when dnsmasq is serving leases on ${Subnet}.0/24."
"@
$routerSetupPath = Join-Path $ConfigDir "setup-router.sh"
Set-Content -Path $routerSetupPath -Value ($routerSetup -replace "`r`n", "`n") -NoNewline -Encoding ASCII
Write-Host "  $routerSetupPath"

# --- PXE server setup script ---
$pxeServerSetup = @"
#!/usr/bin/env bash
# Setup script for the PXE SERVER VM (dnsmasq proxyDHCP + TFTP + sysmanage).
# Run this after installing Linux on the pxe-server VM.
set -euo pipefail

echo "=== PXE Server VM setup ==="

# Install packages
if command -v apt-get &>/dev/null; then
    sudo apt-get update && sudo apt-get install -y dnsmasq tcpdump
elif command -v dnf &>/dev/null; then
    sudo dnf install -y dnsmasq tcpdump
elif command -v apk &>/dev/null; then
    sudo apk add dnsmasq tcpdump
fi

# Create TFTP root
sudo mkdir -p /var/lib/sysmanage/tftp

echo ""
echo "=== Manual steps remaining ==="
echo ""
echo "1. Configure a static IP on the Internal switch interface:"
echo "   sudo ip addr add ${PxeServerIP}/24 dev <interface>"
echo "   sudo ip link set <interface> up"
echo ""
echo "2. Build the iPXE artifacts on this VM (or copy them from another Linux box):"
echo "   cd /path/to/sysmanage-professional-plus"
echo "   sudo apt-get install -y git build-essential liblzma-dev"
echo "   scripts/build-embedded-ipxe.sh http://${PxeServerIP}:8080/api/v1/provisioning/boot.ipxe"
echo "   sudo cp storage/ipxe/sysmanage-ipxe.kpxe /var/lib/sysmanage/tftp/"
echo "   sudo cp storage/ipxe/sysmanage-ipxe.efi  /var/lib/sysmanage/tftp/"
echo ""
echo "3. Render the proxyDHCP config from the provisioning engine:"
echo "   cd /path/to/sysmanage-professional-plus"
echo "   .venv/bin/python -c \""
echo "   import sys; sys.path.insert(0,'tests')"
echo "   from _engine_loader import load_engine"
echo "   eng = load_engine('provisioning_engine')"
echo "   class R: pass"
echo "   r = R()"
echo "   r.mode='proxy'; r.server='dnsmasq'; r.interface='<interface>'"
echo "   r.subnet='${Subnet}.0'; r.netmask='${NetMask}'"
echo "   r.range_start=None; r.range_end=None; r.router=None; r.dns=None"
echo "   r.tftp_root='/var/lib/sysmanage/tftp'; r.boot_file='pxelinux.0'"
echo "   r.server_ip='${PxeServerIP}'"
echo "   r.ipxe_boot_url='http://${PxeServerIP}:8080/api/v1/provisioning/boot.ipxe'"
echo "   r.ipxe_image='undionly.kpxe'; r.ipxe_chain_file='sysmanage.ipxe'"
echo "   r.ipxe_embedded_image='sysmanage-ipxe.kpxe'; r.ipxe_efi_image='sysmanage-ipxe.efi'"
echo "   print(eng.render_dnsmasq_config(r))"
echo "   \" > /tmp/sysmanage-provisioning.conf"
echo ""
echo "4. Start the sysmanage server (it serves boot.ipxe)."
echo ""
echo "5. Create a MAC assignment in SysManage for the Leg A client:"
echo "   MAC: ${LegAMACFmt}"
echo "   And for Leg B:"
echo "   MAC: ${LegBMACFmt}"
echo "   The negative control MAC has NO assignment:"
echo "   MAC: ${ControlMACFmt}"
echo ""
echo "6. Open firewall ports:"
echo "   sudo ufw allow 67/udp    # DHCP"
echo "   sudo ufw allow 68/udp    # DHCP"
echo "   sudo ufw allow 4011/udp  # proxyDHCP"
echo "   sudo ufw allow 69/udp    # TFTP"
echo "   sudo ufw allow 8080/tcp  # sysmanage API"
echo "   (or equivalent for firewalld / nftables)"
echo ""
echo "7. Start dnsmasq (foreground, pristine config):"
echo "   sudo dnsmasq --no-daemon --log-dhcp --port=0 --conf-file=/tmp/sysmanage-provisioning.conf"
echo ""
echo "8. In a second terminal, start the packet capture:"
echo "   sudo tcpdump -i <interface> -n -vv 'port 67 or port 68 or port 4011 or port 69' -w proxydhcp.pcap"
echo ""
echo "9. Boot the client VMs from the Hyper-V console and watch."
"@
$pxeServerSetupPath = Join-Path $ConfigDir "setup-pxeserver.sh"
Set-Content -Path $pxeServerSetupPath -Value ($pxeServerSetup -replace "`r`n", "`n") -NoNewline -Encoding ASCII
Write-Host "  $pxeServerSetupPath"

# ---------------------------------------------------------------------------
# 8. Start the Linux VMs and open their consoles for installation
# ---------------------------------------------------------------------------
Write-Host "`n[Starting Linux VMs]" -ForegroundColor Cyan

foreach ($vm in @($RouterVMName, $PxeServerVMName)) {
    $state = (Get-VM -Name $vm).State
    if ($state -ne "Running") {
        Write-Host "  Starting $vm..."
        Start-VM -Name $vm
    } else {
        Write-Host "  $vm is already running."
    }
}

# Give them a moment to initialize before opening consoles.
Start-Sleep -Seconds 2

Write-Host "  Opening console windows (Hyper-V VMConnect)..."
Write-Host "  Install Linux on both VMs.  The client VMs are NOT started yet." -ForegroundColor Yellow
Write-Host "  Boot them only after the server side is fully configured." -ForegroundColor Yellow

foreach ($vm in @($RouterVMName, $PxeServerVMName)) {
    try {
        Start-Process "vmconnect.exe" -ArgumentList "localhost", $vm
    } catch {
        Write-Host "  Could not launch vmconnect for $vm - open it from Hyper-V Manager." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# 9. Summary
# ---------------------------------------------------------------------------
Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "VMs created:" -ForegroundColor White
Write-Host "  $RouterVMName        - existing DHCP server role (Gen 2, 1GB, 10GB disk)"
Write-Host "  $PxeServerVMName      - dnsmasq proxyDHCP + TFTP + sysmanage (Gen 2, 4GB, 40GB disk)"
Write-Host "  $LegAVMName  - Leg A: BIOS client (Gen 1, Legacy NIC, MAC $LegAMACFmt)"
Write-Host "  $LegBVMName  - Leg B: UEFI client (Gen 2, Secure Boot off, MAC $LegBMACFmt)"
Write-Host "  $ControlVMName - Negative control (Gen 1, Legacy NIC, MAC $ControlMACFmt)"
Write-Host ""
Write-Host "vSwitch:" -ForegroundColor White
Write-Host "  $SwitchName (Internal) - all VMs attached"
Write-Host "  Host adapter: $Subnet.254/24 (for SCP/SSH into VMs from this machine)"
Write-Host ""
Write-Host "Config files:" -ForegroundColor White
Write-Host "  $routerConfPath"
Write-Host "  $routerSetupPath"
Write-Host "  $pxeServerSetupPath"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
if (-not $IsoPath) {
    Write-Host "  1. Attach a Linux ISO to the router and pxeserver VMs:"
    Write-Host "       Set-VMDvdDrive -VMName $RouterVMName -Path <iso-path>"
    Write-Host "       Add-VMDvdDrive -VMName $PxeServerVMName -Path <iso-path>"
    Write-Host "  2. Boot and install Linux on both VMs."
} else {
    Write-Host "  1. Install Linux on both VMs (consoles should be open now)."
}
Write-Host "  2. SCP the config files from $ConfigDir into each VM."
Write-Host "     From this machine: scp <file> user@<vm-ip>:~/"
Write-Host "  3. Follow setup-router.sh on the router VM."
Write-Host "  4. Follow setup-pxeserver.sh on the PXE server VM."
Write-Host "  5. Boot the client VMs and observe the PXE boot chain."
Write-Host "  6. Verify pass criteria from PROXYDHCP-HARDWARE-TEST.md section 6."
Write-Host ""
Write-Host "To tear down:" -ForegroundColor Yellow
Write-Host "  .\scripts\Setup-ProxyDhcpTest.ps1 -Destroy"
Write-Host ""
