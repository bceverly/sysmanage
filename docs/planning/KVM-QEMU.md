# Linux KVM/QEMU Child Host Support Implementation Plan

This document outlines the phased implementation plan for adding Linux KVM/QEMU child host support to sysmanage, sysmanage-agent, and sysmanage-docs.

## Overview

KVM (Kernel-based Virtual Machine) is Linux's native hypervisor, typically managed via libvirt/virsh or direct QEMU commands. Like OpenBSD VMM, KVM creates full virtual machines with their own kernels, requiring:
- VM creation and disk management (qemu-img)
- OS installation (VNC/serial console, or cloud-init/autoinstall)
- Agent installation (SSH-based)
- Networking configuration (virbr0 NAT, bridged, macvtap)

## Key Differences from VMM and LXD

| Aspect | LXD | VMM/VMD | KVM/QEMU |
|--------|-----|---------|----------|
| Platform | Linux | OpenBSD | Linux |
| Type | Container | Full VM | Full VM |
| Management | lxc CLI | vmctl | virsh / qemu-system |
| Command execution | `lxc exec` | SSH | SSH |
| Console | PTY | Serial only | VNC + Serial |
| OS installation | Pre-built images | ISO + serial | ISO + cloud-init |
| Networking | lxdbr0 bridge | vmd local/bridge | virbr0 / bridge |
| Initialization | `lxd init` | `rcctl enable vmd` | libvirtd service |

## Multi-Hypervisor Support on Linux

**Critical Design Consideration:** Unlike OpenBSD (VMM only) or Windows (WSL only), a single Linux host can have **multiple hypervisors installed and operational simultaneously**:

- **KVM/QEMU** - Full virtual machines via libvirt
- **LXD/LXC** - Linux containers
- **VirtualBox** - If installed (future support)
- **Podman/Docker** - Container runtimes (future support)

### UI/UX Requirements

When a Linux host has multiple hypervisors available, the Create Child Host dialog must:

1. **Show available hypervisor options** - Let user choose between KVM, LXD, etc.
2. **Display hypervisor-specific distributions** - KVM shows VM distributions, LXD shows container images
3. **Present hypervisor-specific configuration** - Memory/CPU for KVM, profiles for LXD
4. **Indicate hypervisor status** - Show which are enabled/running vs just available

### Backend Architecture Changes

The virtualization status response for Linux hosts should return **all** available hypervisors:

```python
# Example virtualization status for a Linux host
{
    "platform": "Linux",
    "hypervisors": {
        "kvm": {
            "available": True,      # /dev/kvm exists
            "enabled": True,        # libvirtd enabled
            "running": True,        # libvirtd active
            "initialized": True,    # ready to create VMs
        },
        "lxd": {
            "available": True,      # lxd installed
            "enabled": True,        # snap/service enabled
            "running": True,        # lxd daemon active
            "initialized": True,    # lxd init completed
        },
        "virtualbox": {
            "available": False,     # not installed
            "enabled": False,
            "running": False,
            "initialized": False,
        }
    },
    "default_hypervisor": "kvm",  # Recommended based on capabilities
}
```

### Frontend Changes Required

#### Child Hosts Subtab - Detection/Enable UI

The Child Hosts subtab on HostDetail must display **all** detected hypervisors and their status. This is different from single-hypervisor platforms where we just show one status.

**Proposed Layout for Linux Hosts:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Child Hosts                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Virtualization Capabilities                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                  │   │
│  │  ┌──────────────────────┐  ┌──────────────────────┐             │   │
│  │  │ KVM/QEMU             │  │ LXD                  │             │   │
│  │  │ ✓ Available          │  │ ✓ Available          │             │   │
│  │  │ ✓ Enabled            │  │ ✓ Enabled            │             │   │
│  │  │ ✓ Running            │  │ ✓ Initialized        │             │   │
│  │  │                      │  │                      │             │   │
│  │  │ [Create VM]          │  │ [Create Container]   │             │   │
│  │  └──────────────────────┘  └──────────────────────┘             │   │
│  │                                                                  │   │
│  │  ┌──────────────────────┐                                       │   │
│  │  │ VirtualBox           │                                       │   │
│  │  │ ✗ Not Installed      │                                       │   │
│  │  │                      │                                       │   │
│  │  │ (Install manually)   │                                       │   │
│  │  └──────────────────────┘                                       │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Child Hosts (3)                                          [+ Create]    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Name          │ Type    │ Distribution  │ Status   │ Actions   │   │
│  ├───────────────┼─────────┼───────────────┼──────────┼───────────┤   │
│  │ web-server    │ KVM     │ Ubuntu 24.04  │ Running  │ ...       │   │
│  │ db-container  │ LXD     │ Debian 12     │ Running  │ ...       │   │
│  │ test-vm       │ KVM     │ Alpine 3.20   │ Stopped  │ ...       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Hypervisor Card States:**

