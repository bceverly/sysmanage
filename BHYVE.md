# FreeBSD bhyve Child Host Support Implementation Plan

This document outlines the phased implementation plan for adding FreeBSD bhyve child host support to sysmanage, sysmanage-agent, and sysmanage-docs.

## Overview

bhyve is FreeBSD's native Type-2 hypervisor, providing hardware-assisted virtualization for running guest operating systems. Unlike containers, bhyve creates full virtual machines with their own kernels. Key characteristics:

- Requires CPU virtualization support (Intel VT-x with EPT, or AMD-V with RVI)
- Managed via `bhyve`, `bhyvectl`, and `bhyveload` commands
- Supports UEFI boot (required for non-FreeBSD guests)
- Uses ZFS datasets or file-based disk images
- Network via tap interfaces bridged to physical/virtual interfaces
- Console access via nmdm (null modem) devices or VNC

## Key Differences from Other Hypervisors

| Aspect | KVM/QEMU | VMM/VMD (OpenBSD) | bhyve (FreeBSD) |
|--------|----------|-------------------|-----------------|
| Platform | Linux | OpenBSD | FreeBSD |
| Management | virsh/libvirt | vmctl | bhyvectl/vm-bhyve |
| Disk format | qcow2, raw | raw | raw, ZFS zvol |
| Console | VNC, serial | serial only | nmdm, VNC (UEFI) |
| Boot method | BIOS/UEFI | BIOS | bhyveload/UEFI |
| Network | virbr0, macvtap | vmd local | tap + bridge |
| Guest support | Wide | OpenBSD, Linux | FreeBSD, Linux, Windows |
| Cloud-init | Yes | Partial | Yes (with UEFI) |

---

## Phase 1: bhyve Detection and Role Support

**Goal:** Detect bhyve capability on FreeBSD hosts and display "bhyve Host" role in the UI.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_virtualization_checks.py`**
  - [ ] Add `check_bhyve_support()` method to detect:
    - [ ] Platform is FreeBSD (`platform.system() == "FreeBSD"`)
    - [ ] `bhyvectl` command exists (`shutil.which("bhyvectl")`)
    - [ ] `vmm.ko` kernel module loaded (`kldstat | grep vmm`)
    - [ ] `/dev/vmm` directory exists (kernel support enabled)
    - [ ] CPU virtualization support (`sysctl hw.vmm.vmx.initialized` or `hw.vmm.svm.initialized`)
  - [ ] Return detailed capability dict:
    ```python
    {
        "available": True/False,  # bhyvectl exists
        "enabled": True/False,    # vmm.ko loaded
        "running": True/False,    # ready to create VMs
        "initialized": True/False,
        "cpu_supported": True/False,  # VT-x/AMD-V with EPT/RVI
        "kernel_supported": True/False,  # vmm.ko loadable
        "uefi_available": True/False,  # UEFI firmware present
    }
    ```

- [ ] **`src/sysmanage_agent/collection/role_detection.py`**
  - [ ] Add `bhyve_host` to `role_mappings` dict with `special_detection=True`
  - [ ] Implement `_detect_bhyve_host_role()` method:
    - [ ] Check for bhyvectl binary
    - [ ] Verify vmm.ko is loaded
    - [ ] Get bhyve version info
    - [ ] Return role dict with capability status

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Add bhyve to `check_virtualization_support()` for FreeBSD platform
  - [ ] Add platform check: `if platform.system() == "FreeBSD"`

### sysmanage (Backend) Changes

- [ ] **`backend/security/roles.py`**
  - [ ] Add `BHYVE_HOST` role constant if not already present
  - [ ] Ensure role is included in role display mappings

### sysmanage-docs Changes

- [ ] **Documentation**
  - [ ] Add bhyve section to child-host-management.html
  - [ ] Document bhyve detection and requirements

### Testing Checklist
- [ ] bhyve Host role appears on FreeBSD hosts with vmm.ko loaded
- [ ] Role does not appear on non-FreeBSD systems
- [ ] Role shows correct capability status

---

## Phase 2: bhyve Setup/Initialization Support

**Goal:** Allow users to enable and initialize bhyve on FreeBSD hosts that have it available but not configured.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_bhyve.py`** (NEW FILE)
  - [ ] Create `BhyveOperations` class with:
    - [ ] `__init__(self, agent, logger)` - standard initialization
    - [ ] `async def initialize_bhyve(self) -> Dict` - enable bhyve:
      ```
      1. Load vmm.ko module: kldload vmm
      2. Add vmm_load="YES" to /boot/loader.conf for persistence
      3. Verify /dev/vmm is accessible
      4. Check for UEFI firmware (bhyve-firmware package)
      5. Install vm-bhyve if desired (optional helper tool)
      ```
    - [ ] `async def check_bhyve_ready(self) -> Dict` - verify bhyve is operational
  - [ ] Handle case where reboot is required (rare for bhyve)

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Import and instantiate `BhyveOperations`
  - [ ] Add handler for `initialize_bhyve` message type
  - [ ] Route bhyve initialization requests

