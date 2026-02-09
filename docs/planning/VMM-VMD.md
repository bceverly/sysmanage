# OpenBSD VMM/VMD Child Host Support Implementation Plan

This document outlines the phased implementation plan for adding OpenBSD VMM/VMD child host support to sysmanage, sysmanage-agent, and sysmanage-docs.

## Overview

VMM (Virtual Machine Monitor) is OpenBSD's native hypervisor, managed by the `vmd` daemon and controlled via the `vmctl` utility. Unlike LXD containers or WSL, VMM creates full virtual machines with their own kernels, requiring different approaches for:
- VM creation and disk management
- OS installation (serial console only - no VGA)
- Agent installation (SSH-based, not exec-based)
- Networking configuration (local/bridged/routed options)

## Key Differences from LXD/WSL

| Aspect | LXD | WSL | VMM/VMD |
|--------|-----|-----|---------|
| Type | Container | Compatibility Layer | Full VM |
| Command execution | `lxc exec` | Direct | SSH (post-boot) |
| Console | PTY | Windows terminal | Serial only |
| OS installation | Pre-built images | Microsoft Store | ISO + installer |
| Networking | lxdbr0 bridge | Windows NAT | vmd local/bridge |
| Initialization | `lxd init` | Windows Feature | `rcctl enable vmd` |

---

## Phase 1: VMM Detection and Role Support

**Goal:** Detect VMM capability on OpenBSD hosts and display "VMM Host" role in the UI.

### sysmanage-agent Changes

- [x] **`src/sysmanage_agent/operations/child_host_virtualization_checks.py`**
  - [x] Enhance `check_vmm_support()` to detect:
    - [x] Platform is OpenBSD (`platform.system() == "OpenBSD"`)
    - [x] `vmctl` command exists (`shutil.which("vmctl")`)
    - [x] `/dev/vmm` device exists (kernel support enabled)
    - [x] `vmd` daemon status (`rcctl check vmd`)
    - [ ] CPU virtualization support (VMX/SVM via sysctl)
  - [x] Return detailed capability dict:
    ```python
    {
        "available": True/False,  # vmctl exists
        "enabled": True/False,    # vmd enabled in rc.conf
        "running": True/False,    # vmd currently running
        "initialized": True/False, # ready to create VMs
        "cpu_supported": True/False,
        "kernel_supported": True/False,  # /dev/vmm exists
    }
    ```

- [x] **`src/sysmanage_agent/collection/role_detection.py`**
  - [x] Add `vmm_host` to `role_mappings` dict with `special_detection=True`
  - [x] Implement `_detect_vmm_host_role()` method:
    - [x] Check for vmctl binary
    - [x] Verify vmd is running
    - [ ] Get vmd version info
    - [x] Return role dict with service status

- [x] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [x] Add VMM to `check_virtualization_support()` for OpenBSD platform
  - [x] Add platform check: `if platform.system() == "OpenBSD"`

### sysmanage (Backend) Changes

- [ ] **`backend/security/roles.py`**
  - [ ] Add `VMM_HOST` role constant if not already present
  - [ ] Ensure role is included in role display mappings

### sysmanage-docs Changes

- [ ] **Documentation**
  - [ ] Add VMM/VMD section to child-host-management.html
  - [ ] Document VMM detection and requirements

### Testing Checklist
- [ ] VMM Host role appears on OpenBSD hosts with vmd running
- [ ] Role does not appear on non-OpenBSD systems
- [ ] Role shows correct service status (running/stopped)

---

## Phase 2: VMM Setup/Initialization Support

**Goal:** Allow users to enable and initialize VMM/vmd on OpenBSD hosts that have it available but not configured.

### sysmanage-agent Changes

- [x] **`src/sysmanage_agent/operations/child_host_vmm.py`** (NEW FILE)
  - [x] Create `VmmOperations` class with:
    - [x] `__init__(self, agent, logger)` - standard initialization
    - [x] `async def initialize_vmd(self) -> Dict` - enable and start vmd:
      ```
      1. rcctl enable vmd
      2. rcctl start vmd
      3. Verify /dev/vmm accessible
      4. Check fw_update for vmm-firmware if needed
      ```
    - [ ] `async def check_vmd_ready(self) -> Dict` - verify vmd is operational
  - [x] Handle case where reboot is required (kernel module loading)

- [x] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [x] Import and instantiate `VmmOperations`
  - [x] Add handler for `initialize_vmm` message type
  - [x] Route VMM initialization requests