| State | Visual | Button |
|-------|--------|--------|
| Not Available (no hardware/kernel support) | Grayed out, ✗ icon | None or "Not Supported" |
| Available but Not Installed | Yellow/warning | "Install" (if automatable) |
| Installed but Not Enabled | Orange chip | "Enable" button |
| Enabled but Not Running | Orange chip | "Start" button |
| Running but Not Initialized | Blue chip | "Initialize" button |
| Fully Ready | Green chip, ✓ icons | "Create VM/Container" button |

**State Flow for Each Hypervisor:**

```
┌─────────────┐    ┌───────────┐    ┌─────────┐    ┌─────────┐    ┌───────────┐
│ Not         │───▶│ Available │───▶│ Enabled │───▶│ Running │───▶│ Ready to  │
│ Available   │    │ (Install) │    │ (Start) │    │ (Init)  │    │ Create    │
└─────────────┘    └───────────┘    └─────────┘    └─────────┘    └───────────┘
     ✗                  ⚠                ◐              ◑              ✓
```

**Enable/Initialize Actions by Hypervisor:**

| Hypervisor | "Enable" Action | "Initialize" Action |
|------------|-----------------|---------------------|
| KVM | Install libvirt packages, enable libvirtd | Start libvirtd, create default network |
| LXD | Install lxd snap/package, enable service | Run `lxd init --auto` or guided setup |
| VirtualBox | N/A (manual install required) | N/A |

**UI Component Changes:**

- [ ] **`frontend/src/Pages/HostDetail.tsx`**
  - [ ] Create `HypervisorCard` component for each hypervisor
  - [ ] Show card grid when platform is Linux
  - [ ] Each card shows: name, status indicators, action button
  - [ ] Handle different states (not available → ready)
  - [ ] When multiple hypervisors available, show hypervisor selector in dialog
  - [ ] Filter distributions based on selected hypervisor
  - [ ] Show hypervisor-specific configuration options
  - [ ] Display status chips for each available hypervisor

- [ ] **New Component: `HypervisorStatusCard.tsx`**
  ```typescript
  interface HypervisorStatus {
    type: 'kvm' | 'lxd' | 'virtualbox';
    available: boolean;      // Hardware/kernel support exists
    installed: boolean;      // Packages installed
    enabled: boolean;        // Service enabled
    running: boolean;        // Service/daemon running
    initialized: boolean;    // Ready to create VMs/containers
    canAutoInstall: boolean; // Can we install automatically?
  }

  interface HypervisorCardProps {
    status: HypervisorStatus;
    onInstall: () => void;
    onEnable: () => void;
    onInitialize: () => void;
    onCreate: () => void;
  }
  ```

- [ ] **Comparison: Single vs Multi-Hypervisor UI:**

  | Platform | UI Pattern |
  |----------|------------|
  | OpenBSD | Single status banner: "VMM: Enabled ✓" or "Enable VMM" button |
  | Windows | Single status banner: "WSL: Enabled ✓" or "Enable WSL" button |
  | Linux | Card grid showing all hypervisors with individual status/actions |

- [ ] **Create Child Host Dialog Flow:**
  ```
  1. User clicks "Create Child Host" on Linux host
  2. If multiple hypervisors available:
     - Show hypervisor selection (KVM, LXD, etc.)
     - Each option shows status (enabled/disabled)
  3. After hypervisor selection:
     - Show distributions for that hypervisor type
     - Show hypervisor-specific config options
  4. Proceed with creation using selected hypervisor
  ```

- [ ] **Alternative: "Create" Button Per Hypervisor Card**
  - Each hypervisor card has its own "Create" button
  - Clicking it opens dialog pre-filtered to that hypervisor's distributions
  - Simpler flow: no hypervisor selection step in dialog
  - Recommended approach for cleaner UX

### Database Considerations

The `host_child` table already has `child_type` which handles this:
- `child_type = "kvm"` for KVM VMs
- `child_type = "lxd"` for LXD containers
- `child_type = "vmm"` for OpenBSD VMM VMs
- `child_type = "wsl"` for Windows WSL

The `child_host_distribution` table uses `child_type` to filter distributions.

### Platform Comparison

| Platform | Available Hypervisors | Selection Required |
|----------|----------------------|-------------------|
| OpenBSD | VMM only | No (automatic) |
| Windows | WSL only* | No (automatic) |
| Linux | KVM, LXD, VirtualBox, etc. | **Yes** (user chooses) |

*Windows could theoretically support Hyper-V in the future

### Implementation Note

This multi-hypervisor design should be incorporated into **Phase 1** when implementing KVM detection, ensuring the backend returns a unified structure that can accommodate multiple hypervisors on the same host.

## Detection Strategy

KVM support detection hierarchy:
1. **Kernel support**: `/dev/kvm` exists and accessible
2. **CPU support**: `/proc/cpuinfo` contains `vmx` (Intel) or `svm` (AMD)
3. **Management layer** (in order of preference):
   - libvirt + virsh (most common, recommended)
   - Direct QEMU (fallback, requires more manual config)