### sysmanage (Backend) Changes

- [ ] **`backend/api/child_host_virtualization.py`**
  - [ ] Add `enable_bhyve` endpoint (similar to `enable_vmm`)
  - [ ] Handle initialization status response
  - [ ] Add `get_bhyve_status` endpoint

- [ ] **`backend/api/child_host_models.py`**
  - [ ] Add `EnableBhyveRequest` model if needed
  - [ ] Add `BhyveStatusResponse` model

- [ ] **`backend/websocket/messages.py`**
  - [ ] Add message types for bhyve initialization:
    - [ ] `INITIALIZE_BHYVE`
    - [ ] `BHYVE_INITIALIZED`
    - [ ] `BHYVE_INITIALIZATION_FAILED`

### sysmanage (Frontend) Changes

- [ ] **Enable bhyve button in Host Detail view**
  - [ ] Show when bhyve available but not enabled
  - [ ] Handle initialization result UI notification

### sysmanage-docs Changes

- [ ] **i18n/l10n**
  - [ ] Add "Enable bhyve" strings to all 14 locale files

### Testing Checklist
- [ ] "Enable bhyve" button appears on eligible FreeBSD hosts
- [ ] Enabling bhyve loads vmm.ko module
- [ ] Configuration persisted to /boot/loader.conf
- [ ] bhyve Host role appears after successful initialization

---

## Phase 3: bhyve Networking Configuration

**Goal:** Configure networking for bhyve virtual machines.

### Network Architecture Options

bhyve networking requires creating tap interfaces and bridging them:

1. **Bridge Mode** (recommended for most cases):
   ```
   Physical NIC (em0) <-> bridge0 <-> tap0 <-> VM
   ```
   - VMs get IPs from the same network as the host
   - Requires bridge interface configuration

2. **NAT Mode** (isolated VMs):
   ```
   VM <-> tap0 <-> bridge0 <-> NAT (pf) <-> Physical NIC
   ```
   - VMs on private subnet
   - Requires pf NAT rules