### sysmanage (Backend) Changes

- [x] **`backend/api/child_host_virtualization.py`**
  - [x] Add `enable_vmm` endpoint (similar to `enable_wsl`)
  - [x] Handle reboot requirement notification
  - [x] Add `get_vmm_status` endpoint (included in virtualization status)

- [ ] **`backend/api/child_host_models.py`**
  - [ ] Add `EnableVmmRequest` model if needed
  - [ ] Add `VmmStatusResponse` model

- [ ] **`backend/websocket/messages.py`**
  - [ ] Add message types for VMM initialization

### sysmanage (Frontend) Changes

- [x] **Enable VMM button in Host Detail view**
  - [x] Show when VMM available but not enabled
  - [x] Handle reboot requirement UI notification

### sysmanage-docs Changes

- [x] **i18n/l10n**
  - [x] Add "Enable VMM" strings to all 14 locale files (backend + frontend + docs)
  - [ ] Add VMM setup documentation strings

### Testing Checklist
- [ ] "Enable VMM" button appears on eligible OpenBSD hosts
- [ ] Enabling VMM starts vmd daemon
- [ ] Reboot notification shown if kernel support requires reboot
- [ ] VMM Host role appears after successful initialization

---

## Phase 3: VMM Networking Configuration

**Goal:** Configure networking for VMM virtual machines (local interface with NAT).

### sysmanage-agent Changes

- [ ] **`src/sysmanage_agent/operations/child_host_vmm.py`**
  - [ ] `async def setup_vmm_networking(self, config: Dict) -> Dict`
    - [ ] Create vether interface for VM subnet
    - [ ] Configure bridge for vether
    - [ ] Add NAT rules to pf.conf
    - [ ] Enable IP forwarding if needed
  - [ ] `def _generate_pf_nat_rules(self, subnet: str) -> str`
    - [ ] Generate pf NAT rules for VM traffic
  - [ ] `def _get_default_vm_subnet(self) -> str`
    - [ ] Return default subnet (e.g., "10.50.0.0/24")

- [ ] **Network configuration options:**
  - [ ] **Local mode** (default): vmd's built-in DHCP (-L flag)
    - Simplest, auto-configures networking
    - VMs get IPs from vmd-managed range
  - [ ] **Bridged mode**: Direct LAN access via bridge interface
    - Requires existing bridge configuration
    - VMs visible on physical network
  - [ ] **Routed mode**: vether + pf NAT
    - Full control over VM network
    - Requires pf configuration

### sysmanage (Backend) Changes

- [ ] **`backend/api/child_host_virtualization.py`**
  - [ ] Add `configure_vmm_networking` endpoint
  - [ ] Support network mode selection

### OpenBSD pf.conf Integration

- [ ] **NAT rules template:**
  ```
  # VMM NAT rules - added by sysmanage-agent
  pass out on egress from <vmm_subnet> nat-to (egress)
  pass in on vether0 from <vmm_subnet>
  ```

### Testing Checklist
- [ ] Local networking works with -L flag (simplest case)
- [ ] VMs can reach internet via NAT
- [ ] pf rules added correctly without breaking existing config
- [ ] Networking persists across vmd restarts

---

## Phase 4: VM Distribution Management

**Goal:** Manage VM distributions (ISO images, install configurations) in the database and docs repository.

### sysmanage (Backend) Changes

- [x] **Database Migration** (new Alembic migration)
  - [x] Add VMM distributions to `child_host_distribution` table:
    ```
    child_type: "vmm"
    distribution_name: "OpenBSD"
    distribution_version: "7.6"
    display_name: "OpenBSD 7.6"
    install_identifier: "install76.iso"
    agent_install_commands: [pkg_add commands for agent]
    enabled: true
    ```
  - [x] Add Linux distributions with serial console support:
    - [x] Debian 12 (netinst)
    - [x] Ubuntu 24.04 Server
    - [x] Alpine Linux

- [x] **`backend/persistence/models/child_host.py`**
  - [x] Add VMM-specific fields to `HostChild` if needed:
    - Note: Existing model already supports VMM as child_type
    - [ ] `vm_disk_path` - path to qcow2/raw disk image (future enhancement)
    - [ ] `vm_memory` - allocated memory (e.g., "1G") (future enhancement)
    - [ ] `vm_cpus` - number of vCPUs (future enhancement)
    - [ ] `vm_boot_device` - current boot device (future enhancement)