4. **Nested virtualization**: Check if running inside a VM

---

## Phase 1: KVM Detection and Role Support

**Goal:** Detect KVM capability on Linux hosts and display "KVM Host" role in the UI.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_virtualization_checks.py`**
  - [ ] Add `check_kvm_support()` function:
    - [ ] Check platform is Linux (`platform.system() == "Linux"`)
    - [ ] Check `/dev/kvm` exists and is accessible
    - [ ] Check CPU flags in `/proc/cpuinfo` for `vmx` or `svm`
    - [ ] Check if running as root or in `kvm` group
    - [ ] Detect libvirt: `shutil.which("virsh")` and `systemctl is-active libvirtd`
    - [ ] Detect QEMU: `shutil.which("qemu-system-x86_64")`
    - [ ] Check nested virtualization if applicable
  - [ ] Return detailed capability dict:
    ```python
    {
        "available": True/False,      # /dev/kvm exists
        "enabled": True/False,        # libvirtd enabled
        "running": True/False,        # libvirtd running
        "initialized": True/False,    # ready to create VMs
        "cpu_supported": True/False,  # vmx/svm flags present
        "kernel_supported": True/False,  # kvm module loaded
        "management": "libvirt" | "qemu" | None,
        "nested": True/False,         # nested virt available
    }
    ```

- [ ] **`src/sysmanage_agent/collection/role_detection.py`**
  - [ ] Add `kvm_host` to `role_mappings` dict with `special_detection=True`
  - [ ] Implement `_detect_kvm_host_role()` method:
    - [ ] Check for /dev/kvm
    - [ ] Verify libvirtd is running (if using libvirt)
    - [ ] Get QEMU/KVM version info
    - [ ] Return role dict with service status

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Add KVM to `check_virtualization_support()` for Linux platform
  - [ ] Add platform check: `if platform.system() == "Linux"`
  - [ ] Integrate with existing virtualization check flow

### sysmanage (Backend) Changes

- [ ] **`backend/security/roles.py`**
  - [ ] Add `KVM_HOST` role constant
  - [ ] Ensure role is included in role display mappings

- [ ] **`backend/api/child_host_virtualization.py`**
  - [ ] Handle KVM in virtualization status responses
  - [ ] Add KVM-specific status fields

### sysmanage (Frontend) Changes

- [ ] **`frontend/src/Pages/HostDetail.tsx`**
  - [ ] Add KVM Host role chip/badge display
  - [ ] Handle KVM in virtualization capability display

### sysmanage-docs Changes

- [ ] **Documentation**
  - [ ] Add KVM/QEMU section to child-host-management.html
  - [ ] Document KVM detection and requirements

### i18n/l10n (All 14 locales)

- [ ] Add "KVM Host" role strings
- [ ] Add KVM detection status strings

### Testing Checklist
- [ ] KVM Host role appears on Linux hosts with /dev/kvm
- [ ] Role does not appear on non-Linux systems
- [ ] Role does not appear if /dev/kvm missing
- [ ] Role shows correct service status (libvirtd running/stopped)
- [ ] Works on Ubuntu, Debian, Fedora, Alpine

---

## Phase 2: KVM Setup/Initialization Support

**Goal:** Allow users to enable and initialize KVM/libvirt on Linux hosts.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_kvm.py`** (NEW FILE)
  - [ ] Create `KvmOperations` class with:
    - [ ] `__init__(self, agent, logger)` - standard initialization
    - [ ] `async def initialize_kvm(self) -> Dict` - enable and start libvirtd:
      ```
      1. Check /dev/kvm exists
      2. Install libvirt if missing (package manager detection)
      3. Enable libvirtd service
      4. Start libvirtd service
      5. Add current user to libvirt/kvm groups if needed
      6. Verify virsh connects successfully
      7. Check default network (virbr0) exists
      ```
    - [ ] `async def check_kvm_ready(self) -> Dict` - verify KVM is operational
    - [ ] Detect package manager (apt, dnf, apk, zypper) for installation

- [ ] **Package installation commands by distro:**
  ```python
  LIBVIRT_PACKAGES = {
      "debian": ["qemu-kvm", "libvirt-daemon-system", "libvirt-clients", "virtinst", "bridge-utils"],
      "ubuntu": ["qemu-kvm", "libvirt-daemon-system", "libvirt-clients", "virtinst", "bridge-utils"],
      "fedora": ["@virtualization"],
      "rhel": ["qemu-kvm", "libvirt", "virt-install"],
      "alpine": ["qemu", "qemu-system-x86_64", "libvirt", "libvirt-daemon"],
      "opensuse": ["patterns-server-kvm_server", "patterns-server-kvm_tools"],
  }
  ```

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Import and instantiate `KvmOperations`
  - [ ] Add handler for `initialize_kvm` message type
  - [ ] Route KVM initialization requests