3. **Host-Only** (no external access):
   ```
   VM <-> tap0 <-> bridge0 (no physical member)
   ```
   - VMs can communicate with each other and host only

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_bhyve.py`**
  - [ ] `async def setup_bhyve_networking(self, config: Dict) -> Dict`
    - [ ] Create bridge interface if not exists: `ifconfig bridge0 create`
    - [ ] Add physical interface to bridge: `ifconfig bridge0 addm em0`
    - [ ] Configure bridge for VM use: `ifconfig bridge0 up`
    - [ ] Persist in /etc/rc.conf
  - [ ] `def _create_tap_interface(self, vm_name: str) -> str`
    - [ ] Create tap interface: `ifconfig tap create`
    - [ ] Add tap to bridge: `ifconfig bridge0 addm tapN`
    - [ ] Return tap interface name
  - [ ] `def _setup_nat_networking(self, subnet: str) -> Dict`
    - [ ] Configure private bridge for NAT
    - [ ] Add pf NAT rules
    - [ ] Enable IP forwarding if needed

- [ ] **Network configuration persistence:**
  - [ ] /etc/rc.conf entries for bridge and tap interfaces
  - [ ] /etc/pf.conf entries for NAT (if using NAT mode)

### sysmanage (Backend) Changes

- [ ] **`backend/api/child_host_virtualization.py`**
  - [ ] Add `configure_bhyve_networking` endpoint
  - [ ] Support network mode selection (bridge/nat/host-only)

### FreeBSD pf.conf Integration (NAT mode)

```
# bhyve NAT rules - added by sysmanage-agent
nat on $ext_if from <bhyve_subnet> to any -> ($ext_if)
pass from <bhyve_subnet> to any
```

### Testing Checklist
- [ ] Bridge interface created and configured
- [ ] VMs can reach external network (bridge mode)
- [ ] NAT mode works with pf rules
- [ ] Networking persists across reboots

---

## Phase 4: VM Distribution Management

**Goal:** Manage VM distributions (ISO images, cloud images) in the database.

### sysmanage (Backend) Changes

- [ ] **Database Migration** (new Alembic migration)
  - [ ] Add bhyve distributions to `child_host_distribution` table:
    ```
    child_type: "bhyve"
    distribution_name: "FreeBSD"
    distribution_version: "14.1"
    display_name: "FreeBSD 14.1-RELEASE"
    install_identifier: "FreeBSD-14.1-RELEASE-amd64-disc1.iso"
    iso_url: "https://download.freebsd.org/releases/amd64/amd64/ISO-IMAGES/14.1/..."
    agent_install_commands: [pkg install commands]
    cloud_image_url: "https://..."  # For cloud-init capable images
    enabled: true
    ```
  - [ ] Add other distributions with UEFI support:
    - [ ] Ubuntu Server 24.04 (cloud image)
    - [ ] Debian 12 (cloud image)
    - [ ] Alpine Linux (cloud image)
    - [ ] Windows Server (requires UEFI, manual install)

- [ ] **Cloud Image Support**
  - [ ] FreeBSD publishes VM images: https://download.freebsd.org/releases/VM-IMAGES/
  - [ ] Ubuntu/Debian cloud images work with UEFI boot
  - [ ] cloud-init supported via UEFI + config drive

### sysmanage (Frontend) Changes

- [ ] **`frontend/src/Pages/HostDetail.tsx`**
  - [ ] Set childType to 'bhyve' for FreeBSD hosts with bhyve capability
  - [ ] Update dialog title for bhyve
  - [ ] Update FQDN helper text for bhyve

### Testing Checklist
- [ ] bhyve distributions appear in UI when bhyve Host selected
- [ ] Distribution metadata correctly loaded from database
- [ ] Agent install commands valid for each distribution

---

## Phase 5: VM Creation and Agent Installation

**Goal:** Create VMs, install guest OS, and deploy sysmanage-agent.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_bhyve_types.py`** (NEW FILE)
  - [ ] Add `BhyveVmConfig` dataclass:
    ```python
    @dataclass
    class BhyveVmConfig:
        distribution: str
        vm_name: str
        hostname: str
        username: str
        password: str
        server_url: str
        agent_install_commands: List[str]
        memory: str = "1G"
        disk_size: str = "20G"
        cpus: int = 1
        server_port: int = 8443
        use_https: bool = True
        iso_url: str = ""
        cloud_image_url: str = ""
        use_uefi: bool = True
        use_cloud_init: bool = True
        network_mode: str = "bridge"  # bridge, nat, host-only
    ```