- [x] **`backend/api/child_host_crud.py`**
  - [x] Ensure VMM distributions returned in list endpoints
  - [x] Add filtering by child_type="vmm"

### sysmanage (Frontend) Changes

- [x] **`frontend/src/Pages/HostDetail.tsx`**
  - [x] Set childType to 'vmm' for OpenBSD hosts
  - [x] Update dialog title for VMM
  - [x] Update FQDN helper text for VMM

### sysmanage-docs Changes

- [ ] **Repository structure for VMM**
  - [ ] Add VMM distribution metadata files
  - [ ] Document ISO image requirements
  - [ ] Add autoinstall/preseed configurations for supported distros

- [x] **Agent installation instructions per distro:**
  - [x] OpenBSD: `pkg_add` based installation (in migration)
  - [x] Debian/Ubuntu: APT repository setup (in migration)
  - [x] Alpine: apk-based installation (in migration)

### Testing Checklist
- [ ] VMM distributions appear in UI when VMM Host selected
- [ ] Distribution metadata correctly loaded from database
- [ ] Agent install commands valid for each distribution

---

## Phase 5: VM Creation and Agent Installation

**Goal:** Create VMs, install guest OS, and deploy sysmanage-agent via SSH.

### sysmanage-agent Changes

- [x] **`src/sysmanage_agent/operations/child_host_types.py`**
  - [x] Add `VmmVmConfig` dataclass:
    ```python
    @dataclass
    class VmmVmConfig:
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
    ```

- [x] **`src/sysmanage_agent/operations/child_host_vmm.py`**
  - [x] `async def create_vmm_vm(self, config: VmmVmConfig) -> Dict`
    - [x] Main creation workflow:
      ```
      1. Validate configuration
      2. Check for duplicate VM name
      3. Create disk image (vmctl create)
      4. Download/locate install ISO
      5. Launch VM with install media
      6. Wait for installation to complete (or handle autoinstall)
      7. Reboot VM without install media
      8. Wait for VM to boot and get IP
      9. Establish SSH connection
      10. Set hostname
      11. Create user account
      12. Install sysmanage-agent
      13. Configure agent
      14. Start agent service
      15. Report success
      ```

  - [x] `def _create_disk_image(self, path: str, size: str) -> Dict`
    - [x] `vmctl create -s {size} {path}`
    - [x] Support qcow2 format

  - [x] `def _vm_exists(self, vm_name: str) -> bool`
    - [x] Check `vmctl status` for existing VM

  - [x] `async def _launch_vm_with_iso(self, config, iso_path) -> Dict`
    - [x] `vmctl start -m {mem} -L -i 1 -r {iso} -d {disk} {name}`
    - [ ] Handle serial console redirection (future enhancement)

  - [x] `async def _wait_for_vm_ip(self, vm_name: str, timeout: int) -> str`
    - [x] Poll for VM IP address
    - [x] Check ARP table or vmd DHCP leases
    - [x] Return IP when available

  - [x] `async def _wait_for_ssh(self, ip: str, timeout: int) -> bool`
    - [x] Attempt SSH connection until successful
    - [x] Handle initial connection refusals

  - [x] `async def _run_ssh_command(self, ip, user, password, command) -> Dict`
    - [x] Execute command over SSH (using sshpass)
    - [x] Return stdout, stderr, exit code

  - [x] `async def _install_agent_via_ssh(self, ip, user, password, commands) -> Dict`
    - [x] Run agent installation commands
    - [x] Configure agent with server URL/port
    - [x] Start agent service

  - [x] `async def _send_progress(self, step: str, message: str)`
    - [x] Send progress updates to server (same pattern as LXD)

- [x] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [x] Import and use `VmmVmConfig`
  - [x] Route VMM child host creation to `vmm_ops.create_vmm_vm()`
  - [x] Add VMM to `list_child_hosts()` for OpenBSD platform

- [x] **`src/sysmanage_agent/operations/child_host_listing.py`**
  - [x] Add `list_vmm_vms()` method to enumerate VMM VMs via `vmctl status`

### Serial Console / Autoinstall Considerations

- [ ] **OpenBSD Autoinstall**
  - [ ] Support `autoinstall` response files
  - [ ] Boot with `bsd.rd` and detect autoinstall server
  - [ ] Or use serial console interaction via expect-like patterns

- [ ] **Linux Autoinstall**
  - [ ] Debian/Ubuntu: preseed files or cloud-init
  - [ ] Alpine: answer file support
  - [ ] Ensure serial console (`console=ttyS0`) in kernel params