### sysmanage (Backend) Changes

- [ ] **`backend/api/child_host_virtualization.py`**
  - [ ] Add `enable_kvm` endpoint (similar to `enable_wsl` / `enable_vmm`)
  - [ ] Add `get_kvm_status` endpoint

- [ ] **`backend/api/child_host_models.py`**
  - [ ] Add `EnableKvmRequest` model if needed
  - [ ] Add `KvmStatusResponse` model

- [ ] **`backend/websocket/messages.py`**
  - [ ] Add `KVM_INITIALIZED` message type
  - [ ] Add `KVM_INITIALIZATION_FAILED` message type
  - [ ] Add `INITIALIZE_KVM` command type

- [ ] **`backend/api/handlers/child_host/virtualization.py`**
  - [ ] Add `handle_kvm_initialize_result()` handler

### sysmanage (Frontend) Changes

- [ ] **Enable KVM button in Host Detail view**
  - [ ] Show when KVM available but not enabled
  - [ ] Handle installation progress (package installation can take time)
  - [ ] Show success/failure notifications

### i18n/l10n (All 14 locales - backend + frontend)

- [ ] "Enable KVM" button text
- [ ] "KVM initialization in progress" status
- [ ] "KVM enabled successfully" message
- [ ] Error messages for initialization failures

### Testing Checklist
- [ ] "Enable KVM" button appears on eligible Linux hosts
- [ ] Enabling KVM installs required packages
- [ ] libvirtd service starts successfully
- [ ] KVM Host role appears after successful initialization
- [ ] Works on Ubuntu 22.04/24.04, Debian 12, Fedora 40+

---

## Phase 3: KVM Networking Configuration

**Goal:** Configure networking for KVM virtual machines.

### Networking Modes

1. **NAT (default)** - virbr0 with libvirt's built-in DHCP/NAT
   - Simplest, works out of the box
   - VMs get IPs from 192.168.122.0/24 (default)
   - Outbound NAT through host

2. **Bridged** - Direct LAN access via Linux bridge
   - VMs get IPs from physical network DHCP
   - Requires bridge interface setup
   - VMs visible on physical network

3. **macvtap** - Direct physical NIC attachment
   - High performance
   - VMs can't communicate with host on same interface

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_kvm.py`**
  - [ ] `async def setup_kvm_networking(self, config: Dict) -> Dict`
    - [ ] Ensure default network exists: `virsh net-list --all`
    - [ ] Start default network if stopped: `virsh net-start default`
    - [ ] Set autostart: `virsh net-autostart default`
  - [ ] `async def create_bridge_network(self, name: str, bridge: str) -> Dict`
    - [ ] Create libvirt network definition for bridged mode
    - [ ] Apply via `virsh net-define` / `virsh net-start`
  - [ ] `def _get_default_network_xml(self) -> str`
    - [ ] Generate libvirt network XML for NAT mode
  - [ ] `def _get_bridge_network_xml(self, name: str, bridge: str) -> str`
    - [ ] Generate libvirt network XML for bridged mode

- [ ] **Network XML templates:**
  ```xml
  <!-- NAT network (default) -->
  <network>
    <name>default</name>
    <forward mode='nat'/>
    <bridge name='virbr0' stp='on' delay='0'/>
    <ip address='192.168.122.1' netmask='255.255.255.0'>
      <dhcp>
        <range start='192.168.122.2' end='192.168.122.254'/>
      </dhcp>
    </ip>
  </network>
  ```

### sysmanage (Backend) Changes

- [ ] **`backend/api/child_host_virtualization.py`**
  - [ ] Add `configure_kvm_networking` endpoint
  - [ ] Support network mode selection

### sysmanage (Frontend) Changes

- [ ] **Network configuration in KVM setup**
  - [ ] Network mode dropdown (NAT/Bridged)
  - [ ] Bridge interface selection for bridged mode

### Testing Checklist
- [ ] Default NAT network works out of box
- [ ] VMs can reach internet via NAT
- [ ] Bridged mode works with existing Linux bridge
- [ ] Networking persists across libvirtd restarts

---

## Phase 4: KVM Distribution Management

**Goal:** Manage VM distributions (ISO images, cloud images) in the database.

### sysmanage (Backend) Changes

- [ ] **Database Migration** (new Alembic migration)
  - [ ] Add KVM distributions to `child_host_distribution` table:
    ```
    child_type: "kvm"
    distribution_name: "Ubuntu"
    distribution_version: "24.04"
    display_name: "Ubuntu 24.04 LTS"
    iso_url: "https://releases.ubuntu.com/24.04/..."
    cloud_image_url: "https://cloud-images.ubuntu.com/..."  # Optional
    agent_install_commands: [apt commands for agent]
    enabled: true
    ```
  - [ ] Supported distributions:
    - [ ] Ubuntu 22.04 LTS, 24.04 LTS (Server)
    - [ ] Debian 11, 12
    - [ ] Fedora 39, 40
    - [ ] AlmaLinux 9 / Rocky Linux 9
    - [ ] Alpine Linux 3.19, 3.20
    - [ ] openSUSE Leap 15.6

- [ ] **`backend/persistence/models/child_host.py`**
  - [ ] Ensure model supports KVM child_type
  - [ ] Consider adding KVM-specific fields:
    - [ ] `vm_disk_format` - qcow2/raw
    - [ ] `vm_disk_path` - path to disk image
    - [ ] `vm_memory` - allocated memory
    - [ ] `vm_cpus` - number of vCPUs

- [ ] **`backend/api/child_host_crud.py`**
  - [ ] Ensure KVM distributions returned in list endpoints
  - [ ] Add filtering by child_type="kvm"

### sysmanage (Frontend) Changes

- [ ] **`frontend/src/Pages/HostDetail.tsx`**
  - [ ] Set childType to 'kvm' for Linux hosts with KVM
  - [ ] Update dialog title for KVM
  - [ ] Show appropriate distributions

### Cloud-Init vs Traditional ISO Install

- [ ] **Cloud image support (preferred for automation):**
  - [ ] Download cloud image (.qcow2 or .img)
  - [ ] Create cloud-init ISO with user-data/meta-data
  - [ ] Boot VM with cloud image + cloud-init ISO
  - [ ] Agent installation via cloud-init runcmd

- [ ] **Traditional ISO install (fallback):**
  - [ ] Download installation ISO
  - [ ] Create preseed/kickstart/autoinstall config
  - [ ] Boot VM with ISO
  - [ ] Automated installation via preseed/kickstart

### Testing Checklist
- [ ] KVM distributions appear in UI when KVM Host selected
- [ ] Distribution metadata correctly loaded from database
- [ ] Agent install commands valid for each distribution

---

## Phase 5: VM Creation and Agent Installation

**Goal:** Create VMs, install guest OS, and deploy sysmanage-agent.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_kvm_types.py`** (NEW FILE)
  - [ ] Add `KvmVmConfig` dataclass:
    ```python
    @dataclass
    class KvmVmConfig:
        distribution: str
        vm_name: str
        hostname: str
        username: str
        password: str
        server_url: str
        agent_install_commands: List[str]
        memory: str = "2G"  # More memory than VMM default
        disk_size: str = "20G"
        cpus: int = 2
        server_port: int = 8443
        use_https: bool = True
        iso_url: str = ""
        cloud_image_url: str = ""
        use_cloud_init: bool = True
        network: str = "default"  # libvirt network name
    ```