- [ ] **`src/sysmanage_agent/operations/child_host_bhyve_creation.py`** (NEW FILE)
  - [ ] `class BhyveCreation`:
    - [ ] `async def create_bhyve_vm(self, config: BhyveVmConfig) -> Dict`
      - Main creation workflow:
        ```
        1. Validate configuration
        2. Check for duplicate VM name
        3. Create ZFS dataset or disk image
        4. Create tap interface and add to bridge
        5. Download cloud image or ISO
        6. Create cloud-init ISO (if using cloud-init)
        7. Generate bhyve command or vm.conf
        8. Boot VM
        9. Wait for VM to get IP
        10. Wait for SSH availability
        11. Install sysmanage-agent via SSH
        12. Configure agent
        13. Start agent service
        14. Report success
        ```

    - [ ] `def _create_disk_image(self, path: str, size: str) -> Dict`
      - Option 1: ZFS zvol: `zfs create -V {size} zroot/bhyve/{vm_name}`
      - Option 2: File image: `truncate -s {size} {path}`

    - [ ] `def _vm_exists(self, vm_name: str) -> bool`
      - Check `/dev/vmm/{vm_name}` exists
      - Or check `bhyvectl --vm={vm_name} --get-stats`

    - [ ] `async def _boot_vm_uefi(self, config: BhyveVmConfig) -> Dict`
      - Build bhyve command with UEFI:
        ```bash
        bhyve -c {cpus} -m {memory} \
          -H -A -P \
          -s 0:0,hostbridge \
          -s 1:0,lpc \
          -s 2:0,virtio-net,{tap_if} \
          -s 3:0,virtio-blk,{disk_path} \
          -s 4:0,ahci-cd,{cloud_init_iso} \
          -l bootrom,/usr/local/share/uefi-firmware/BHYVE_UEFI.fd \
          -l com1,/dev/nmdm{N}A \
          {vm_name}
        ```

    - [ ] `async def _boot_vm_bhyveload(self, config: BhyveVmConfig) -> Dict`
      - For FreeBSD guests without UEFI:
        ```bash
        bhyveload -m {memory} -d {disk_path} {vm_name}
        bhyve -c {cpus} -m {memory} ...
        ```

    - [ ] `async def _wait_for_vm_ip(self, vm_name: str, tap_if: str, timeout: int) -> str`
      - Check ARP table: `arp -an | grep {tap_mac}`
      - Or check DHCP leases if running local DHCP

    - [ ] `async def _wait_for_ssh(self, ip: str, timeout: int) -> bool`
      - Attempt SSH connection until successful

    - [ ] `async def _install_agent_via_ssh(self, ip, user, password, commands) -> Dict`
      - Run agent installation commands
      - Configure agent with server URL/port
      - Start agent service

    - [ ] `async def _send_progress(self, step: str, message: str)`
      - Send progress updates to server

- [ ] **`src/sysmanage_agent/operations/child_host_bhyve_cloudinit.py`** (NEW FILE)
  - [ ] Generate cloud-init ISO for bhyve VMs
  - [ ] Similar to KVM cloud-init but adapted for bhyve
  - [ ] Use `makefs` or `mkisofs` to create ISO

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Import and use `BhyveVmConfig`
  - [ ] Route bhyve child host creation to `BhyveCreation.create_bhyve_vm()`
  - [ ] Add bhyve to `list_child_hosts()` for FreeBSD platform

- [ ] **`src/sysmanage_agent/operations/child_host_listing.py`**
  - [ ] Add `list_bhyve_vms()` method:
    - [ ] List VMs from `/dev/vmm/*`
    - [ ] Get status via `bhyvectl --vm={name} --get-stats`
    - [ ] Return list with name, status, etc.

### VM Lifecycle Management with bhyve

bhyve VMs are ephemeral by default - the VM device is destroyed when bhyve exits. For persistent VMs:

- [ ] **Device persistence**
  - [ ] Create /dev/vmm/{name} persists while VM runs
  - [ ] On clean shutdown, device is removed
  - [ ] On crash, may need `bhyvectl --vm={name} --destroy`

- [ ] **Process management**
  - [ ] bhyve runs as a foreground process
  - [ ] Use daemon(8) or supervisor to background
  - [ ] Consider using vm-bhyve for easier management

### sysmanage (Backend) Changes