- [ ] **Fallback: Manual Installation Support**
  - [ ] Allow creation without auto-install
  - [ ] User completes installation via serial console
  - [ ] Agent detects when VM is ready for agent installation

### sysmanage (Backend) Changes

- [x] **`backend/api/handlers/child_host/virtualization.py`**
  - [x] Add `handle_vmm_initialize_result()` handler
  - [x] Handle VMM initialization success/failure
  - [x] Queue virtualization check after successful initialization

- [x] **`backend/api/handlers/child_host/__init__.py`**
  - [x] Export `handle_vmm_initialize_result`

- [x] **`backend/api/handlers/child_host_handlers.py`**
  - [x] Re-export `handle_vmm_initialize_result`

- [x] **`backend/websocket/messages.py`**
  - [x] Add `VMM_INITIALIZED` message type
  - [x] Add `VMM_INITIALIZATION_FAILED` message type
  - [x] Add `INITIALIZE_VMM` command type

- [x] **`backend/i18n/locales/en/LC_MESSAGES/messages.po`**
  - [x] Add VMM initialization strings

### sysmanage (Frontend) Changes

- [x] **Child Host Creation Dialog**
  - [x] VMM handled via existing child_type mechanism
  - [ ] Add VMM-specific configuration fields (memory, disk size) - future enhancement
  - [x] Show appropriate distributions for VMM (already filtered by child_type)

### sysmanage-docs Changes

- [x] **i18n/l10n for all 14 locales**
  - [x] VM creation dialog title strings
  - [x] FQDN help text for VMM
  - [ ] Progress step messages - future enhancement
  - [ ] Error messages - future enhancement

### Testing Checklist
- [ ] VM disk image created successfully
- [ ] VM boots with install ISO
- [ ] OS installation completes (auto or manual)
- [ ] VM gets IP address via DHCP
- [ ] SSH connection established
- [ ] Agent installed and configured
- [ ] Agent connects to sysmanage server
- [ ] Child host appears in Pending Hosts

---

## Phase 6: VM Lifecycle Control

**Goal:** Implement start/stop/restart/delete operations for VMM VMs.

### sysmanage-agent Changes

- [x] **`src/sysmanage_agent/operations/child_host_vmm.py`**
  - [x] `async def start_vm(self, vm_name: str) -> Dict`
    - [x] `vmctl start {vm_name}` (if defined in vm.conf)
    - [ ] Or `vmctl start -d {disk} -m {mem} {vm_name}`
    - [ ] Wait for VM to be running

  - [x] `async def stop_vm(self, vm_name: str, force: bool = False) -> Dict`
    - [x] `vmctl stop {vm_name}` - graceful shutdown via ACPI
    - [x] `vmctl stop -f {vm_name}` - force stop if needed
    - [ ] Wait for VM to stop

  - [x] `async def restart_vm(self, vm_name: str) -> Dict`
    - [x] Stop then start
    - [ ] Or `vmctl pause` / `vmctl unpause` for quick restart

  - [x] `async def delete_vm(self, vm_name: str, delete_disk: bool = True) -> Dict`
    - [x] Stop VM if running
    - [ ] Remove from vm.conf if present
    - [ ] Delete disk image if requested
    - [ ] Clean up networking if dedicated

  - [ ] `async def get_vm_status(self, vm_name: str) -> Dict`
    - [ ] Parse `vmctl status` output
    - [ ] Return: running/stopped/paused, memory, uptime

- [ ] **`src/sysmanage_agent/operations/child_host_listing.py`**
  - [ ] `async def list_vmm_vms(self) -> List[Dict]`
    - [ ] Parse `vmctl status` to enumerate VMs
    - [ ] Return list with name, status, memory, etc.

- [x] **`src/sysmanage_agent/operations/child_host_operations.py`**
  - [x] Route control operations to VmmOperations:
    - [x] `start_child_host` for vmm type
    - [x] `stop_child_host` for vmm type
    - [x] `restart_child_host` for vmm type
    - [x] `delete_child_host` for vmm type

### sysmanage (Backend) Changes

- [ ] **`backend/api/child_host_control.py`**
  - [ ] Ensure VMM child hosts handled by control endpoints
  - [ ] No changes needed if generic enough

- [ ] **`backend/websocket/messages.py`**
  - [ ] Add VMM control message types if needed

### vm.conf Integration (Optional Enhancement)

- [ ] **Persistent VM definitions**
  - [ ] Add VMs to `/etc/vm.conf` for auto-start
  - [ ] Parse existing vm.conf entries
  - [ ] Support `enable` flag for boot-time start

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

