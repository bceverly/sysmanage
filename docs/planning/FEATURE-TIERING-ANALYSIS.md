# Feature Tiering Analysis: Open Source vs Professional+

This document analyzes which features in the current open-source sysmanage/sysmanage-agent codebase would be more appropriate for the commercial sysmanage-professional-plus version, and how they should be organized into modules.

## Executive Summary

The analysis identifies **10 new modules** that should be moved to the commercial tier, containing features that are primarily valuable to enterprise-scale organizations rather than home users or small businesses.

---

## Current Pro+ Modules (Already Commercial)

| Module | Tier | Description |
|--------|------|-------------|
| proplus_core | Professional | License management UI |
| health_engine | Professional | Health analysis & recommendations |
| compliance_engine | Professional | CIS/DISA STIG auditing |
| vuln_engine | Enterprise | CVE vulnerability scanning |
| alerting_engine | Enterprise | Email/Webhook/Slack/Teams alerts |

---

## Proposed New Pro+ Modules

### PROFESSIONAL TIER (SMB and above)

---

### 1. reporting_engine

**Currently in open source:**
- `backend/api/reports/endpoints.py`
- `backend/api/reports/pdf/hosts.py`
- `backend/api/reports/pdf/users.py`
- `backend/api/reports/html/hosts.py`
- `backend/api/reports/html/users.py`

**Features to move:**
- PDF report generation (host inventory, user management)
- HTML report generation
- Custom report templates
- Scheduled report delivery
- Report branding/customization
- Export to multiple formats

**Rationale:** Home users don't need professional reports. SMBs and enterprises need polished reports for management presentations, compliance audits, and documentation. Report generation is a classic enterprise feature that justifies paid licensing.

**Estimated size:** ~1,500 lines of code

---

### 2. audit_engine

**Currently in open source:**
- `backend/api/audit_log.py`
- `backend/services/audit_service.py`
- `backend/persistence/models/audit.py` (AuditLog model)

**Features to move:**
- Comprehensive audit trail with entity change tracking
- IP address and user agent logging
- Audit log retention policies
- Compliance export formats (CSV, JSON, SIEM-compatible)
- Advanced audit log search and filtering
- Tamper-evident logging
- Audit log archival and rotation

**What to keep in open source:**
- Basic activity logging (login events, simple action tracking)

**Rationale:** Detailed audit trails are a compliance requirement for SOC2, HIPAA, PCI-DSS, ISO 27001, and other frameworks. Home users don't need this level of tracking. Enterprises pay significant amounts for compliance tooling.

**Estimated size:** ~2,000 lines of code

---

### 3. secrets_engine

**Currently in open source:**
- `backend/api/secrets/crud.py`
- `backend/api/secrets/deployment.py`
- `backend/api/secrets/models.py`
- `backend/api/openbao.py` (28KB)
- `backend/services/vault_service.py`

**Features to move:**
- OpenBAO/Vault integration
- Encrypted secret storage
- Secret deployment to hosts
- Credential rotation scheduling
- Secret access auditing
- Secret versioning
- Dynamic secret generation

**Rationale:** Enterprise secret management with vault integration is a security feature that enterprises will pay for. Home users store credentials in config files or simple password managers. Secret management at scale is a solved enterprise problem with commercial solutions.

**Estimated size:** ~2,500 lines of code

---

### ENTERPRISE TIER (Large organizations)

---

### 4. observability_engine

**Currently in open source:**

*Graylog Integration:*
- `backend/api/graylog_integration.py` (22KB)
- `backend/api/host_graylog.py`
- `backend/services/graylog_integration.py`
- `sysmanage_agent/operations/graylog_attachment.py` (261 lines)
- `sysmanage_agent/collection/graylog_collector.py`

*Grafana Integration:*
- `backend/api/grafana_integration.py` (21KB)
- `backend/api/host_monitoring.py` (14KB)
- `backend/services/grafana_integration.py`

*OpenTelemetry:*
- `backend/api/opentelemetry/deployment.py`
- `backend/api/opentelemetry/status.py`
- `backend/api/opentelemetry/service_control.py`
- `backend/api/opentelemetry/eligibility.py`
- `backend/api/opentelemetry/grafana_connection.py`
- `sysmanage_agent/operations/opentelemetry_operations.py` (167 lines)
- `sysmanage_agent/operations/otel_deployment_helper.py` (184 lines)
- `sysmanage_agent/operations/otel_deploy_linux.py` (210 lines)
- `sysmanage_agent/operations/otel_deploy_bsd.py` (107 lines)
- `sysmanage_agent/operations/otel_deploy_macos.py` (33 lines)
- `sysmanage_agent/operations/otel_deploy_windows.py` (33 lines)
- `sysmanage_agent/operations/otel_base.py`

