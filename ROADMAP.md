# SysManage Comprehensive Roadmap

This document provides a detailed roadmap for realizing all features in both open-source sysmanage/sysmanage-agent and the commercial sysmanage-professional-plus (Pro+) tiers. It includes feature development phases, intermediate stabilization periods, and release milestones.

---

## Table of Contents

1. [Current State Assessment](#current-state-assessment)
2. [Release Philosophy](#release-philosophy)
3. [Roadmap Overview](#roadmap-overview)
4. [Phase 0: Current State (Already Implemented)](#phase-0-current-state-already-implemented)
5. [Phase 1: Stabilization Alpha](#phase-1-stabilization-alpha)
6. [Phase 2: Foundation Features](#phase-2-foundation-features)
7. [Phase 3: Stabilization Beta](#phase-3-stabilization-beta)
8. [Phase 4: Pro+ Module Migration - Part 1](#phase-4-pro-module-migration---part-1)
9. [Phase 5: Virtualization Completion](#phase-5-virtualization-completion)
10. [Phase 6: Stabilization RC1](#phase-6-stabilization-rc1)
11. [Phase 7: Pro+ Module Migration - Part 2](#phase-7-pro-module-migration---part-2)
12. [Phase 8: Platform Enhancements](#phase-8-platform-enhancements)
13. [Phase 9: Stabilization RC2](#phase-9-stabilization-rc2)
14. [Phase 10: Enterprise Features](#phase-10-enterprise-features)
15. [Phase 11: Polish and GA](#phase-11-polish-and-ga)
16. [Release Schedule Summary](#release-schedule-summary)
17. [Module Migration Plan](#module-migration-plan)

---

## Current State Assessment

### Already Implemented - Open Source (sysmanage/sysmanage-agent)

#### Core Infrastructure
- [x] Host registration and approval workflow
- [x] WebSocket-based agent communication
- [x] Real-time host status monitoring
- [x] Role-based access control (RBAC)
- [x] User authentication and session management
- [x] Host tagging system (full CRUD)
- [x] Multi-platform support (Linux, macOS, Windows, FreeBSD, OpenBSD, NetBSD)

#### Software Management
- [x] Software inventory collection (all supported package managers)
- [x] Update detection and availability tracking
- [x] Package installation/removal (basic)
- [x] Repository management (Linux)

#### Hardware & System Information
- [x] CPU, RAM, disk, network status collection
- [x] System uptime and load monitoring
- [x] Operating system information
- [x] Storage device inventory

#### Security Basics
- [x] Certificate monitoring (SSL cert expiration)
- [x] Basic firewall status detection
- [x] Basic antivirus status detection
- [x] User account listing
- [x] Ubuntu Pro integration

#### Child Host Management (Partial)
- [x] LXD container support (Ubuntu)
- [x] WSL instance support (Windows)
- [x] VMM/vmd support (OpenBSD) - ~70% complete
- [ ] KVM/QEMU support (Linux) - not started
- [ ] bhyve support (FreeBSD) - not started

### Already Implemented - Pro+ (sysmanage-professional-plus)

| Module | Tier | Status | Description |
|--------|------|--------|-------------|
| proplus_core | Professional | ✅ Complete | License management UI |
| health_engine | Professional | ✅ Complete | AI-powered health analysis & recommendations |
| compliance_engine | Professional | ✅ Complete | CIS/DISA STIG auditing |
| vuln_engine | Enterprise | ✅ Complete | CVE vulnerability scanning |
| alerting_engine | Enterprise | ✅ Complete | Email/Webhook/Slack/Teams alerts |

### Licensing System
- [x] License key validation (ECDSA P-521 signatures)
- [x] License storage and management UI
- [x] Feature gating for API endpoints
- [x] Frontend feature checks
- [x] Host count enforcement
- [x] Grace period handling

---

## Release Philosophy

### Stabilization Phases

Between major feature development phases, we insert **stabilization phases** focused on:

1. **Unit Test Coverage** - Increase Python test coverage toward 80%+
2. **Playwright E2E Tests** - Ensure UI flows work correctly
3. **SonarQube Cleanup** - Resolve all code quality issues
4. **Dependabot Updates** - Apply security patches and dependency updates
5. **Security Analysis** - Review for vulnerabilities (OWASP top 10)
6. **Performance Testing** - Identify and resolve bottlenecks
7. **Documentation Updates** - Keep docs current with features

### Release Versioning

- **Alpha (0.x.0-alpha.N)** - Feature incomplete, internal testing only
- **Beta (0.x.0-beta.N)** - Feature complete, external testing welcome
- **RC (0.x.0-rc.N)** - Release candidate, production-ready pending final validation
- **GA (1.0.0+)** - General availability, production-ready

---

## Roadmap Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SYSMANAGE ROADMAP                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  Phase 0: Current State                                                         │
│     └── [DONE] Core platform, LXD, WSL, VMM (partial), Pro+ base modules        │
│                                                                                 │
│  Phase 1: Stabilization Alpha                                          v0.9.0  │
│     └── Unit tests, Playwright, SonarQube, Dependabot, Security audit          │
│                                                                                 │
│  Phase 2: Foundation Features (Open Source)                                     │
│     └── Access Groups, Scheduled Updates, Package Compliance, Audit, Broadcast │
│                                                                                 │
│  Phase 3: Stabilization Beta                                           v0.10.0 │
│     └── Test coverage push, full i18n audit, performance baseline              │
│                                                                                 │
│  Phase 4: Pro+ Migration Part 1 (Professional Tier)                            │
│     └── reporting_engine, audit_engine, secrets_engine                         │
│                                                                                 │
│  Phase 5: Virtualization Completion                                             │
│     └── KVM/QEMU (Linux), bhyve (FreeBSD), VMM completion (OpenBSD)            │
│                                                                                 │
│  Phase 6: Stabilization RC1                                            v0.11.0 │
│     └── Integration testing, load testing, security penetration test           │
│                                                                                 │
│  Phase 7: Pro+ Migration Part 2 (Enterprise Tier)                              │
│     └── observability_engine, automation_engine, fleet_engine                  │
│                                                                                 │
│  Phase 8: Platform Enhancements (Open Source)                                   │
│     └── Infrastructure Deployment, Firewall Recommendations, Child Profiles    │
│                                                                                 │
│  Phase 9: Stabilization RC2                                            v0.12.0 │
│     └── Final polish, documentation completion, i18n verification              │
│                                                                                 │
│  Phase 10: Enterprise Features (Pro+)                                          │
│     └── av_management_engine, firewall_orchestration_engine, MFA               │
│                                                                                 │
│  Phase 11: Polish and GA                                               v1.0.0  │
│     └── Multi-tenancy, API completeness, platform-native logging, GA release   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Current State (Already Implemented)

**Status:** ✅ Complete

This represents the current baseline. All items listed in [Current State Assessment](#current-state-assessment) are complete and operational.

---

## Phase 1: Stabilization Alpha

**Target Release:** v0.9.0-alpha.1
**Focus:** Code quality and test coverage

### Goals

1. **Unit Test Coverage**
   - [ ] sysmanage backend: Achieve 70% coverage (currently ~56%)
   - [ ] sysmanage-agent: Maintain 90%+ coverage
   - [ ] Pro+ modules: Achieve 80% coverage per module

2. **Playwright E2E Tests**
   - [ ] Host list and detail page flows
   - [ ] User management flows
   - [ ] Settings page flows
   - [ ] Child host creation flows (LXD, WSL)
   - [ ] Pro+ feature flows (health analysis, compliance)

3. **SonarQube Cleanup**
   - [x] sysmanage-agent: 0 issues ✅
   - [ ] sysmanage backend: Target 0 critical/major issues
   - [ ] sysmanage frontend: Target 0 critical issues

4. **Dependabot Updates**
   - [ ] Apply all security patches
   - [ ] Update to latest stable versions of key dependencies
   - [ ] Resolve any breaking changes

5. **Security Analysis**
   - [ ] OWASP dependency check
   - [ ] SQL injection audit
   - [ ] XSS vulnerability scan
   - [ ] Authentication flow review
   - [ ] Secret handling audit

### Deliverables

- [ ] All SonarQube critical/major issues resolved
- [ ] Test coverage reports published
- [ ] Security audit report documented
- [ ] Performance baseline established

### Exit Criteria

- SonarQube: 0 critical issues, <10 major issues
- Backend test coverage: ≥70%
- Agent test coverage: ≥90%
- All Dependabot security alerts resolved

---

## Phase 2: Foundation Features

**Focus:** Open-source feature completion (FEATURES-TODO.md items #2-6)

### Features

#### 2.1 Access Groups and Registration Keys

**Priority:** High
**Effort:** Medium

- [ ] AccessGroup model with hierarchy (parent/child)
- [ ] RegistrationKey model with access group association
- [ ] Registration key auto-approval workflow
- [ ] RBAC scoping by access group
- [ ] Frontend: Access group management in Settings
- [ ] i18n/l10n for all 14 languages

#### 2.2 Scheduled Update Profiles

**Priority:** High
**Effort:** Medium

- [ ] UpgradeProfile model with cron scheduling
- [ ] Security-only update option
- [ ] Profile-tag associations
- [ ] Staggered rollout windows
- [ ] APScheduler integration
- [ ] Frontend: Automation tab with profile management
- [ ] i18n/l10n for all 14 languages

#### 2.3 Package Compliance Profiles

**Priority:** Medium
**Effort:** Medium

- [ ] PackageProfile and PackageProfileConstraint models
- [ ] Required/blocked package definitions
- [ ] Version constraint support
- [ ] Agent-side compliance checking
- [ ] HostComplianceStatus storage
- [ ] Frontend: Compliance tab in HostDetail
- [ ] i18n/l10n for all 14 languages

#### 2.4 Activity Audit Log Enhancement

**Priority:** High
**Effort:** Low

- [ ] EXECUTE action type for script executions
- [ ] Script output storage in details JSON
- [ ] Enhanced filtering (date range, entity type, user, result)
- [ ] Export to CSV/PDF
- [ ] Audit all API endpoints
- [ ] i18n/l10n for all 14 languages

#### 2.5 Broadcast Messaging

**Priority:** Medium
**Effort:** Medium

- [ ] BROADCAST message type
- [ ] Efficient broadcast channel implementation
- [ ] Agent broadcast message handler
- [ ] Frontend: "Broadcast Refresh" button
- [ ] i18n/l10n for all 14 languages

### Deliverables

- [ ] All Foundation features implemented and tested
- [ ] API documentation updated
- [ ] User documentation updated

---

## Phase 3: Stabilization Beta

**Target Release:** v0.10.0-beta.1
**Focus:** Test coverage push, i18n audit, performance baseline

### Goals

1. **Test Coverage Push**
   - [ ] Backend coverage: Target 75%
   - [ ] Agent coverage: Maintain 90%+
   - [ ] Add integration tests for new Foundation features
   - [ ] Playwright tests for Foundation feature UI flows

2. **i18n Audit**
   - [ ] Verify all strings externalized
   - [ ] Translation completeness check for all 14 languages
   - [ ] RTL layout verification (Arabic)
   - [ ] Character encoding verification (CJK languages)

3. **Performance Baseline**
   - [ ] Establish response time benchmarks
   - [ ] WebSocket connection scalability test (100, 500, 1000 agents)
   - [ ] Database query optimization review
   - [ ] Frontend bundle size audit

4. **Documentation**
   - [ ] Update all feature documentation
   - [ ] API reference complete
   - [ ] Deployment guide updated

### Exit Criteria

- Backend test coverage: ≥75%
- All translations verified complete
- Performance baselines documented
- No critical bugs in Foundation features

---

## Phase 4: Pro+ Module Migration - Part 1

**Focus:** Migrate Professional-tier features from open source to Pro+

### Modules to Migrate

#### 4.1 reporting_engine (Professional)

**Source Files:**
- `backend/api/reports/endpoints.py`
- `backend/api/reports/pdf/hosts.py`
- `backend/api/reports/pdf/users.py`
- `backend/api/reports/html/hosts.py`
- `backend/api/reports/html/users.py`

**Features:**
- [ ] PDF report generation (host inventory, user management)
- [ ] HTML report generation
- [ ] Custom report templates
- [ ] Scheduled report delivery
- [ ] Report branding/customization
- [ ] Export to multiple formats

**Migration Steps:**
1. [ ] Create `module-source/reporting_engine/` structure
2. [ ] Create `reporting_engine.pyx` Cython module
3. [ ] Migrate code with license gating
4. [ ] Create frontend plugin bundle
5. [ ] Remove from open source (replace with license check)
6. [ ] Update documentation
7. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~1,500 lines

#### 4.2 audit_engine (Professional)

**Source Files:**
- `backend/api/audit_log.py`
- `backend/services/audit_service.py`
- `backend/persistence/models/audit.py`

**Features:**
- [ ] Comprehensive audit trail with entity change tracking
- [ ] IP address and user agent logging
- [ ] Audit log retention policies
- [ ] Compliance export formats (CSV, JSON, SIEM-compatible)
- [ ] Advanced audit log search and filtering
- [ ] Tamper-evident logging
- [ ] Audit log archival and rotation

**Keep in Open Source:**
- Basic activity logging (login events, simple action tracking)

**Migration Steps:**
1. [ ] Create `module-source/audit_engine/` structure
2. [ ] Create `audit_engine.pyx` Cython module
3. [ ] Split basic vs advanced audit functionality
4. [ ] Migrate advanced features with license gating
5. [ ] Create frontend plugin bundle
6. [ ] Update documentation
7. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~2,000 lines

#### 4.3 secrets_engine (Professional)

**Source Files:**
- `backend/api/secrets/crud.py`
- `backend/api/secrets/deployment.py`
- `backend/api/secrets/models.py`
- `backend/api/openbao.py`
- `backend/services/vault_service.py`

**Features:**
- [ ] OpenBAO/Vault integration
- [ ] Encrypted secret storage
- [ ] Secret deployment to hosts
- [ ] Credential rotation scheduling
- [ ] Secret access auditing
- [ ] Secret versioning
- [ ] Dynamic secret generation

**Migration Steps:**
1. [ ] Create `module-source/secrets_engine/` structure
2. [ ] Create `secrets_engine.pyx` Cython module
3. [ ] Migrate all secrets functionality
4. [ ] Create frontend plugin bundle
5. [ ] Remove from open source
6. [ ] Update documentation
7. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~2,500 lines

### Deliverables

- [ ] 3 new Pro+ modules (reporting, audit, secrets)
- [ ] Open source code updated with license checks
- [ ] Documentation for Professional tier features
- [ ] Migration guide for existing users

---

## Phase 5: Virtualization Completion

**Focus:** Complete all hypervisor support

### 5.1 VMM/vmd Completion (OpenBSD)

**Current Status:** ~70% complete

**Remaining Work:**
- [ ] Phase 3: Networking configuration (pf NAT rules)
- [ ] Phase 7: Documentation and i18n for all 14 languages
- [ ] Testing on OpenBSD 7.6+
- [ ] Autoinstall support for guest OS

**Reference:** See VMM-VMD.md for detailed implementation plan.

### 5.2 KVM/QEMU Implementation (Linux)

**Current Status:** Not started

**Implementation Phases:**

1. [ ] **Detection and Role Support**
   - [ ] `check_kvm_support()` in virtualization_checks.py
   - [ ] KVM_HOST role detection
   - [ ] Multi-hypervisor UI for Linux hosts

2. [ ] **Setup/Initialization**
   - [ ] `KvmOperations` class
   - [ ] libvirt package installation by distro
   - [ ] libvirtd service management

3. [ ] **Networking Configuration**
   - [ ] NAT mode (virbr0 default)
   - [ ] Bridged mode support
   - [ ] Network XML templates

4. [ ] **Distribution Management**
   - [ ] Database migration for KVM distributions
   - [ ] Ubuntu, Debian, Fedora, Alpine, RHEL support
   - [ ] Cloud image support

5. [ ] **VM Creation**
   - [ ] `KvmVmConfig` dataclass
   - [ ] qemu-img disk creation
   - [ ] Cloud-init ISO generation
   - [ ] libvirt domain XML generation
   - [ ] SSH-based agent installation

6. [ ] **Lifecycle Control**
   - [ ] start/stop/restart/delete via virsh
   - [ ] VM status reporting
   - [ ] Autostart configuration

7. [ ] **Documentation and i18n**
   - [ ] All 14 languages

**Reference:** See KVM-QEMU.md for detailed implementation plan.

### 5.3 bhyve Implementation (FreeBSD)

**Current Status:** Not started

**Implementation Phases:**

1. [ ] **Detection and Role Support**
   - [ ] `check_bhyve_support()` in virtualization_checks.py
   - [ ] BHYVE_HOST role detection
   - [ ] vmm.ko kernel module detection

2. [ ] **Setup/Initialization**
   - [ ] `BhyveOperations` class
   - [ ] vmm.ko loading and /boot/loader.conf persistence
   - [ ] UEFI firmware detection (bhyve-firmware package)

3. [ ] **Networking Configuration**
   - [ ] Bridge mode (tap + bridge interfaces)
   - [ ] NAT mode (pf rules)
   - [ ] Host-only mode

4. [ ] **Distribution Management**
   - [ ] Database migration for bhyve distributions
   - [ ] FreeBSD, Ubuntu, Debian, Alpine, Windows Server support
   - [ ] Cloud image support

5. [ ] **VM Creation**
   - [ ] `BhyveVmConfig` dataclass
   - [ ] ZFS zvol or file-based disk creation
   - [ ] Cloud-init support with UEFI
   - [ ] bhyve command generation
   - [ ] SSH-based agent installation

6. [ ] **Lifecycle Control**
   - [ ] start/stop/restart/delete via bhyvectl
   - [ ] VM device management (/dev/vmm/*)
   - [ ] Process management (daemon)

7. [ ] **Documentation and i18n**
   - [ ] All 14 languages

**Reference:** See BHYVE.md for detailed implementation plan.

### Deliverables

- [ ] Complete VMM/vmd support for OpenBSD
- [ ] Full KVM/QEMU support for Linux
- [ ] Full bhyve support for FreeBSD
- [ ] Multi-hypervisor UI for Linux hosts
- [ ] Documentation for all hypervisors

---

## Phase 6: Stabilization RC1

**Target Release:** v0.11.0-rc.1
**Focus:** Integration testing, load testing, security penetration test

### Goals

1. **Integration Testing**
   - [ ] End-to-end tests for all virtualization platforms
   - [ ] Cross-platform agent testing
   - [ ] Pro+ module integration tests
   - [ ] WebSocket reliability under load

2. **Load Testing**
   - [ ] 100 concurrent agents
   - [ ] 500 concurrent agents
   - [ ] 1000 concurrent agents
   - [ ] Database query performance under load
   - [ ] WebSocket message throughput

3. **Security Penetration Test**
   - [ ] External penetration test (if budget allows)
   - [ ] Internal security review
   - [ ] Authentication bypass attempts
   - [ ] Privilege escalation attempts
   - [ ] WebSocket security review

4. **Bug Fixes**
   - [ ] Resolve all critical bugs
   - [ ] Resolve all high-priority bugs
   - [ ] Triage and document remaining bugs

### Exit Criteria

- All integration tests passing
- Load test targets met
- Security review complete with no critical findings
- No critical bugs remaining

---

## Phase 7: Pro+ Module Migration - Part 2

**Focus:** Migrate Enterprise-tier features from open source to Pro+

### Modules to Migrate

#### 7.1 observability_engine (Enterprise)

**Source Files:**
- Graylog: `backend/api/graylog_integration.py`, `backend/services/graylog_integration.py`, agent operations
- Grafana: `backend/api/grafana_integration.py`, `backend/services/grafana_integration.py`
- OpenTelemetry: `backend/api/opentelemetry/*`, agent operations

**Features:**
- [ ] Graylog server configuration and health monitoring
- [ ] GELF TCP/UDP input configuration
- [ ] Syslog forwarding setup
- [ ] Windows Sidecar deployment
- [ ] Grafana server integration
- [ ] Dashboard and panel provisioning
- [ ] DataSource configuration
- [ ] OTEL Collector deployment and management
- [ ] Prometheus metrics export
- [ ] Distributed tracing setup

**Estimated Size:** ~4,000 lines

#### 7.2 automation_engine (Enterprise)

**Source Files:**
- `backend/api/scripts/routes_saved_scripts.py`
- `backend/api/scripts/routes_executions.py`
- `backend/api/scripts/models.py`
- `backend/persistence/models/scripts.py`
- `sysmanage_agent/operations/script_operations.py`

**Features:**
- [ ] Saved script library with versioning
- [ ] Script execution across multiple hosts
- [ ] Execution logging with stdout/stderr capture
- [ ] Multi-shell support
- [ ] Scheduled script execution
- [ ] Approval workflows for privileged scripts
- [ ] Script parameterization

**Estimated Size:** ~2,000 lines

#### 7.3 fleet_engine (Enterprise)

**Source Files:**
- `backend/api/fleet.py`
- Bulk operation endpoints

**Features:**
- [ ] Bulk host operations
- [ ] Advanced host grouping
- [ ] Scheduled fleet-wide operations
- [ ] Rolling deployments
- [ ] Fleet-wide configuration deployment
- [ ] Host selection queries
- [ ] Operation progress tracking

**Estimated Size:** ~1,500 lines

### Deliverables

- [ ] 3 new Pro+ modules (observability, automation, fleet)
- [ ] Open source code updated with stubs/license checks
- [ ] Documentation for Enterprise tier features

---

## Phase 8: Platform Enhancements

**Focus:** Open-source platform features (FEATURES-TODO.md items #21-24)

### Features

#### 8.1 Infrastructure Deployment

**Priority:** Medium
**Effort:** High

- [ ] DeploymentTemplate model
- [ ] Pre-built templates (Graylog, Grafana, PostgreSQL, MySQL)
- [ ] Deployment tracking and status
- [ ] Docker compose and package-based options
- [ ] i18n/l10n for all 14 languages

#### 8.2 Firewall Recommendations

**Priority:** Medium
**Effort:** Medium

- [ ] Server role detection integration
- [ ] FirewallRuleTemplate model
- [ ] Role-to-rule mapping
- [ ] Recommendation preview and apply
- [ ] i18n/l10n for all 14 languages

#### 8.3 Child Host Profiles

**Priority:** Medium
**Effort:** Medium

- [ ] ChildHostProfile model
- [ ] Default configurations per virtualization type
- [ ] Post-install script support
- [ ] Profile assignment via tags
- [ ] i18n/l10n for all 14 languages

#### 8.4 Enhanced Snap Management

**Priority:** Low
**Effort:** Low

- [ ] Snap install/remove from UI
- [ ] Snap update management
- [ ] Auto-update pause/resume
- [ ] Channel and confinement display
- [ ] i18n/l10n for all 14 languages

### Deliverables

- [ ] All Platform Enhancement features implemented
- [ ] Documentation updated

---

## Phase 9: Stabilization RC2

**Target Release:** v0.12.0-rc.1
**Focus:** Final polish, documentation completion, i18n verification

### Goals

1. **Documentation Completion**
   - [ ] All features documented
   - [ ] API reference 100% complete
   - [ ] Deployment guides for all platforms
   - [ ] Troubleshooting guides
   - [ ] Migration guides

2. **i18n Verification**
   - [ ] All 14 languages complete
   - [ ] Professional review of translations (if budget allows)
   - [ ] UI screenshot verification per language

3. **UI/UX Polish**
   - [ ] Consistent styling across all pages
   - [ ] Accessibility audit (WCAG 2.1 AA)
   - [ ] Mobile responsiveness verification
   - [ ] Loading state improvements

4. **Performance Optimization**
   - [ ] Database query optimization
   - [ ] Frontend bundle optimization
   - [ ] API response time optimization
   - [ ] WebSocket efficiency improvements

### Exit Criteria

- All documentation complete
- All translations verified
- Accessibility audit passed
- Performance targets met

---

## Phase 10: Enterprise Features

**Focus:** Final Pro+ Enterprise-tier modules

### Modules to Migrate

#### 10.1 av_management_engine (Enterprise)

**Source Files:**
- `sysmanage_agent/operations/antivirus_*.py` (12 files)
- `sysmanage_agent/collection/antivirus_collection.py`
- `sysmanage_agent/collection/commercial_antivirus_collection.py`
- `backend/api/antivirus_*.py`

**Features:**
- [ ] ClamAV/ClamWin deployment and configuration
- [ ] Antivirus service control
- [ ] Scan scheduling and management
- [ ] Commercial AV detection (CrowdStrike, SentinelOne, etc.)
- [ ] Definition update management
- [ ] AV policy deployment

**Keep in Open Source:**
- Basic AV status detection (is AV installed and running)

**Estimated Size:** ~3,000 lines

#### 10.2 firewall_orchestration_engine (Enterprise)

**Source Files:**
- `backend/api/firewall_roles*.py`
- `backend/persistence/models/firewall.py`
- `sysmanage_agent/operations/firewall_*.py` (13 files)

**Features:**
- [ ] Firewall role definitions with port rules
- [ ] Role assignment to hosts
- [ ] Policy deployment across fleets
- [ ] Multi-platform firewall management (UFW, firewalld, pf, ipfw, etc.)
- [ ] Firewall compliance checking
- [ ] Rule conflict detection

**Keep in Open Source:**
- Basic firewall status reporting (read-only)

**Estimated Size:** ~4,000 lines

#### 10.3 Multi-Factor Authentication

**Priority:** High
**Effort:** Medium

- [ ] TOTP authenticator app support
- [ ] Email code verification fallback
- [ ] Backup codes
- [ ] Per-user MFA enforcement
- [ ] Admin MFA requirement option
- [ ] pyotp integration
- [ ] i18n/l10n for all 14 languages

### Additional Enterprise Features

#### 10.4 Repository Mirroring (Professional+)

- [ ] APT/DNF repository mirroring
- [ ] Tiered mirrors for multi-region
- [ ] Repository snapshots
- [ ] Air-gapped deployment support

#### 10.5 External Identity Providers (Professional+)

- [ ] LDAP/Active Directory authentication
- [ ] OIDC provider support (Okta, Azure AD, Keycloak)
- [ ] External group to role mapping
- [ ] Local account fallback

### Deliverables

- [ ] av_management_engine module
- [ ] firewall_orchestration_engine module
- [ ] MFA implementation
- [ ] Repository mirroring
- [ ] External IdP support

---

## Phase 11: Polish and GA

**Target Release:** v1.0.0
**Focus:** Multi-tenancy, API completeness, GA release

### Features

#### 11.1 Multi-Tenancy (Enterprise)

- [ ] Account model with isolation
- [ ] Account switching for users with multiple accounts
- [ ] Per-account settings and limits
- [ ] Data isolation verification

#### 11.2 API Completeness

- [ ] Audit all features for missing endpoints
- [ ] API versioning (/api/v1/, /api/v2/)
- [ ] ApiKey model for automation
- [ ] Rate limiting middleware
- [ ] Complete OpenAPI documentation

#### 11.3 Additional Polish Items

- [ ] GPG Key Management
- [ ] Administrator Invitations
- [ ] Platform-Native Logging
- [ ] Livepatch Integration (Ubuntu)
- [ ] Custom Metrics and Graphs (Professional+)
- [ ] Process Management

### GA Release Checklist

- [ ] All planned features implemented
- [ ] All tests passing (unit, integration, E2E)
- [ ] SonarQube: 0 critical issues
- [ ] Security audit complete
- [ ] Performance benchmarks met
- [ ] Documentation 100% complete
- [ ] All 14 translations verified
- [ ] Customer beta feedback addressed
- [ ] Marketing materials ready
- [ ] Support processes in place

---

## Release Schedule Summary

| Phase | Version | Focus | Key Deliverables |
|-------|---------|-------|------------------|
| 0 | Current | Baseline | Core platform operational |
| 1 | v0.9.0-alpha | Stabilization | Test coverage, SonarQube cleanup |
| 2 | - | Foundation | Access groups, update profiles, compliance |
| 3 | v0.10.0-beta | Stabilization | Performance baseline, i18n audit |
| 4 | - | Pro+ Part 1 | reporting, audit, secrets engines |
| 5 | - | Virtualization | KVM, bhyve, VMM completion |
| 6 | v0.11.0-rc | Stabilization | Integration tests, load tests, security |
| 7 | - | Pro+ Part 2 | observability, automation, fleet engines |
| 8 | - | Platform | Infrastructure deployment, firewall recs |
| 9 | v0.12.0-rc | Stabilization | Final polish, docs complete |
| 10 | - | Enterprise | AV management, firewall orchestration, MFA |
| 11 | **v1.0.0** | GA | Multi-tenancy, API complete, launch |

---

## Module Migration Plan

### Migration Philosophy

When migrating code from open source to Pro+:

1. **Create Cython module** in sysmanage-professional-plus
2. **Implement license gating** in the module
3. **Create frontend plugin** for UI components
4. **Update open source** to remove advanced features
5. **Add license checks** to remaining stubs in open source
6. **Document the change** clearly for users
7. **Provide migration path** for existing deployments

### Code Organization After Migration

**Open Source (sysmanage/sysmanage-agent):**
- Core platform functionality
- Basic versions of features (read-only firewall status, basic audit logs)
- License validation infrastructure
- Plugin loading architecture

**Pro+ (sysmanage-professional-plus):**
- Advanced feature implementations
- Cython-compiled backend modules
- JavaScript frontend plugins
- Enterprise-only functionality

### Timeline by Module

| Module | Tier | Phase | Est. Lines | Priority |
|--------|------|-------|------------|----------|
| reporting_engine | Professional | 4 | ~1,500 | High |
| audit_engine | Professional | 4 | ~2,000 | High |
| secrets_engine | Professional | 4 | ~2,500 | High |
| observability_engine | Enterprise | 7 | ~4,000 | Medium |
| automation_engine | Enterprise | 7 | ~2,000 | Medium |
| fleet_engine | Enterprise | 7 | ~1,500 | Medium |
| av_management_engine | Enterprise | 10 | ~3,000 | Low |
| firewall_orchestration_engine | Enterprise | 10 | ~4,000 | Low |
| virtualization_engine | Enterprise | 5* | ~15,000 | High |

*Note: virtualization_engine is developed in Pro+ from the start as part of Phase 5, not migrated from open source.

### Total Migration Estimate

- **Professional Tier:** ~6,000 lines (Phase 4)
- **Enterprise Tier - Part 1:** ~7,500 lines (Phase 7)
- **Enterprise Tier - Part 2:** ~7,000 lines (Phase 10)
- **New Development:** ~15,000 lines (virtualization)

**Grand Total:** ~35,500 lines to migrate/develop for Pro+

---

## Dependencies and Risks

### External Dependencies

| Dependency | Risk | Mitigation |
|------------|------|------------|
| libvirt | Breaking changes | Pin version, test upgrades |
| Cloud-init | Image compatibility | Validate per distribution |
| SonarCloud | Service availability | Local SonarQube backup |
| Translation services | Quality variance | Professional review phase |

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Cython compilation issues | Medium | High | Extensive CI testing |
| Cross-platform compatibility | Medium | Medium | Multi-platform CI |
| License bypass attempts | Low | High | Code obfuscation, runtime checks |
| Performance degradation at scale | Medium | High | Load testing in each phase |

### Business Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Feature creep | High | Medium | Strict phase boundaries |
| User confusion on tiers | Medium | Medium | Clear documentation |
| Migration friction | Medium | Medium | Smooth upgrade paths |

---

## Success Metrics

### Quality Metrics

- **Test Coverage:** Backend ≥75%, Agent ≥90%, Pro+ ≥80%
- **SonarQube:** 0 critical issues, <10 major issues
- **Security:** 0 critical vulnerabilities
- **Documentation:** 100% feature coverage

### Performance Metrics

- **API Response Time:** p95 < 200ms
- **Agent Connection:** Support 1000+ concurrent agents
- **Page Load Time:** < 3 seconds
- **WebSocket Latency:** < 100ms

### User Metrics

- **Successful Deployments:** Track installation success rate
- **Feature Adoption:** Track Pro+ feature usage
- **Support Tickets:** Reduce per-release

---

*Document Version: 1.0*
*Last Updated: February 2026*
*Based on: FEATURES-TODO.md, FEATURE-TIERING-ANALYSIS.md, VMM-VMD.md, BHYVE.md, KVM-QEMU.md*