- [ ] **`src/sysmanage_agent/operations/child_host_kvm.py`**
  - [ ] `async def create_kvm_vm(self, config: KvmVmConfig) -> Dict`
    - [ ] Main creation workflow:
      ```
      1. Validate configuration
      2. Check for duplicate VM name (virsh list --all)
      3. Create disk image (qemu-img create)
      4. Download ISO or cloud image
      5. If cloud-init: Create cloud-init ISO
      6. Generate libvirt domain XML
      7. Define VM (virsh define)
      8. Start VM (virsh start)
      9. Wait for VM to get IP
      10. Wait for SSH to be available
      11. Install sysmanage-agent via SSH
      12. Configure agent
      13. Start agent service
      14. Report success
      ```

  - [ ] `def _create_disk_image(self, path: str, size: str, format: str = "qcow2") -> Dict`
    - [ ] `qemu-img create -f qcow2 {path} {size}`

  - [ ] `def _vm_exists(self, vm_name: str) -> bool`
    - [ ] Check `virsh dominfo {vm_name}`

  - [ ] `def _generate_domain_xml(self, config: KvmVmConfig, disk_path: str) -> str`
    - [ ] Generate libvirt domain XML with:
      - [ ] CPU, memory configuration
      - [ ] Disk attachment
      - [ ] Network interface (virtio)
      - [ ] Serial console
      - [ ] VNC display (optional)
      - [ ] Cloud-init ISO if applicable

  - [ ] `async def _create_cloud_init_iso(self, config: KvmVmConfig) -> str`
    - [ ] Generate meta-data (instance-id, local-hostname)
    - [ ] Generate user-data (users, ssh keys, packages, runcmd)
    - [ ] Create ISO: `genisoimage -output seed.iso -volid cidata -joliet -rock user-data meta-data`

  - [ ] `def _generate_user_data(self, config: KvmVmConfig) -> str`
    - [ ] Cloud-init user-data YAML with:
      - [ ] User creation with password
      - [ ] SSH password auth enabled
      - [ ] Package installation
      - [ ] Agent install commands in runcmd
      - [ ] Agent configuration

  - [ ] `async def _wait_for_vm_ip(self, vm_name: str, timeout: int) -> str`
    - [ ] Poll `virsh domifaddr {vm_name}` or
    - [ ] Check libvirt DHCP leases: `virsh net-dhcp-leases default`
    - [ ] Return IP when available

  - [ ] `async def _wait_for_ssh(self, ip: str, timeout: int) -> bool`
    - [ ] Attempt SSH connection until successful

  - [ ] `async def _run_ssh_command(self, ip, user, password, command) -> Dict`
    - [ ] Execute command over SSH (reuse from VMM implementation)

  - [ ] `async def _install_agent_via_ssh(self, ip, user, password, commands) -> Dict`
    - [ ] Run agent installation commands
    - [ ] Configure agent with server URL/port
    - [ ] Start agent service

  - [ ] `async def _send_progress(self, step: str, message: str)`
    - [ ] Send progress updates to server

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Import and use `KvmVmConfig`
  - [ ] Route KVM child host creation to `kvm_ops.create_kvm_vm()`
  - [ ] Add KVM to `list_child_hosts()` for Linux platform