**Features to move:**
- Graylog server configuration and health monitoring
- GELF TCP/UDP input configuration
- Syslog forwarding setup
- Windows Sidecar deployment
- Grafana server integration
- Dashboard and panel provisioning
- DataSource configuration
- OTEL Collector deployment and management
- Prometheus metrics export
- Distributed tracing setup
- Metrics collection configuration

**Rationale:** Centralized logging, metrics, and tracing infrastructure is enterprise observability. Home users don't run Graylog, Grafana, or distributed tracing stacks. These integrations require significant infrastructure investment that only enterprises make.

**Estimated size:** ~4,000 lines of code

---

### 5. container_engine (PROFESSIONAL TIER)

**Currently in open source:**

*LXD/LXC (Ubuntu):*
- `sysmanage_agent/operations/child_host_lxd.py`
- `sysmanage_agent/operations/child_host_lxd_container_creator.py`

*WSL (Windows):*
- `sysmanage_agent/operations/child_host_wsl.py`
- `sysmanage_agent/operations/child_host_wsl_setup.py`
- `sysmanage_agent/operations/child_host_wsl_control.py`
- `sysmanage_agent/operations/child_host_listing_wsl.py`

**Features to move:**
- LXD container creation and lifecycle (Ubuntu)
- LXD container networking
- WSL instance creation and lifecycle (Windows)
- WSL distribution management
- Container/instance status monitoring

**What to keep in open source:**
- Read-only container/instance listing

**Rationale:** LXD and WSL are commonly used by SMBs for containerization and development environments. These are simpler than full VM hypervisors and appropriate for Professional tier.

**Estimated size:** ~2,000 lines of code

---

### 6. virtualization_engine (ENTERPRISE TIER)

**Currently in open source:**

*Core Operations:*
- `sysmanage_agent/operations/child_host_operations.py`
- `sysmanage_agent/operations/child_host_listing.py`
- `sysmanage_agent/operations/child_host_virtualization_checks.py`
- `sysmanage_agent/operations/child_host_types.py`
- `sysmanage_agent/operations/child_host_config_generator.py`

*KVM/QEMU (Linux):*
- `sysmanage_agent/operations/child_host_kvm.py`
- `sysmanage_agent/operations/child_host_kvm_creation.py`
- `sysmanage_agent/operations/child_host_kvm_lifecycle.py`
- `sysmanage_agent/operations/child_host_kvm_networking.py`
- `sysmanage_agent/operations/child_host_kvm_cloudinit.py`
- `sysmanage_agent/operations/child_host_kvm_dns.py`
- `sysmanage_agent/operations/child_host_kvm_freebsd.py`
- `sysmanage_agent/operations/child_host_kvm_types.py`

*bhyve (FreeBSD):*
- `sysmanage_agent/operations/child_host_bhyve.py`
- `sysmanage_agent/operations/child_host_bhyve_creation.py`
- `sysmanage_agent/operations/child_host_bhyve_freebsd.py`
- `sysmanage_agent/operations/child_host_bhyve_lifecycle.py`
- `sysmanage_agent/operations/child_host_bhyve_networking.py`
- `sysmanage_agent/operations/child_host_bhyve_persistence.py`
- `sysmanage_agent/operations/child_host_bhyve_provisioning.py`
- `sysmanage_agent/operations/child_host_bhyve_images.py`
- `sysmanage_agent/operations/child_host_bhyve_metadata.py`
- `sysmanage_agent/operations/child_host_bhyve_types.py`