**Goal:** Complete documentation and translations for all VMM/VMD features.

### sysmanage-docs Changes

- [ ] **`child-host-management.html`**
  - [ ] Add VMM/VMD section (similar to LXD and WSL sections)
  - [ ] Overview and requirements
  - [ ] Detection and role explanation
  - [ ] Setup instructions
  - [ ] VM creation process
  - [ ] Networking configuration
  - [ ] Supported distributions
  - [ ] LXD vs WSL vs VMM comparison table
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
docs.admin.child_host.vmm.title
docs.admin.child_host.vmm.overview_title
docs.admin.child_host.vmm.overview_desc
docs.admin.child_host.vmm.requirements_title
docs.admin.child_host.vmm.req_openbsd
docs.admin.child_host.vmm.req_cpu
docs.admin.child_host.vmm.req_vmd
docs.admin.child_host.vmm.req_disk
docs.admin.child_host.vmm.detection_title
docs.admin.child_host.vmm.detection_desc
docs.admin.child_host.vmm.setup_title
docs.admin.child_host.vmm.setup_desc
docs.admin.child_host.vmm.setup_step1 (rcctl enable vmd)
docs.admin.child_host.vmm.setup_step2 (rcctl start vmd)
docs.admin.child_host.vmm.setup_step3 (verify /dev/vmm)
docs.admin.child_host.vmm.creation_title
docs.admin.child_host.vmm.creation_desc
docs.admin.child_host.vmm.creation_step1-8
docs.admin.child_host.vmm.networking_title
docs.admin.child_host.vmm.networking_desc
docs.admin.child_host.vmm.net_local
docs.admin.child_host.vmm.net_bridged
docs.admin.child_host.vmm.net_routed
docs.admin.child_host.vmm.distributions_title
docs.admin.child_host.vmm.distributions_desc
docs.admin.child_host.vmm.comparison_title (VMM vs LXD vs WSL)
docs.admin.child_host.vmm.troubleshooting (issue9-12)
```

### sysmanage (Backend) i18n

- [ ] **`backend/i18n/locales/*/LC_MESSAGES/messages.po`**
  - [ ] Add VMM-related backend strings for all 14 locales

### sysmanage (Frontend) i18n

- [ ] **`frontend/public/locales/*/translation.json`**
  - [ ] Add VMM-related UI strings for all 14 locales

### Testing Checklist
- [ ] Documentation renders correctly
- [ ] All locale files valid JSON/PO
- [ ] No missing translation keys
- [ ] UI displays correctly in all languages

---

## Implementation Notes

### SSH Library Choice
For SSH operations, consider:
- `paramiko` - Pure Python SSH library (already used in many projects)
- `asyncssh` - Async SSH library (better fit for async codebase)
- `subprocess` with `ssh` command - Simplest but less control

### Error Handling
- VM creation can fail at many points - provide clear rollback
- SSH connection failures should include troubleshooting hints
- Disk space checks before creating large disk images
- Timeout handling for long-running operations

### Security Considerations
- SSH key vs password authentication for initial setup
- Secure password handling during agent configuration
- VM isolation verification
- pf rules review for NAT security

### Performance Considerations
- VM creation is slower than container creation
- OS installation can take 10-30 minutes
- Consider background job pattern for long operations
- Progress updates essential for user experience

---

## Dependencies

### Python Packages (sysmanage-agent)
- `asyncssh` or `paramiko` - SSH client library
- Existing dependencies should be sufficient otherwise

### System Requirements (OpenBSD Host)
- OpenBSD 7.x or later
- CPU with VMX (Intel) or SVM (AMD) support
- Sufficient disk space for VM images
- Network connectivity for VM DHCP

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Serial console complexity | High | Medium | Use autoinstall where possible |
| SSH setup failures | Medium | High | Robust retry logic, clear error messages |
| Networking configuration conflicts | Medium | Medium | Validate pf rules before applying |
| Long installation times | High | Low | Progress updates, async operations |
| Cross-platform testing | High | Medium | OpenBSD CI/CD environment needed |

---

## Success Criteria

1. VMM Host role detected on OpenBSD systems with vmd
2. Users can enable VMM from the UI
3. VM creation works with supported distributions
4. Agent auto-installs and connects to server
5. VM lifecycle operations (start/stop/restart/delete) work
6. Full documentation in all 14 languages
7. All existing tests pass
8. New tests cover VMM functionality