- [ ] **`src/sysmanage_agent/operations/child_host_listing.py`**
  - [ ] Add `list_kvm_vms()` method to enumerate KVM VMs via `virsh list --all`

### Libvirt Domain XML Template

```xml
<domain type='kvm'>
  <name>{vm_name}</name>
  <memory unit='GiB'>{memory}</memory>
  <vcpu>{cpus}</vcpu>
  <os>
    <type arch='x86_64'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough'/>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='{disk_path}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <disk type='file' device='cdrom'>
      <source file='{cloudinit_iso}'/>
      <target dev='sda' bus='sata'/>
      <readonly/>
    </disk>
    <interface type='network'>
      <source network='{network}'/>
      <model type='virtio'/>
    </interface>
    <serial type='pty'>
      <target port='0'/>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <graphics type='vnc' port='-1' autoport='yes'/>
  </devices>
</domain>
```

### Cloud-Init User-Data Template

```yaml
#cloud-config
hostname: {hostname}
fqdn: {fqdn}
manage_etc_hosts: true

users:
  - name: {username}
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: false
    passwd: {password_hash}

ssh_pwauth: true
disable_root: false

package_update: true
package_upgrade: true

packages:
  - curl
  - gnupg

runcmd:
  # Agent installation commands from database
  {agent_install_commands}
  # Configure agent
  - |
    cat > /etc/sysmanage-agent.yaml << 'EOF'
    server:
      url: {server_url}
      port: {server_port}
      use_https: {use_https}
    EOF
  - systemctl enable sysmanage-agent
  - systemctl start sysmanage-agent
```

### sysmanage (Backend) Changes

- [ ] **`backend/api/handlers/child_host/virtualization.py`**
  - [ ] Add `handle_kvm_initialize_result()` handler
  - [ ] Handle KVM VM creation progress updates

- [ ] **`backend/websocket/messages.py`**
  - [ ] Add KVM-specific message types if needed

### sysmanage (Frontend) Changes

- [ ] **Child Host Creation Dialog**
  - [ ] KVM handled via existing child_type mechanism
  - [ ] Add KVM-specific configuration fields (memory, disk size, CPUs)
  - [ ] Show appropriate distributions for KVM

### Testing Checklist
- [ ] VM disk image created successfully (qcow2)
- [ ] Cloud-init ISO generated correctly
- [ ] VM boots with cloud image
- [ ] Cloud-init runs and configures system
- [ ] VM gets IP address via DHCP
- [ ] SSH connection established
- [ ] Agent installed and configured
- [ ] Agent connects to sysmanage server
- [ ] Child host appears in Pending Hosts

---

## Phase 6: VM Lifecycle Control