*VMM/vmd (OpenBSD):*
- `sysmanage_agent/operations/child_host_vmm.py`
- `sysmanage_agent/operations/child_host_vmm_vm_creator.py`
- `sysmanage_agent/operations/child_host_vmm_lifecycle.py`
- `sysmanage_agent/operations/child_host_vmm_launcher.py`
- `sysmanage_agent/operations/child_host_vmm_network_helpers.py`
- `sysmanage_agent/operations/child_host_vmm_ssh.py`
- `sysmanage_agent/operations/child_host_vmm_site_builder.py`
- `sysmanage_agent/operations/child_host_vmm_httpd_autoinstall.py`
- `sysmanage_agent/operations/child_host_vmm_package_builder.py`
- `sysmanage_agent/operations/child_host_vmm_packages.py`
- `sysmanage_agent/operations/child_host_vmm_password_utils.py`
- `sysmanage_agent/operations/child_host_vmm_disk.py`
- `sysmanage_agent/operations/child_host_vmm_vmconf.py`
- `sysmanage_agent/operations/child_host_vmm_github.py`
- `sysmanage_agent/operations/child_host_vmm_scripts.py`
- `sysmanage_agent/operations/child_host_vmm_bsd_embedder.py`
- `sysmanage_agent/operations/child_host_vmm_utils.py`

*Guest OS Provisioning:*
- `sysmanage_agent/operations/child_host_ubuntu_vm_creator.py`
- `sysmanage_agent/operations/child_host_ubuntu_autoinstall.py`
- `sysmanage_agent/operations/child_host_ubuntu_packages.py`
- `sysmanage_agent/operations/child_host_ubuntu_scripts.py`
- `sysmanage_agent/operations/child_host_debian_vm_creator.py`
- `sysmanage_agent/operations/child_host_debian_autoinstall.py`
- `sysmanage_agent/operations/child_host_debian_packages.py`
- `sysmanage_agent/operations/child_host_debian_scripts.py`
- `sysmanage_agent/operations/child_host_debian_console.py`
- `sysmanage_agent/operations/child_host_debian_agent_download.py`
- `sysmanage_agent/operations/child_host_alpine_vm_creator.py`
- `sysmanage_agent/operations/child_host_alpine_autoinstall.py`
- `sysmanage_agent/operations/child_host_alpine_packages.py`
- `sysmanage_agent/operations/child_host_alpine_scripts.py`
- `sysmanage_agent/operations/child_host_alpine_console.py`
- `sysmanage_agent/operations/child_host_alpine_site_builder.py`

*Platform Utilities:*
- `sysmanage_agent/operations/_virtualization_linux.py`
- `sysmanage_agent/operations/_virtualization_windows.py`
- `sysmanage_agent/operations/_virtualization_bsd.py`

*Server-side:*
- `backend/api/child_host.py`
- `backend/api/child_host_crud.py` (32KB)
- `backend/api/child_host_control.py`
- `backend/api/child_host_virtualization.py` (14KB)
- `backend/api/child_host_virtualization_enable.py` (22KB)
- `backend/api/child_host_virtualization_status.py`

**Features to move:**
- KVM/QEMU VM management (Linux)
- bhyve VM management (FreeBSD)
- VMM/vmd VM management (OpenBSD)
- Cloud-init integration for all hypervisors
- Network configuration (NAT, bridge, host-only)
- Guest OS autoinstall (Ubuntu, Debian, Alpine, FreeBSD)
- VM disk management
- VM resource configuration

**What to keep in open source:**
- Basic virtualization detection (what hypervisor is running)
- Read-only listing of existing VMs

**Rationale:** Full hypervisor management is datacenter/enterprise infrastructure. Managing KVM, bhyve, or VMM programmatically with cloud-init provisioning is Infrastructure-as-Code territory that enterprises invest heavily in.

**Estimated size:** ~13,000 lines of code

---

### 7. automation_engine

**Currently in open source:**
- `backend/api/scripts/routes_saved_scripts.py` (15KB)
- `backend/api/scripts/routes_executions.py` (19KB)
- `backend/api/scripts/models.py`
- `backend/persistence/models/scripts.py` (SavedScript, ScriptExecutionLog)
- `sysmanage_agent/operations/script_operations.py` (129 lines)

**Features to move:**
- Saved script library with versioning
- Script execution across multiple hosts
- Execution logging with stdout/stderr capture
- Multi-shell support (bash, zsh, PowerShell, cmd, ksh)
- Scheduled script execution
- Approval workflows for privileged scripts
- Script parameterization
- Execution history and audit trail
- Script sharing between users

**Rationale:** Fleet-wide script automation with auditing is enterprise IT operations. Home users run scripts manually via SSH or local terminal. Automation at scale requires governance, auditing, and scheduling that enterprises need.

**Estimated size:** ~2,000 lines of code

---

### 8. fleet_engine

**Currently in open source:**
- `backend/api/fleet.py` (11KB)
- Bulk operation endpoints scattered throughout API files