- [ ] **`backend/api/handlers/child_host/virtualization.py`**
  - [ ] Add `handle_bhyve_initialize_result()` handler
  - [ ] Handle bhyve VM creation progress/result

- [ ] **`backend/websocket/messages.py`**
  - [ ] Add `BHYVE_VM_CREATED` message type
  - [ ] Add `BHYVE_VM_CREATION_FAILED` message type
  - [ ] Add `BHYVE_VM_PROGRESS` message type

### Testing Checklist
- [ ] VM disk image/zvol created successfully
- [ ] VM boots with UEFI
- [ ] VM gets IP address via DHCP
- [ ] SSH connection established
- [ ] Agent installed and configured
- [ ] Agent connects to sysmanage server
- [ ] Child host appears in Pending Hosts

---

## Phase 6: VM Lifecycle Control

**Goal:** Implement start/stop/restart/delete operations for bhyve VMs.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_bhyve_lifecycle.py`** (NEW FILE)
  - [ ] `class BhyveLifecycle`:
    - [ ] `async def start_vm(self, vm_name: str) -> Dict`
      - [ ] Check if VM device exists (already running)
      - [ ] Load with bhyveload or boot with UEFI
      - [ ] Start bhyve process (daemonized)
      - [ ] Wait for VM to be running

    - [ ] `async def stop_vm(self, vm_name: str, force: bool = False) -> Dict`
      - [ ] Graceful: Send ACPI poweroff via bhyvectl
        ```bash
        bhyvectl --vm={vm_name} --force-poweroff
        ```
      - [ ] Or send shutdown command via SSH if agent running
      - [ ] Force: Kill bhyve process and destroy device
        ```bash
        pkill -f "bhyve: {vm_name}"
        bhyvectl --vm={vm_name} --destroy
        ```

    - [ ] `async def restart_vm(self, vm_name: str) -> Dict`
      - [ ] Stop VM
      - [ ] Wait for clean shutdown
      - [ ] Start VM

    - [ ] `async def delete_vm(self, vm_name: str, delete_disk: bool = True) -> Dict`
      - [ ] Stop VM if running
      - [ ] Destroy VM device: `bhyvectl --vm={vm_name} --destroy`
      - [ ] Delete disk image/zvol if requested
      - [ ] Remove tap interface
      - [ ] Clean up any configuration files

    - [ ] `async def get_vm_status(self, vm_name: str) -> Dict`
      - [ ] Check if /dev/vmm/{vm_name} exists
      - [ ] Get stats via bhyvectl
      - [ ] Return: running/stopped, memory, vcpus

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Route control operations to BhyveLifecycle:
    - [ ] `start_child_host` for bhyve type
    - [ ] `stop_child_host` for bhyve type
    - [ ] `restart_child_host` for bhyve type
    - [ ] `delete_child_host` for bhyve type

### Console Access (Future Enhancement)

- [ ] **nmdm (null modem) console**
  - [ ] Each VM can have a serial console via nmdm device pair
  - [ ] `/dev/nmdmNA` connected to bhyve
  - [ ] `/dev/nmdmNB` accessible from host via `cu -l /dev/nmdmNB`
  - [ ] Could expose via web terminal in future

- [ ] **VNC console (UEFI only)**
  - [ ] Add `-s 29,fbuf,tcp=0.0.0.0:5900,w=1024,h=768` to bhyve
  - [ ] VNC accessible on port 5900+N
  - [ ] Could expose via noVNC in UI

### Testing Checklist
- [ ] Start stopped VM
- [ ] Stop running VM (graceful)
- [ ] Force stop hung VM
- [ ] Restart VM
- [ ] Delete VM and disk
- [ ] VM status correctly reported
- [ ] Operations work from UI

---

## Phase 7: Documentation and i18n/l10n

**Goal:** Complete documentation and translations for all bhyve features.

### sysmanage-docs Changes

- [ ] **`child-host-management.html`**
  - [ ] Add bhyve section (similar to LXD, WSL, VMM sections)
  - [ ] Overview and requirements
  - [ ] Detection and role explanation
  - [ ] Setup instructions
  - [ ] VM creation process
  - [ ] Networking configuration
  - [ ] Supported distributions
  - [ ] Comparison table (bhyve vs KVM vs VMM vs LXD vs WSL)
  - [ ] Troubleshooting section

- [ ] **i18n/l10n - All 14 locale JSON files:**
  - [ ] `en.json` - English (base)
  - [ ] `de.json` - German
  - [ ] `es.json` - Spanish
  - [ ] `fr.json` - French
  - [ ] `ar.json` - Arabic
  - [ ] `it.json` - Italian
  - [ ] `ko.json` - Korean
  - [ ] `ja.json` - Japanese
  - [ ] `hi.json` - Hindi
  - [ ] `zh_CN.json` - Simplified Chinese
  - [ ] `zh_TW.json` - Traditional Chinese
  - [ ] `pt.json` - Portuguese
  - [ ] `nl.json` - Dutch
  - [ ] `ru.json` - Russian

### Translation Keys to Add

```
docs.admin.child_host.bhyve.title
docs.admin.child_host.bhyve.overview_title
docs.admin.child_host.bhyve.overview_desc
docs.admin.child_host.bhyve.requirements_title
docs.admin.child_host.bhyve.req_freebsd
docs.admin.child_host.bhyve.req_cpu
docs.admin.child_host.bhyve.req_vmm
docs.admin.child_host.bhyve.req_uefi
docs.admin.child_host.bhyve.detection_title
docs.admin.child_host.bhyve.detection_desc
docs.admin.child_host.bhyve.setup_title
docs.admin.child_host.bhyve.setup_desc
docs.admin.child_host.bhyve.setup_step1 (kldload vmm)
docs.admin.child_host.bhyve.setup_step2 (loader.conf)
docs.admin.child_host.bhyve.setup_step3 (verify /dev/vmm)
docs.admin.child_host.bhyve.creation_title
docs.admin.child_host.bhyve.creation_desc
docs.admin.child_host.bhyve.creation_steps
docs.admin.child_host.bhyve.networking_title
docs.admin.child_host.bhyve.networking_desc
docs.admin.child_host.bhyve.net_bridge
docs.admin.child_host.bhyve.net_nat
docs.admin.child_host.bhyve.net_hostonly
docs.admin.child_host.bhyve.distributions_title
docs.admin.child_host.bhyve.distributions_desc
docs.admin.child_host.bhyve.comparison_title
docs.admin.child_host.bhyve.troubleshooting
```

### sysmanage (Backend) i18n

- [ ] **`backend/i18n/locales/*/LC_MESSAGES/messages.po`**
  - [ ] Add bhyve-related backend strings for all 14 locales

### sysmanage (Frontend) i18n

- [ ] **`frontend/public/locales/*/translation.json`**
  - [ ] Add bhyve-related UI strings for all 14 locales

### Testing Checklist
- [ ] Documentation renders correctly
- [ ] All locale files valid JSON/PO
- [ ] No missing translation keys
- [ ] UI displays correctly in all languages

---

## Implementation Notes

### bhyve vs vm-bhyve

Consider whether to use raw bhyve commands or the vm-bhyve wrapper:

**Raw bhyve:**
- More control, fewer dependencies
- Must manage device lifecycle manually
- Must build complex command lines

**vm-bhyve:**
- Simpler configuration files
- Handles ZFS datasets automatically
- Manages network interfaces
- Provides `vm list`, `vm start`, `vm stop` commands
- Adds a dependency

Recommendation: Start with raw bhyve for full control, consider vm-bhyve integration later.

### ZFS Integration

FreeBSD commonly uses ZFS. Consider:
- Creating a dedicated dataset: `zroot/bhyve`
- Each VM gets a child dataset: `zroot/bhyve/{vm_name}`
- Disk images as zvols: `zroot/bhyve/{vm_name}/disk0`
- Snapshots for backup/restore (future feature)

### UEFI Firmware

Required for non-FreeBSD guests. Install via:
```bash
pkg install bhyve-firmware
```

Firmware location: `/usr/local/share/uefi-firmware/BHYVE_UEFI.fd`

### Error Handling

- VM creation can fail at many points - provide clear rollback
- bhyve process crashes leave /dev/vmm device behind - need cleanup
- SSH connection failures should include troubleshooting hints
- Disk space checks before creating large disk images
- Timeout handling for long-running operations

### Security Considerations

- VMs run as root by default (bhyve limitation)
- Network isolation via separate bridges
- Consider firewall rules for VM-to-host communication
- Secure password handling during agent configuration

### Performance Considerations

- UEFI boot is slower than bhyveload
- ZFS zvols perform better than file images
- virtio drivers recommended for best performance
- Progress updates essential for user experience

---

## Dependencies

### System Requirements (FreeBSD Host)
- FreeBSD 12.0 or later (13.x or 14.x recommended)
- CPU with VT-x/EPT (Intel) or AMD-V/RVI (AMD) support
- vmm.ko kernel module
- bhyve-firmware package (for UEFI guests)
- Sufficient disk space for VM images
- Network interface for bridging

### Python Packages (sysmanage-agent)
- Existing dependencies should be sufficient
- May need asyncssh or paramiko for SSH operations (already available)

### FreeBSD Packages
```bash
pkg install bhyve-firmware    # UEFI firmware
pkg install grub2-bhyve       # Optional: for GRUB-based Linux guests
pkg install vm-bhyve          # Optional: management wrapper
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| UEFI boot complexity | Medium | Medium | Good defaults, fallback to bhyveload for FreeBSD |
| Network bridge configuration | Medium | High | Validate bridge exists before VM creation |
| ZFS vs file image choice | Low | Low | Support both, prefer ZFS when available |
| bhyve process management | Medium | Medium | Use daemon(8), implement proper cleanup |
| SSH setup failures | Medium | High | Robust retry logic, clear error messages |
| Long boot times | Medium | Low | Progress updates, async operations |