**Goal:** Implement start/stop/restart/delete operations for KVM VMs.

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_kvm.py`**
  - [ ] `async def start_vm(self, vm_name: str) -> Dict`
    - [ ] `virsh start {vm_name}`
    - [ ] Wait for VM to be running
    - [ ] Return success with VM info

  - [ ] `async def stop_vm(self, vm_name: str, force: bool = False) -> Dict`
    - [ ] `virsh shutdown {vm_name}` - graceful ACPI shutdown
    - [ ] `virsh destroy {vm_name}` - force stop if needed
    - [ ] Wait for VM to stop

  - [ ] `async def restart_vm(self, vm_name: str) -> Dict`
    - [ ] `virsh reboot {vm_name}` or stop then start
    - [ ] Wait for VM to be running again

  - [ ] `async def delete_vm(self, vm_name: str, delete_disk: bool = True) -> Dict`
    - [ ] Stop VM if running: `virsh destroy {vm_name}`
    - [ ] Get disk paths: `virsh domblklist {vm_name}`
    - [ ] Undefine VM: `virsh undefine {vm_name}`
    - [ ] Delete disk images if requested
    - [ ] Clean up cloud-init ISO

  - [ ] `async def get_vm_status(self, vm_name: str) -> Dict`
    - [ ] Parse `virsh dominfo {vm_name}`
    - [ ] Get state, memory, CPUs, autostart
    - [ ] Get IP address if running

  - [ ] `async def get_vm_console(self, vm_name: str) -> Dict`
    - [ ] Return VNC connection info or serial console path

- [ ] **`src/sysmanage_agent/operations/child_host_listing.py`**
  - [ ] `async def list_kvm_vms(self) -> List[Dict]`
    - [ ] Parse `virsh list --all` to enumerate VMs
    - [ ] For each VM, get detailed info
    - [ ] Return list with name, status, memory, IPs, etc.

- [ ] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [ ] Route control operations to KvmOperations:
    - [ ] `start_child_host` for kvm type
    - [ ] `stop_child_host` for kvm type
    - [ ] `restart_child_host` for kvm type
    - [ ] `delete_child_host` for kvm type

### sysmanage (Backend) Changes

- [ ] **`backend/api/child_host_control.py`**
  - [ ] Ensure KVM child hosts handled by control endpoints

- [ ] **`backend/websocket/messages.py`**
  - [ ] Add KVM control message types if needed

### VM Autostart Configuration

- [ ] `async def set_autostart(self, vm_name: str, enabled: bool) -> Dict`
  - [ ] `virsh autostart {vm_name}` or `virsh autostart --disable {vm_name}`

### Testing Checklist
- [ ] Start stopped VM
- [ ] Stop running VM (graceful shutdown)
- [ ] Force stop hung VM
- [ ] Restart VM
- [ ] Delete VM and optionally disk
- [ ] VM status correctly reported
- [ ] Operations work from UI
- [ ] Autostart configuration works

---

## Phase 7: Advanced Features (Optional)

**Goal:** Additional features for enhanced KVM management.

### Snapshots

- [ ] `async def create_snapshot(self, vm_name: str, snapshot_name: str) -> Dict`
  - [ ] `virsh snapshot-create-as {vm_name} {snapshot_name}`

- [ ] `async def list_snapshots(self, vm_name: str) -> List[Dict]`
  - [ ] `virsh snapshot-list {vm_name}`

- [ ] `async def restore_snapshot(self, vm_name: str, snapshot_name: str) -> Dict`
  - [ ] `virsh snapshot-revert {vm_name} {snapshot_name}`

- [ ] `async def delete_snapshot(self, vm_name: str, snapshot_name: str) -> Dict`
  - [ ] `virsh snapshot-delete {vm_name} {snapshot_name}`

### Live Migration (Future)

- [ ] Support for migrating VMs between KVM hosts
- [ ] Requires shared storage or disk copy

### Resource Adjustment

- [ ] `async def set_memory(self, vm_name: str, memory: str) -> Dict`
  - [ ] Hot-add memory if supported, otherwise requires restart

- [ ] `async def set_cpus(self, vm_name: str, cpus: int) -> Dict`
  - [ ] Hot-add CPUs if supported

### Disk Management

- [ ] `async def add_disk(self, vm_name: str, size: str) -> Dict`
  - [ ] Create and attach additional disk

- [ ] `async def resize_disk(self, vm_name: str, disk: str, new_size: str) -> Dict`
  - [ ] Resize disk image (requires guest cooperation)

---

## Phase 8: Documentation and i18n/l10n

**Goal:** Complete documentation and translations for all KVM features.

### sysmanage-docs Changes

- [ ] **`child-host-management.html`**
  - [ ] Add KVM/QEMU section (similar to LXD, WSL, VMM sections)
  - [ ] Overview and requirements
  - [ ] Detection and role explanation
  - [ ] Setup instructions (libvirt installation)
  - [ ] VM creation process (cloud-init focus)
  - [ ] Networking configuration
  - [ ] Supported distributions
  - [ ] Comparison table: KVM vs LXD vs VMM vs WSL
  - [ ] Troubleshooting section

- [ ] **i18n/l10n - All 14 locale JSON files**

### Translation Keys to Add

```
docs.admin.child_host.kvm.title
docs.admin.child_host.kvm.overview_title
docs.admin.child_host.kvm.overview_desc
docs.admin.child_host.kvm.requirements_title
docs.admin.child_host.kvm.req_linux
docs.admin.child_host.kvm.req_cpu (vmx/svm)
docs.admin.child_host.kvm.req_libvirt
docs.admin.child_host.kvm.req_disk
docs.admin.child_host.kvm.detection_title
docs.admin.child_host.kvm.detection_desc
docs.admin.child_host.kvm.setup_title
docs.admin.child_host.kvm.setup_step1 (install packages)
docs.admin.child_host.kvm.setup_step2 (enable libvirtd)
docs.admin.child_host.kvm.setup_step3 (start libvirtd)
docs.admin.child_host.kvm.setup_step4 (verify)
docs.admin.child_host.kvm.creation_title
docs.admin.child_host.kvm.creation_desc
docs.admin.child_host.kvm.creation_step1-10
docs.admin.child_host.kvm.networking_title
docs.admin.child_host.kvm.networking_desc
docs.admin.child_host.kvm.net_nat
docs.admin.child_host.kvm.net_bridged
docs.admin.child_host.kvm.distributions_title
docs.admin.child_host.kvm.distributions_desc
docs.admin.child_host.kvm.comparison_title
docs.admin.child_host.kvm.troubleshooting
```

### sysmanage (Backend) i18n

- [ ] **`backend/i18n/locales/*/LC_MESSAGES/messages.po`**
  - [ ] Add KVM-related backend strings for all 14 locales

### sysmanage (Frontend) i18n

- [ ] **`frontend/public/locales/*/translation.json`**
  - [ ] Add KVM-related UI strings for all 14 locales

### Testing Checklist
- [ ] Documentation renders correctly
- [ ] All locale files valid JSON/PO
- [ ] No missing translation keys
- [ ] UI displays correctly in all languages

---

## Implementation Notes

### libvirt vs Direct QEMU

**Prefer libvirt because:**
- Consistent API across Linux distributions
- Built-in networking (virbr0, DHCP, NAT)
- VM persistence and autostart
- Easier management (virsh commands)
- Better documentation and community support

**Direct QEMU fallback for:**
- Systems without libvirt installed
- Minimal/embedded Linux systems
- Specific QEMU features not exposed by libvirt

### Cloud-Init vs ISO Install

**Prefer cloud-init because:**
- Faster (no interactive installation)
- Cloud images are smaller and pre-optimized
- Well-supported on all major distributions
- Easy to customize via user-data

**ISO install for:**
- Distributions without cloud images
- Custom installation requirements
- Situations where cloud-init fails

### Error Handling

- VM creation can fail at many points - provide clear rollback
- SSH connection failures should include troubleshooting hints
- Disk space checks before creating large disk images
- Timeout handling for long-running operations
- libvirt error message parsing

### Security Considerations

- SSH key vs password authentication for initial setup
- Secure password handling during agent configuration
- VM isolation verification
- libvirt ACLs and polkit policies
- SELinux/AppArmor considerations

### Performance Considerations

- Cloud image downloads can be large (500MB-2GB)
- Consider caching cloud images
- VM creation is slower than container creation
- Progress updates essential for user experience
- virtio drivers for best performance

---

## Dependencies

### Python Packages (sysmanage-agent)

- `libvirt-python` - libvirt bindings (optional, can use subprocess)
- Existing SSH library (reuse from VMM)
- `pyyaml` - for cloud-init generation (likely already present)

### System Requirements (Linux Host)

- Linux kernel with KVM support (kvm, kvm_intel or kvm_amd modules)
- CPU with VT-x (Intel) or AMD-V (AMD) support
- libvirt and QEMU packages
- Sufficient disk space for VM images
- Network connectivity for VM DHCP

### Package Requirements by Distribution

| Distribution | Packages |
|--------------|----------|
| Ubuntu/Debian | qemu-kvm, libvirt-daemon-system, libvirt-clients, virtinst, genisoimage |
| Fedora/RHEL | @virtualization group, or qemu-kvm, libvirt, virt-install |
| Alpine | qemu, qemu-system-x86_64, libvirt, libvirt-daemon |
| openSUSE | patterns-server-kvm_server, patterns-server-kvm_tools |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| libvirt installation failures | Medium | High | Detect package manager, clear error messages |
| Cloud-init not working on some images | Medium | Medium | Fallback to ISO install |
| Networking configuration conflicts | Medium | Medium | Validate network before changes |
| Large download times (ISOs/images) | High | Low | Progress updates, caching |
| Permission issues (libvirt/kvm groups) | Medium | Medium | Clear instructions, auto-add to groups |
| SELinux/AppArmor blocking VMs | Medium | High | Documentation, troubleshooting guide |

---

## Success Criteria

1. KVM Host role detected on Linux systems with /dev/kvm
2. Users can enable KVM/libvirt from the UI
3. VM creation works with supported distributions (cloud-init)
4. Agent auto-installs and connects to server
5. VM lifecycle operations (start/stop/restart/delete) work
6. Full documentation in all 14 languages
7. All existing tests pass
8. New tests cover KVM functionality
9. Works on Ubuntu, Debian, Fedora, Alpine, openSUSE

---

## Comparison: VMM vs KVM Implementation

| Aspect | VMM (OpenBSD) | KVM (Linux) |
|--------|---------------|-------------|
| Management tool | vmctl | virsh (libvirt) |
| Disk creation | vmctl create | qemu-img create |
| VM definition | vm.conf (optional) | libvirt XML |
| Default networking | -L flag (local DHCP) | virbr0 (NAT) |
| Console | Serial only | VNC + Serial |
| Preferred install | ISO + preseed | Cloud-init |
| Guest OS install | Slower (ISO) | Faster (cloud images) |
| Code reuse | SSH functions, progress reporting | Same |