**Features to move:**
- Bulk host operations (update all, restart all, etc.)
- Advanced host grouping (beyond simple tags)
- Scheduled fleet-wide operations
- Rolling deployments (update hosts in configurable waves)
- Fleet-wide configuration deployment
- Host selection queries (all hosts matching criteria)
- Operation progress tracking across fleet
- Failure handling and retry logic
- Maintenance windows

**Rationale:** Managing hundreds or thousands of hosts requires fleet orchestration capabilities. Home users have 1-10 hosts and can manage them individually. Fleet management is a core enterprise requirement.

**Estimated size:** ~1,500 lines of code

---

### 9. av_management_engine

**Currently in open source:**
- `sysmanage_agent/operations/antivirus_operations.py`
- `sysmanage_agent/operations/antivirus_base.py`
- `sysmanage_agent/operations/antivirus_deploy_linux.py`
- `sysmanage_agent/operations/antivirus_deploy_windows.py`
- `sysmanage_agent/operations/antivirus_deploy_bsd.py`
- `sysmanage_agent/operations/antivirus_remove_linux.py`
- `sysmanage_agent/operations/antivirus_remove_windows.py`
- `sysmanage_agent/operations/antivirus_remove_bsd.py`
- `sysmanage_agent/operations/antivirus_deployment_helpers.py`
- `sysmanage_agent/operations/antivirus_removal_helpers.py`
- `sysmanage_agent/operations/antivirus_service_manager.py`
- `sysmanage_agent/operations/antivirus_utils.py`
- `sysmanage_agent/collection/antivirus_collection.py`
- `sysmanage_agent/collection/commercial_antivirus_collection.py`
- `backend/api/antivirus_defaults.py` (10KB)
- `backend/api/antivirus_status.py` (20KB)
- `backend/api/commercial_antivirus_status.py`

**Features to move:**
- ClamAV/ClamWin deployment and configuration
- Antivirus service control (start, stop, restart)
- Scan scheduling and management
- Commercial antivirus detection (CrowdStrike, SentinelOne, Sophos, etc.)
- Definition update management
- Quarantine management
- AV policy deployment
- Compliance reporting for AV status

**What to keep in open source:**
- Basic AV status detection (is AV installed and running)
- Simple AV presence reporting

**Rationale:** Centralized antivirus management is enterprise endpoint security. Home users install AV manually and manage it through the AV vendor's interface. Enterprises need centralized visibility and control.

**Estimated size:** ~3,000 lines of code

---

### 10. firewall_orchestration_engine

**Currently in open source:**

*Server-side:*
- `backend/api/firewall_roles.py` (30KB)
- `backend/api/firewall_roles_helpers.py`
- `backend/api/firewall_status.py`
- `backend/persistence/models/firewall.py` (FirewallRole, FirewallRoleOpenPort, HostFirewallRole)

*Agent-side:*
- `sysmanage_agent/operations/firewall_operations.py`
- `sysmanage_agent/operations/firewall_linux.py`
- `sysmanage_agent/operations/firewall_linux_ufw.py`
- `sysmanage_agent/operations/firewall_linux_firewalld.py`
- `sysmanage_agent/operations/firewall_linux_parsers.py`
- `sysmanage_agent/operations/firewall_windows.py`
- `sysmanage_agent/operations/firewall_macos.py`
- `sysmanage_agent/operations/firewall_bsd.py`
- `sysmanage_agent/operations/firewall_bsd_pf.py`
- `sysmanage_agent/operations/firewall_bsd_ipfw.py`
- `sysmanage_agent/operations/firewall_bsd_npf.py`
- `sysmanage_agent/operations/firewall_bsd_parsers.py`
- `sysmanage_agent/operations/firewall_port_helpers.py`
- `sysmanage_agent/operations/firewall_collector.py`

**Features to move:**
- Firewall role definitions with port rules
- Role assignment to hosts
- Policy deployment across fleets
- Multi-platform firewall management:
  - Linux: UFW, firewalld, iptables
  - Windows: Windows Defender Firewall
  - macOS: Application Firewall
  - BSD: pf, ipfw, npf
- Firewall compliance checking
- Rule conflict detection
- Firewall change auditing

**What to keep in open source:**
- Basic firewall status reporting (is firewall on, what ports are open)
- Read-only firewall rule viewing

**Rationale:** Centralized firewall policy management is enterprise network security. Home users configure firewalls individually through OS interfaces. Enterprises need policy-based management across hundreds of hosts.

**Estimated size:** ~4,000 lines of code

---

## Summary Table