---

## Success Criteria

1. bhyve Host role detected on FreeBSD systems with vmm.ko
2. Users can enable bhyve from the UI
3. VM creation works with supported distributions
4. Cloud-init properly configures VMs
5. Agent auto-installs and connects to server
6. VM lifecycle operations (start/stop/restart/delete) work
7. Full documentation in all 14 languages
8. All existing tests pass
9. New tests cover bhyve functionality

---

## Command Reference

### Detection
```bash
# Check if bhyve is available
which bhyvectl

# Check if vmm.ko is loaded
kldstat | grep vmm

# Check CPU virtualization support
sysctl hw.vmm.vmx.initialized    # Intel
sysctl hw.vmm.svm.initialized    # AMD
```

### Setup
```bash
# Load vmm kernel module
kldload vmm

# Persist across reboots
echo 'vmm_load="YES"' >> /boot/loader.conf

# Install UEFI firmware
pkg install bhyve-firmware
```

### Networking
```bash
# Create bridge
ifconfig bridge0 create
ifconfig bridge0 addm em0
ifconfig bridge0 up

# Create tap for VM
ifconfig tap0 create
ifconfig bridge0 addm tap0
```

### VM Management
```bash
# Create disk image
truncate -s 20G /vm/myvm/disk0.img
# Or with ZFS
zfs create -V 20G zroot/bhyve/myvm/disk0

# Boot with UEFI
bhyve -c 2 -m 2G -H -A -P \
  -s 0:0,hostbridge \
  -s 1:0,lpc \
  -s 2:0,virtio-net,tap0 \
  -s 3:0,virtio-blk,/vm/myvm/disk0.img \
  -l bootrom,/usr/local/share/uefi-firmware/BHYVE_UEFI.fd \
  myvm

# Stop VM
bhyvectl --vm=myvm --force-poweroff

# Destroy VM device
bhyvectl --vm=myvm --destroy

# List running VMs
ls /dev/vmm/
```