| Module | Tier | Primary Value Proposition | Est. Lines |
|--------|------|---------------------------|------------|
| **reporting_engine** | Professional | Professional reports for management/audits | ~1,500 |
| **audit_engine** | Professional | Compliance audit trails (SOC2, HIPAA, etc.) | ~2,000 |
| **secrets_engine** | Professional | Enterprise secret/credential management | ~2,500 |
| **container_engine** | Professional | LXD and WSL container/instance management | ~2,000 |
| **observability_engine** | Enterprise | Graylog + Grafana + OTEL integration | ~4,000 |
| **virtualization_engine** | Enterprise | KVM, bhyve, VMM hypervisor management | ~13,000 |
| **automation_engine** | Enterprise | Fleet-wide script automation | ~2,000 |
| **fleet_engine** | Enterprise | Bulk operations and fleet orchestration | ~1,500 |
| **av_management_engine** | Enterprise | Centralized antivirus management | ~3,000 |
| **firewall_orchestration_engine** | Enterprise | Centralized firewall policy management | ~4,000 |

**Total estimated code to move:** ~35,500 lines

---

## What Should Stay Open Source

These features are appropriate for all users including home/hobbyist:

### Host Monitoring (Keep)
- CPU, RAM, disk, network status
- System uptime and load
- OS information

### Software Management (Keep)
- Software inventory (what's installed)
- Update detection (what updates are available)
- Basic package management (install/uninstall individual packages)
- Package manager support

### Security Basics (Keep)
- Certificate monitoring (SSL cert expiration dates)
- Basic firewall status (is it on, what ports are open - read only)
- Basic AV status (is AV installed and running - read only)
- User account listing (who has access)

### Organization (Keep)
- Basic tagging for host organization
- Host approval workflow (basic security gate)

### Access Control (Keep)
- Role-based access control (basic user permissions)
- User authentication and session management

### Ubuntu Pro (Keep)
- Ubuntu Pro status reporting
- Basic Pro service visibility

### Virtualization/Container Basics (Keep)
- Read-only VM listing (view existing VMs and their status)
- Read-only container listing (view existing containers/instances)
- Basic hypervisor detection (what hypervisor is running)

Note: Advanced RBAC features (custom roles, fine-grained permissions) could be Professional tier.

---

## Revenue Tier Strategy

### Free/Open Source
- **Target:** Individual users, hobbyists, home labs, evaluation
- **Value:** Basic host monitoring, software inventory, manual operations
- **Hosts:** Unlimited (self-hosted)

### Professional ($X/host/month)
- **Target:** Small-to-medium businesses (10-100 hosts)
- **Value:** Reports, audit trails, secrets management, container management, compliance basics, health analysis
- **Modules:** reporting_engine, audit_engine, secrets_engine, container_engine, health_engine, compliance_engine

### Enterprise ($Y/host/month)
- **Target:** Large organizations (100+ hosts)
- **Value:** Full observability stack, virtualization, fleet automation, centralized security
- **Modules:** All Professional modules plus observability_engine, virtualization_engine, automation_engine, fleet_engine, av_management_engine, firewall_orchestration_engine, vuln_engine, alerting_engine

---

## Implementation Considerations

### Agent-Side Code
Many features have agent-side components that would need to be conditionally enabled based on license. Options:
1. **Compile-time:** Ship different agent builds (open source vs commercial)
2. **Runtime:** Agent checks license and enables/disables features
3. **Hybrid:** Core agent is open source, commercial features as loadable modules

### Database Models
Models for commercial features should be in the main codebase but tables only created when licensed. The current proplus.py pattern works well.

### API Routes
Commercial routes should only be mounted when the module is licensed. The current `proplus_routes.py` pattern handles this.

### Frontend
Plugin architecture already supports dynamic loading of commercial UI components.

---

## Migration Path

1. **Phase 1:** Move reporting_engine, audit_engine, secrets_engine, container_engine to Pro+ (Professional tier, lower risk)
2. **Phase 2:** Move av_management_engine, firewall_orchestration_engine (Enterprise tier security)
3. **Phase 3:** Move automation_engine, fleet_engine (Enterprise tier operations)
4. **Phase 4:** Move observability_engine, virtualization_engine (Enterprise tier, largest/most complex)

Each phase should include:
- Code migration to sysmanage-professional-plus
- License gating implementation
- Documentation updates
- Customer communication

---

*Document generated: February 2026*
*Analysis based on sysmanage codebase exploration*
