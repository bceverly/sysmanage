# SysManage Comprehensive Roadmap

This document provides a detailed roadmap for realizing all features in both open-source sysmanage/sysmanage-agent and the commercial sysmanage-professional-plus (Pro+) tiers. It includes feature development phases, intermediate stabilization periods, and release milestones.

---

## Table of Contents

### Historical Releases
1. [Historical Release: v0.9.0 - Project Foundation](#historical-release-v090---project-foundation)
2. [Historical Release: v0.9.0 - Core Platform](#historical-release-v090---core-platform)
3. [Historical Release: v0.9.0 - Multi-Platform Expansion](#historical-release-v090---multi-platform-expansion)
4. [Historical Release: v0.9.0 - Package Distribution](#historical-release-v090---package-distribution)
5. [Historical Release: v0.9.1 - CI/CD & Quality](#historical-release-v091---cicd--quality)
6. [Historical Release: v0.9.2 - Management Features](#historical-release-v092---management-features)
7. [Historical Release: v1.0.0 - Child Host Foundation](#historical-release-v100---child-host-foundation)
8. [Historical Release: v1.0.1 - Virtualization Expansion](#historical-release-v101---virtualization-expansion)
9. [Historical Release: v1.0.2 - Platform Maturity](#historical-release-v102---platform-maturity)
10. [Historical Release: v1.1.0 - Professional+ Launch](#historical-release-v110---professional-launch)

### Current State & Future Roadmap
11. [Current State Assessment](#current-state-assessment)
12. [Release Philosophy](#release-philosophy)
13. [Roadmap Overview](#roadmap-overview)
14. [Phase 0: Current State (Already Implemented)](#phase-0-current-state-already-implemented)
15. [Phase 1: Stabilization](#phase-1-stabilization)
16. [Phase 2: Pro+ Professional Tier](#phase-2-pro-professional-tier)
17. [Phase 3: Pro+ Enterprise Tier - Part 1](#phase-3-pro-enterprise-tier---part-1)
18. [Phase 4: Stabilization](#phase-4-stabilization)
19. [Phase 5: Pro+ Enterprise Tier - Part 2](#phase-5-pro-enterprise-tier---part-2)
20. [Phase 6: Stabilization](#phase-6-stabilization)
21. [Phase 7: Stabilization RC1](#phase-7-stabilization-rc1)
22. [Phase 8: Foundation Features](#phase-8-foundation-features)
23. [Phase 9: Stabilization RC2](#phase-9-stabilization-rc2)
24. [Phase 10: Pro+ Enterprise Tier - Part 3](#phase-10-pro-enterprise-tier---part-3)
25. [Phase 11: Air-Gapped Environment Support (Enterprise)](#phase-11-air-gapped-environment-support-enterprise)
26. [Phase 12: Multi-Site Federation (Enterprise)](#phase-12-multi-site-federation-enterprise)
27. [Phase 13: Enterprise GA (v3.0.0.0)](#phase-13-enterprise-ga-v3000)
28. [Release Schedule Summary](#release-schedule-summary)
29. [Module Migration Plan](#module-migration-plan)

---

# Historical Releases

This section documents the development history of SysManage from initial commit through v1.1.0.0.

---

## Historical Release: v0.9.0 - Project Foundation

**Releases:** Initial commit through v0.9.0.5
**Status:** ✅ Complete

### Core Architecture

- [x] FastAPI backend with SQLAlchemy ORM
- [x] PostgreSQL database with Alembic migrations
- [x] JWT authentication with replay attack mitigation
- [x] HTTPS/TLS support with certificate configuration
- [x] YAML-based configuration system
- [x] Swagger/OpenAPI documentation

### Frontend Foundation

- [x] React.js with TypeScript conversion
- [x] Material-UI component library
- [x] JWT refresh token flow
- [x] Login page with session management
- [x] User management CRUD interface

### Agent Communication

- [x] WebSocket-based real-time communication
- [x] Host registration and status tracking
- [x] Bidirectional message passing

---

## Historical Release: v0.9.0 - Core Platform

**Releases:** v0.9.0.6 through v0.9.0.12
**Status:** ✅ Complete

### Host Management

- [x] Host inventory with real-time status
- [x] CPU, RAM, disk, network monitoring
- [x] Operating system detection and display
- [x] Host approval workflow
- [x] Auto-registration support

### Software Management

- [x] Software inventory collection
- [x] Package manager detection (apt, dnf, pkg, etc.)
- [x] Update availability tracking
- [x] Package installation/removal

### Security Features

- [x] Role-based access control (RBAC)
- [x] Certificate monitoring (SSL expiration)
- [x] Basic firewall status detection
- [x] Basic antivirus status detection

---

## Historical Release: v0.9.0 - Multi-Platform Expansion

**Releases:** v0.9.0.13 through v0.9.0.20
**Status:** ✅ Complete

### BSD Platform Support

- [x] FreeBSD agent and installer
- [x] OpenBSD agent and port
- [x] NetBSD agent and installer

### Package Managers

- [x] pkg (FreeBSD)
- [x] pkg_add (OpenBSD)
- [x] pkgin (NetBSD)
- [x] DNF/YUM (RHEL/CentOS/Fedora)
- [x] Zypper (openSUSE)

### Build Infrastructure

- [x] RPM packaging for CentOS/RHEL
- [x] openSUSE Tumbleweed support
- [x] Software Bill of Materials (SBOM) generation

---

## Historical Release: v0.9.0 - Package Distribution

**Releases:** v0.9.0.21 through v0.9.0.32
**Status:** ✅ Complete

### Desktop Platform Installers

- [x] macOS installer package
- [x] Windows MSI installer
- [x] Windows NSSM service integration

### Linux Distribution Channels

- [x] Launchpad PPA (Ubuntu/Debian)
- [x] Open Build Service (openSUSE/SLES)
- [x] COPR (Fedora/CentOS)

### CI/CD Pipeline

- [x] GitHub Actions build/release workflow
- [x] Multi-platform automated builds
- [x] Automated version tagging

---

## Historical Release: v0.9.1 - CI/CD & Quality

**Releases:** v0.9.1.0 through v0.9.1.12
**Status:** ✅ Complete

### Code Quality

- [x] SonarQube Cloud integration
- [x] Semgrep security scanning
- [x] Code coverage reporting
- [x] Automated dependency updates (Dependabot)

### Distribution Improvements

- [x] Snap package for Ubuntu
- [x] Snap Store integration (latest/edge channel)
- [x] COPR build automation
- [x] Fixed CentOS RPM builds

### Security Hardening

- [x] Addressed Semgrep security issues
- [x] Fixed code scanning alerts
- [x] Dependency vulnerability remediation

---

## Historical Release: v0.9.2 - Management Features

**Releases:** v0.9.2.0 through v0.9.2.4
**Status:** ✅ Complete

### Firewall Management

- [x] Firewall role definitions
- [x] Port rule configuration
- [x] Role assignment to hosts

### User & Group Management

- [x] Add users and groups to hosts
- [x] Delete users and groups from hosts
- [x] Default package manager configuration per OS

### UI Testing

- [x] Selenium test framework
- [x] Playwright E2E tests
- [x] Cross-browser testing (Chrome, Firefox)
- [x] Cross-platform UI tests (Windows, Linux, BSD)

### Repository Management

- [x] Default repository configuration
- [x] Third-party repository support

---

## Historical Release: v1.0.0 - Child Host Foundation

**Releases:** v1.0.0.3 through v1.0.0.9
**Status:** ✅ Complete

### Container Management

- [x] LXD container support (Ubuntu)
- [x] WSL instance support (Windows)
- [x] Container/instance listing and status

### VMM/vmd Support (OpenBSD)

- [x] VM listing and status
- [x] VM creation with autoinstall
- [x] vm.conf generation
- [x] Network configuration

### Alpine Linux

- [x] Alpine as child host OS
- [x] Alpine installer build workflow
- [x] Multiple Alpine version support

### Platform Fixes

- [x] Auto-registration race condition fix
- [x] Unapproved host status visibility
- [x] NSSM dependency handling (Windows)

---

## Historical Release: v1.0.1 - Virtualization Expansion

**Releases:** v1.0.1.0 through v1.0.1.7
**Status:** ✅ Complete

### KVM/QEMU Support (Linux)

- [x] KVM hypervisor integration
- [x] VM creation with cloud-init
- [x] Multi-distribution support (Ubuntu, Debian, Alpine)
- [x] FreeBSD guest installation on KVM

### bhyve Support (FreeBSD)

- [x] bhyve hypervisor integration
- [x] UEFI boot support
- [x] ZFS zvol storage
- [x] NAT networking with pf

### Child Host Expansion

- [x] Debian child host on OpenBSD parent
- [x] FreeBSD child host on KVM
- [x] Cross-platform hashing algorithm support

### Security Scanning

- [x] Manual security scan trigger
- [x] Semgrep Pro integration

---

## Historical Release: v1.0.2 - Platform Maturity

**Releases:** v1.0.2.0 through v1.0.2.2
**Status:** ✅ Complete

### Platform Expansion

- [x] Oracle Linux support
- [x] Additional unit test coverage

### Security Hardening

- [x] bcrypt rounds security fix
- [x] Bandit security issue remediation
- [x] Path expansion security fix

### Code Quality

- [x] Black code formatting
- [x] SonarQube issue resolution
- [x] Test coverage improvements (~55%)

---

## Historical Release: v1.1.0 - Professional+ Launch

**Release:** v1.1.0.0
**Status:** ✅ Complete

### Pro+ Module Architecture

- [x] Cython-compiled backend modules
- [x] JavaScript frontend plugin system
- [x] License validation (ECDSA P-521)
- [x] Feature gating infrastructure

### Professional Tier Modules

- [x] **proplus_core** - License management UI
- [x] **health_engine** - AI-powered health analysis & recommendations
- [x] **compliance_engine** - CIS/DISA STIG auditing

### Enterprise Tier Modules

- [x] **vuln_engine** - CVE vulnerability scanning
- [x] **alerting_engine** - Email/Webhook/Slack/Teams notifications
- [ ] **federation_controller_engine** - Multi-site coordinator with rollup reporting and command dispatch
- [ ] **federation_site_engine** - Site server federation sync and command reception

### Licensing System

- [x] License key validation
- [x] Host count enforcement
- [x] Grace period handling
- [x] Tier-based feature access

---

# Current State & Future Roadmap

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

#### Child Host Management (Open Source - Read Only)
- [x] VM/container listing and status (read-only for all hypervisors)
- [x] Virtualization capability detection

#### Child Host Management (Implemented - Moving to Pro+)

The following virtualization features are implemented and will be migrated to Pro+:

**Professional Tier (~2,000 lines):**
- [x] LXD container management (Ubuntu) - complete
- [x] WSL instance management (Windows) - complete

**Enterprise Tier (~13,000 lines):**
- [x] KVM/QEMU VM management (Linux) - ~90% complete (~4,500 lines)
- [x] bhyve VM management (FreeBSD) - ~90% complete (~4,600 lines)
- [x] VMM/vmd VM management (OpenBSD) - ~70% complete
- [x] Cloud-init provisioning (all hypervisors)
- [x] Multi-hypervisor networking configuration

### Already Implemented - Pro+ (sysmanage-professional-plus)

| Module | Tier | Status | Description |
|--------|------|--------|-------------|
| proplus_core | Professional | ✅ Complete | License management UI |
| health_engine | Professional | ✅ Complete | AI-powered health analysis & recommendations |
| compliance_engine | Professional | ✅ Complete | CIS/DISA STIG auditing |
| vuln_engine | Enterprise | ✅ Complete | CVE vulnerability scanning |
| alerting_engine | Enterprise | ✅ Complete | Email/Webhook/Slack/Teams alerts |
| federation_controller_engine | Enterprise | Planned (Phase 12) | Multi-site coordinator, rollup reporting, command dispatch |
| federation_site_engine | Enterprise | Planned (Phase 12) | Site server sync, command reception, offline resilience |

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

1. **Unit Test Coverage** - Increase test coverage by 5% each stabilization phase
2. **Playwright E2E Tests** - Ensure UI flows work correctly
3. **SonarQube Cleanup** - Resolve all code quality issues
4. **Dependabot Updates** - Apply security patches and dependency updates
5. **Security Analysis** - Review for vulnerabilities (OWASP top 10)
6. **Performance Testing** - Identify and resolve bottlenecks
7. **Documentation Updates** - Keep docs current with features

### Release Versioning

**Current Version:** v1.1.0.0

We use four-part versioning: `major.minor.patch.build`

- **v1.x.0.0** - Open source feature releases (Foundation features)
- **v2.0.0.0** - First Pro+ commercial release (Professional tier modules)
- **v2.x.0.0** - Pro+ feature releases (Enterprise tier modules, Platform)
- **v3.0.0.0** - Major enterprise GA release with full feature set

Each stabilization phase produces a release. Feature phases may produce one or more releases depending on scope.

---

## Roadmap Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SYSMANAGE ROADMAP                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  Phase 0: Current State                                             v1.1.0.0   │
│     └── [DONE] Core platform + virtualization code (moving to Pro+)            │
│                Pro+ modules: proplus_core, health, compliance, vuln, alerting  │
│                                                                                 │
│  Phase 1: Stabilization                                             v1.2.0.0   │
│     └── Unit tests, Playwright, SonarQube, Dependabot, Security audit          │
│                                                                                 │
│  Phase 2: Pro+ Professional Tier                                    v1.3.0.0   │
│     └── reporting, audit, secrets + container_engine (LXD, WSL)                │
│                                                                                 │
│  Phase 3: Pro+ Enterprise Tier - Part 1                             v1.4.0.0   │
│     └── av_management_engine, firewall_orchestration_engine (security first)   │
│                                                                                 │
│  Phase 4: Stabilization                                             v1.5.0.0   │
│     └── Pro+ integration testing, license gating verification                  │
│                                                                                 │
│  Phase 5: Pro+ Enterprise Tier - Part 2                             v1.6.0.0   │
│     └── automation_engine, fleet_engine                                        │
│                                                                                 │
│  Phase 6: Stabilization                                             v1.7.0.0   │
│     └── Test coverage push, full i18n audit, performance baseline              │
│                                                                                 │
│  Phase 7: Stabilization RC1                                         v1.8.0.0   │
│     └── Integration testing, load testing, security penetration test           │
│                                                                                 │
│  Phase 8: Foundation Features (Open Source)                         v2.0.0.0   │
│     └── Access Groups, Scheduled Updates, Compliance, Agent Generic Handlers   │
│                                                                                 │
│  Phase 9: Stabilization RC2                                         v2.1.0.0   │
│     └── Final polish, documentation completion, i18n verification              │
│                                                                                 │
│  Phase 10: Pro+ Enterprise Tier - Part 3                            v2.2.0.0   │
│     └── virtualization_engine, observability_engine, MFA (largest/most complex)│
│                                                                                 │
│  Phase 11: Air-Gapped Environment Support                           v2.3.0.0   │
│     └── Dual-server architecture, optical media transfer, offline CVE sync     │
│                                                                                 │
│  Phase 12: Multi-Site Federation                                    v2.4.0.0   │
│     └── Coordinator + site servers, rollup reporting, command dispatch          │
│                                                                                 │
│  Phase 13: Major Enterprise GA                                      v3.0.0.0   │
│     └── Multi-tenancy, API completeness, platform-native logging, GA release   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Current State (Already Implemented)

**Status:** ✅ Complete

This represents the current baseline. All items listed in [Current State Assessment](#current-state-assessment) are complete and operational.

---

## Phase 1: Stabilization

**Target Release:** v1.2.0.0
**Focus:** Code quality and test coverage

### Goals

1. **Unit Test Coverage**
   - [x] sysmanage backend: Achieve 65% coverage (was ~56%, now 65%) ✅
   - [x] sysmanage-agent: Achieve 65% coverage (was ~59%, now 93%) ✅
   - [x] Pro+ modules: Achieve 70% coverage (achieved 75%) ✅

2. **Playwright E2E Tests**
   - [x] Host list and detail page flows ✅
   - [x] User management flows ✅
   - [x] Settings page flows ✅
   - [x] Child host creation flows (LXD, WSL) ✅
   - [x] Pro+ feature flows (health analysis, compliance) ✅

3. **SonarQube Cleanup**
   - [x] sysmanage-agent: 0 issues ✅
   - [x] sysmanage backend: 0 critical/major issues ✅
   - [x] sysmanage frontend: 0 critical issues ✅

4. **Dependabot Updates**
   - [x] Apply all security patches ✅
   - [x] Update to latest stable versions of key dependencies ✅
   - [x] Resolve any breaking changes ✅
   - Note: bcrypt 5.0.0 blocked by passlib incompatibility; eslint 10 blocked by react-hooks plugin

5. **Security Analysis**
   - [x] OWASP dependency check (Safety, Snyk, npm audit) ✅
   - [x] SQL injection audit (Semgrep, Bandit) ✅
   - [x] XSS vulnerability scan (ESLint security plugin, eslint-plugin-no-unsanitized) ✅
   - [x] Authentication flow review ✅
   - [x] Secret handling audit (TruffleHog) ✅

### Deliverables

- [x] All SonarQube critical/major issues resolved ✅
- [x] Test coverage reports published (Codecov integration, README badges, SonarCloud) ✅
- [x] Security audit report documented (comprehensive CI/CD security scanning) ✅
- [x] Performance baseline established (Artillery load testing with p95/p99 thresholds) ✅

### Exit Criteria

- [x] SonarQube: 0 critical issues, <10 major issues ✅
- [x] Backend test coverage: ≥65% (achieved 65%) ✅
- [x] Agent test coverage: ≥65% (achieved 93%) ✅
- [x] Pro+ test coverage: ≥70% (achieved 75%) ✅
- [x] All Dependabot security alerts resolved ✅

---

## Phase 2: Pro+ Professional Tier

**Target Release:** v1.3.0.0
**Focus:** Migrate Professional-tier features from open source to Pro+

### Modules to Migrate

#### 2.1 reporting_engine (Professional)

**Source Files:**
- `backend/api/reports/endpoints.py` -> Stubbed (returns Pro+ required)
- `backend/api/reports/pdf/` -> Moved to Pro+
- `backend/api/reports/html/` -> Moved to Pro+

**Features:**
- [x] PDF report generation (host inventory, user management)
- [x] HTML report generation
- [x] Scheduled report delivery
- [x] Export to multiple formats (PDF, HTML)

**Migration Steps:**
1. [x] Create `module-source/reporting_engine/` structure
2. [x] Create `reporting_engine.pyx` Cython module
3. [x] Migrate code with license gating
4. [x] Create frontend plugin bundle
5. [x] Remove from open source (replace with license check)
6. [x] Update documentation (proplus_routes.py integration)
7. [x] i18n/l10n for all 14 languages

**Actual Size:** ~1,200 lines Cython + ~300 lines frontend

#### 2.2 audit_engine (Professional)

**Source Files:**
- `backend/api/audit_log.py` -> Kept basic functionality in open source
- `backend/services/audit_service.py` -> Kept basic logging in open source

**Features:**
- [x] Comprehensive audit trail with entity change tracking
- [x] IP address and user agent logging
- [x] Audit log retention policies
- [x] Compliance export formats (CSV, JSON, SIEM-compatible - CEF/LEEF)
- [x] Advanced audit log search and filtering
- [x] Tamper-evident logging (SHA-256 integrity hashing)
- [x] Audit log archival and rotation
- [x] Audit statistics and analytics

**Keep in Open Source:**
- Basic activity logging (login events, simple action tracking)

**Migration Steps:**
1. [x] Create `module-source/audit_engine/` structure
2. [x] Create `audit_engine.pyx` Cython module
3. [x] Split basic vs advanced audit functionality
4. [x] Migrate advanced features with license gating
5. [x] Create frontend plugin bundle
6. [x] Update documentation (proplus_routes.py integration)
7. [x] i18n/l10n for all 14 languages

**Actual Size:** ~600 lines Cython + ~300 lines frontend

#### 2.3 secrets_engine (Professional)

**Server-Side Source Files:**
- `backend/api/secrets/crud.py`
- `backend/api/secrets/deployment.py`
- `backend/api/secrets/models.py`
- `backend/api/openbao.py`
- `backend/services/vault_service.py`

**Agent-Side Source Files (deployment logic moved to server):**
- `sysmanage_agent/operations/ssh_key_operations.py` (~253 lines) — SSH key deployment
- `sysmanage_agent/operations/certificate_operations.py` (~256 lines) — Certificate deployment

**Features:**
- [x] OpenBAO/Vault integration
- [x] Encrypted secret storage
- [x] Secret deployment to hosts (SSH keys, certificates)
- [x] Credential rotation scheduling
- [x] Secret access auditing
- [x] Secret versioning

**Migration Steps:**
1. [x] Create `module-source/secrets_engine/` structure
2. [x] Create `secrets_engine.pyx` Cython module
3. [x] Migrate all secrets functionality
4. [x] Extract SSH key and certificate deployment logic from agent (~509 lines) to server-side Cython
5. [x] Create frontend plugin bundle
6. [x] Remove from open source (all endpoints return 402 without secrets_engine)
7. [x] Update documentation (proplus_routes.py integration)
8. [x] i18n/l10n for all 14 languages

**Actual Size:** ~500 lines Cython + ~300 lines frontend + ~509 lines migrated from agent

#### 2.4 container_engine (Professional)

**Server-Side Source Files:**
- `backend/api/child_host_virtualization.py` (container portions)
- `backend/api/handlers/child_host/control.py` (container portions)

**Agent-Side Source Files (config construction logic moved to server):**
- `sysmanage_agent/operations/child_host_lxd.py` (~800 lines) — LXD orchestrator
- `sysmanage_agent/operations/child_host_lxd_container_creator.py` (~600 lines) — LXD creation
- `sysmanage_agent/operations/child_host_wsl.py` (~500 lines) — WSL orchestrator
- `sysmanage_agent/operations/child_host_wsl_setup.py` (~450 lines) — WSL setup/provisioning
- `sysmanage_agent/operations/child_host_wsl_control.py` (~350 lines) — WSL lifecycle
- `sysmanage_agent/operations/child_host_listing_wsl.py` (~295 lines) — WSL listing

**Features:**
- [x] LXD container creation and lifecycle (Ubuntu)
- [x] LXD container networking
- [x] WSL instance creation and lifecycle (Windows)
- [x] WSL distribution management
- [x] Container/instance status monitoring

**Keep in Open Source:**
- Read-only container/instance listing

**Migration Steps:**
1. [x] Create `module-source/container_engine/` structure
2. [x] Create `container_engine.pyx` Cython module
3. [x] Migrate LXD and WSL management code
4. [x] Extract config/provisioning logic from agent (~2,995 lines) to server-side Cython
5. [x] Create frontend plugin bundle
6. [x] Update open source to read-only listing (all write endpoints return 402 without container_engine)
7. [x] Update documentation (proplus_routes.py integration)
8. [x] i18n/l10n for all 14 languages

**Actual Size:** ~400 lines Cython + ~300 lines frontend + ~2,995 lines migrated from agent

#### 2.5 Safe Parent Host Reboot with Child Host Orchestration

**Priority:** High
**Effort:** Medium

Rebooting a parent host without cleanly stopping its running child hosts (VMs, containers, WSL instances) can cause data corruption, filesystem damage, or service outages on the children. This feature adds safety orchestration around parent host reboots.

**Open Source (detection and warning):**
- [x] When a user initiates a reboot on a parent host, query for running child hosts on that parent
- [x] Display a warning dialog listing all running child hosts and the risk of unclean shutdown
- [x] Require explicit user confirmation before proceeding
- [x] If no Pro+ container_engine is available, warn but allow the user to proceed with a manual reboot (child hosts will not be automatically managed)

**Pro+ container_engine (automated orchestration for LXD/WSL):**
- [x] On confirmed parent reboot, record which child hosts are currently running (persist to database)
- [x] Cleanly shut down all running LXD containers and WSL instances on the parent before issuing the reboot command
- [x] Wait for child host shutdown confirmation before proceeding with parent reboot
- [x] After parent host boots and agent reconnects, automatically restart the child hosts that were running at the time of reboot
- [x] Report restart status to the user (success/failure per child host)
- [x] Handle edge cases: child hosts that fail to stop gracefully (force stop after timeout), child hosts that fail to restart

**Note:** Phase 10 (virtualization_engine) extends this capability to KVM/QEMU, bhyve, and VMM/vmd virtual machines.

- [x] i18n/l10n for all 14 languages

### Deliverables

- [x] 4 new Pro+ modules (reporting, audit, secrets, container)
- [x] Open source code updated with license checks
- [x] Documentation accurately describes Pro+/Community feature split (no separate migration guide needed — no existing users to migrate)
- [x] Safe parent host reboot with child host orchestration (Section 2.5)
- [x] Frontend i18n gap fill for all 13 non-English locales

---

## Phase 3: Pro+ Enterprise Tier - Part 1

**Target Release:** v1.4.0.0
**Focus:** Security engines for Enterprise tier (AV and firewall management)

### Architecture Decision: Server-Side Config Generation

**Problem:** The sysmanage-agent currently contains ~13,900 lines of configuration
construction code for firewalls (~8,000 lines across 15 files) and antivirus (~5,800
lines across 12 files). This code generates platform-specific config files (UFW rules,
firewalld XML, pf.conf, IPFW rules, NPF rules, Windows Firewall netsh commands,
ClamAV configs, etc.) and deploys them locally on the agent host.

Migrating this to Pro+ presents a licensing enforcement challenge: the agent is open
source Python running on customer machines, making license checks trivially bypassable.
Adding license management infrastructure to the agent is undesirable.

**Decision:** Move all configuration construction logic to the server-side Cython
modules. The Pro+ modules on the server will:

1. **Generate platform-specific config files** using the host's OS/platform info
   already collected and stored in the database
2. **Send fully-baked config files** to the agent via the existing message queue,
   along with deployment instructions (target path, permissions, service restart
   commands)
3. **The agent receives generic "deploy file" and "run command" messages** — no
   firewall/AV business logic remains in the agent

**Benefits:**
- **License enforcement is airtight** — the Cython-compiled server module is the
  only place config generation happens
- **Agent stays simple** — it deploys files and runs commands, a pattern it already
  supports for secrets deployment and script execution
- **Centralized logic** — config generation is testable on the server without
  platform-specific agent environments
- **No agent license infrastructure needed** — avoids adding license validation,
  key management, and module loading to the agent codebase

**Agent changes:**
- Firewall/AV *collection* code stays in the agent and open source (read-only
  status detection)
- Firewall/AV *deployment* operations are replaced with generic file deployment
  and service control handlers (or reuse existing ones)
- ~13,900 lines of config construction code removed from the agent

### Modules to Migrate

#### 3.1 av_management_engine (Enterprise)

**Server-Side Source Files (to migrate to Cython):**
- `backend/api/antivirus_*.py`

**Agent-Side Source Files (config construction logic to move to server):**
- `sysmanage_agent/operations/antivirus_operations.py` (618 lines) — orchestrator
- `sysmanage_agent/operations/antivirus_base.py` (961 lines) — base class, config templates
- `sysmanage_agent/operations/antivirus_deploy_linux.py` (243 lines) — Debian/Ubuntu, RHEL/CentOS, openSUSE
- `sysmanage_agent/operations/antivirus_deploy_windows.py` (113 lines) — ClamWin via Chocolatey
- `sysmanage_agent/operations/antivirus_deploy_bsd.py` (660 lines) — macOS, FreeBSD, OpenBSD, NetBSD
- `sysmanage_agent/operations/antivirus_remove_linux.py` (151 lines)
- `sysmanage_agent/operations/antivirus_remove_windows.py` (74 lines)
- `sysmanage_agent/operations/antivirus_remove_bsd.py` (292 lines)
- `sysmanage_agent/operations/antivirus_deployment_helpers.py` (830 lines)
- `sysmanage_agent/operations/antivirus_removal_helpers.py` (455 lines)
- `sysmanage_agent/operations/antivirus_service_manager.py` (530 lines)
- `sysmanage_agent/operations/antivirus_utils.py` (25 lines)

**Agent-Side Collection (stays in agent, open source):**
- `sysmanage_agent/collection/antivirus_collection.py`
- `sysmanage_agent/collection/commercial_antivirus_collection.py`

**Features:**
- [ ] ClamAV/ClamWin deployment and configuration
- [ ] Antivirus service control
- [ ] Scan scheduling and management
- [ ] Commercial AV detection (CrowdStrike, SentinelOne, etc.)
- [ ] Definition update management
- [ ] AV policy deployment

**Keep in Open Source:**
- Basic AV status detection (is AV installed and running)
- Agent-side collection of AV status and commercial AV detection

**Migration Steps:**
1. [ ] Create `module-source/av_management_engine/` structure
2. [ ] Create `av_management_engine.pyx` Cython module
3. [ ] Extract config generation logic from agent operations into server-side Cython module
4. [ ] Implement platform-specific config builders (Linux/Windows/BSD/macOS) on server
5. [ ] Define message protocol for "deploy AV config" commands (file content, target path, service commands)
6. [ ] Update agent to handle generic file deployment + service control messages
7. [ ] Remove config construction code from agent (~5,800 lines)
8. [ ] Create frontend plugin bundle
9. [ ] Update open source server to return 402 without av_management_engine
10. [ ] Update documentation
11. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~6,500 lines (server-side Cython: ~5,800 from agent + ~700 server API)

#### 3.2 firewall_orchestration_engine (Enterprise)

**Server-Side Source Files (to migrate to Cython):**
- `backend/api/firewall_roles*.py`
- `backend/persistence/models/firewall.py`

**Agent-Side Source Files (config construction logic to move to server):**
- `sysmanage_agent/operations/firewall_operations.py` (272 lines) — orchestrator
- `sysmanage_agent/operations/firewall_base.py` (161 lines) — base class
- `sysmanage_agent/operations/firewall_linux.py` (231 lines) — Linux dispatcher
- `sysmanage_agent/operations/firewall_linux_ufw.py` (707 lines) — UFW rule generation
- `sysmanage_agent/operations/firewall_linux_firewalld.py` (509 lines) — firewalld config
- `sysmanage_agent/operations/firewall_linux_parsers.py` (353 lines) — rule parsing
- `sysmanage_agent/operations/firewall_bsd.py` (496 lines) — BSD dispatcher
- `sysmanage_agent/operations/firewall_bsd_pf.py` (278 lines) — pf.conf generation
- `sysmanage_agent/operations/firewall_bsd_ipfw.py` (298 lines) — IPFW rule generation
- `sysmanage_agent/operations/firewall_bsd_npf.py` (303 lines) — NPF rule generation
- `sysmanage_agent/operations/firewall_bsd_parsers.py` (449 lines) — BSD rule parsing
- `sysmanage_agent/operations/firewall_windows.py` (592 lines) — Windows Firewall/netsh
- `sysmanage_agent/operations/firewall_macos.py` (315 lines) — macOS socketfilterfw
- `sysmanage_agent/operations/firewall_port_helpers.py` (499 lines) — port helpers
- `sysmanage_agent/operations/firewall_collector.py` (483 lines) — status collection

**Agent-Side Collection (stays in agent, open source):**
- `sysmanage_agent/operations/firewall_collector.py` — firewall status collection
- `sysmanage_agent/collection/` firewall-related collection modules

**Features:**
- [ ] Firewall role definitions with port rules
- [ ] Role assignment to hosts
- [ ] Policy deployment across fleets
- [ ] Multi-platform firewall config generation (UFW, firewalld, pf, ipfw, npf, Windows Firewall, macOS)
- [ ] Firewall compliance checking
- [ ] Rule conflict detection

**Keep in Open Source:**
- Basic firewall status reporting (read-only)
- Agent-side firewall status collection

**Migration Steps:**
1. [ ] Create `module-source/firewall_orchestration_engine/` structure
2. [ ] Create `firewall_orchestration_engine.pyx` Cython module
3. [ ] Extract config generation logic from agent operations into server-side Cython module
4. [ ] Implement platform-specific firewall config builders on server:
   - UFW rules (Ubuntu/Debian)
   - firewalld XML zones/services (RHEL/CentOS/Fedora)
   - pf.conf rules (OpenBSD/FreeBSD)
   - IPFW rules (FreeBSD)
   - NPF rules (NetBSD)
   - Windows Firewall netsh commands
   - macOS socketfilterfw commands
5. [ ] Define message protocol for "deploy firewall config" commands
6. [ ] Update agent to handle generic file deployment + command execution messages
7. [ ] Remove config construction code from agent (~8,000 lines)
8. [ ] Create frontend plugin bundle
9. [ ] Update open source server to return 402 without firewall_orchestration_engine
10. [ ] Update documentation
11. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~9,500 lines (server-side Cython: ~8,000 from agent + ~1,500 server API/models)

### Deliverables

- [ ] 2 new Pro+ modules (AV management, firewall orchestration)
- [ ] Server-side config generation for all supported platforms
- [ ] Agent generic deployment handlers operational (from Phase 8, or implemented early as dependency)
- [ ] ~13,800 lines of config construction code removed from agent
- [ ] Open source code updated with stubs/license checks
- [ ] Documentation for Enterprise tier features

**Note:** Phase 3 depends on the agent generic deployment handlers (Section 8.6). These
handlers must be implemented before Phase 3 modules can function. If Phase 8 has not yet
shipped, the generic handlers should be implemented early as a Phase 3 prerequisite.

---

## Phase 4: Stabilization

**Target Release:** v1.5.0.0
**Focus:** Pro+ integration testing and license gating verification

### Goals

1. **Pro+ Module Testing**
   - [ ] Verify all Professional and Enterprise Part 1 modules work correctly
   - [ ] License gating verification for each module
   - [ ] Plugin loading and registration testing
   - [ ] Cross-module integration tests

2. **Container Engine Testing**
   - [ ] LXD container lifecycle testing on Ubuntu
   - [ ] WSL instance lifecycle testing on Windows
   - [ ] Verify read-only mode for unlicensed users

3. **Security Engine Testing**
   - [ ] AV management engine testing across platforms
   - [ ] Firewall orchestration engine testing across platforms
   - [ ] Verify read-only mode for unlicensed users

4. **Documentation**
   - [ ] Professional tier feature documentation
   - [ ] Enterprise Part 1 feature documentation
   - [ ] Upgrade guide from open source to Professional/Enterprise

### Exit Criteria

- All Professional and Enterprise Part 1 modules functional
- License gating working correctly
- No critical bugs in Pro+ modules

---

## Phase 5: Pro+ Enterprise Tier - Part 2

**Target Release:** v1.6.0.0
**Focus:** Automation and fleet management for Enterprise tier

### Modules to Migrate

#### 5.1 automation_engine (Enterprise)

**Server-Side Source Files:**
- `backend/api/scripts/routes_saved_scripts.py`
- `backend/api/scripts/routes_executions.py`
- `backend/api/scripts/models.py`
- `backend/persistence/models/scripts.py`

**Agent-Side Source Files (execution logic moved to server orchestration):**
- `sysmanage_agent/operations/script_operations.py` (~328 lines) — script execution engine

**Features:**
- [ ] Saved script library with versioning
- [ ] Script execution across multiple hosts
- [ ] Execution logging with stdout/stderr capture
- [ ] Multi-shell support (bash, zsh, PowerShell, cmd, ksh)
- [ ] Scheduled script execution
- [ ] Approval workflows for privileged scripts
- [ ] Script parameterization

**Estimated Size:** ~2,300 lines (server-side Cython: ~2,000 server + ~300 from agent orchestration logic)

#### 5.2 fleet_engine (Enterprise)

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

- [ ] 2 new Pro+ modules (automation, fleet)
- [ ] Documentation for Enterprise tier features

---

## Phase 6: Stabilization

**Target Release:** v1.7.0.0
**Focus:** Test coverage push, i18n audit, performance baseline

### Goals

1. **Test Coverage Push** (+5% from Phase 1)
   - [ ] Backend coverage: Target 70%
   - [ ] Agent coverage: Target 70%
   - [ ] Pro+ coverage: Target 75%
   - [ ] Add integration tests for new Pro+ features
   - [ ] Playwright tests for Pro+ feature UI flows

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

- Backend test coverage: ≥70%
- Agent test coverage: ≥70%
- Pro+ test coverage: ≥75%
- All translations verified complete
- Performance baselines documented
- No critical bugs in Pro+ features

---

## Phase 7: Stabilization RC1

**Target Release:** v1.8.0.0
**Focus:** Integration testing, load testing, security penetration test

### Goals

1. **Test Coverage Push** (+5% from Phase 6)
   - [ ] Backend coverage: Target 75%
   - [ ] Agent coverage: Target 75%
   - [ ] Pro+ coverage: Target 80%

2. **Integration Testing**
   - [ ] End-to-end tests for container_engine (LXD, WSL)
   - [ ] End-to-end tests for av_management_engine
   - [ ] End-to-end tests for firewall_orchestration_engine
   - [ ] End-to-end tests for automation_engine and fleet_engine
   - [ ] Cross-platform agent testing
   - [ ] Pro+ module integration tests
   - [ ] WebSocket reliability under load

3. **Load Testing**
   - [ ] 100 concurrent agents
   - [ ] 500 concurrent agents
   - [ ] 1000 concurrent agents
   - [ ] Database query performance under load
   - [ ] WebSocket message throughput

4. **Security Penetration Test**
   - [ ] External penetration test (if budget allows)
   - [ ] Internal security review
   - [ ] Authentication bypass attempts
   - [ ] Privilege escalation attempts
   - [ ] WebSocket security review

5. **Bug Fixes**
   - [ ] Resolve all critical bugs
   - [ ] Resolve all high-priority bugs
   - [ ] Triage and document remaining bugs

### Exit Criteria

- Backend test coverage: ≥75%
- Agent test coverage: ≥75%
- Pro+ test coverage: ≥80%
- All integration tests passing
- Load test targets met
- Security review complete with no critical findings
- No critical bugs remaining

---

## Phase 8: Foundation Features

**Target Release:** v2.0.0.0
**Focus:** Open-source feature completion (FEATURES-TODO.md items #2-6)

### Features

#### 8.1 Access Groups and Registration Keys

**Priority:** High
**Effort:** Medium

- [ ] AccessGroup model with hierarchy (parent/child)
- [ ] RegistrationKey model with access group association
- [ ] Registration key auto-approval workflow
- [ ] RBAC scoping by access group
- [ ] Frontend: Access group management in Settings
- [ ] i18n/l10n for all 14 languages

#### 8.2 Scheduled Update Profiles

**Priority:** High
**Effort:** Medium

- [ ] UpgradeProfile model with cron scheduling
- [ ] Security-only update option
- [ ] Profile-tag associations
- [ ] Staggered rollout windows
- [ ] APScheduler integration
- [ ] Frontend: Automation tab with profile management
- [ ] i18n/l10n for all 14 languages

#### 8.3 Package Compliance Profiles

**Priority:** Medium
**Effort:** Medium

- [ ] PackageProfile and PackageProfileConstraint models
- [ ] Required/blocked package definitions
- [ ] Version constraint support
- [ ] Agent-side compliance checking
- [ ] HostComplianceStatus storage
- [ ] Frontend: Compliance tab in HostDetail
- [ ] i18n/l10n for all 14 languages

#### 8.4 Activity Audit Log Enhancement

**Priority:** High
**Effort:** Low

- [ ] EXECUTE action type for script executions
- [ ] Script output storage in details JSON
- [ ] Enhanced filtering (date range, entity type, user, result)
- [ ] Export to CSV/PDF
- [ ] Audit all API endpoints
- [ ] i18n/l10n for all 14 languages

#### 8.5 Broadcast Messaging

**Priority:** Medium
**Effort:** Medium

- [ ] BROADCAST message type
- [ ] Efficient broadcast channel implementation
- [ ] Agent broadcast message handler
- [ ] Frontend: "Broadcast Refresh" button
- [ ] i18n/l10n for all 14 languages

#### 8.6 Agent Generic Deployment Handlers (Open Source)

**Priority:** High (prerequisite for Phase 3, 5, 10 Pro+ modules)
**Effort:** Medium

The server-side config generation architecture (decided in Phase 3) requires the open-source
agent to support generic file deployment and command execution messages. These handlers enable
all Pro+ modules to send fully-baked config files and deployment instructions to the agent
without any module-specific logic in the agent itself.

**Agent-Side Changes (~1,500 estimated lines):**
- [ ] Generic file deployment handler — receive file content, target path, ownership, and permissions from server; write file to disk atomically (write to temp, rename)
- [ ] Generic command execution handler — receive a command list from server; execute sequentially with stdout/stderr capture and exit code reporting
- [ ] Generic service control handler — receive service name + action (start/stop/restart/enable/disable); use platform-appropriate service manager (systemd, rc.d, services.msc, launchctl)
- [ ] Deployment receipt/acknowledgment messages — report success/failure back to server for each deployment step
- [ ] File integrity verification — optional SHA-256 checksum verification before writing deployed files
- [ ] Rollback support — backup existing config files before overwriting; restore on deployment failure
- [ ] Message protocol documentation for "deploy file", "execute command", and "control service" message types

**Note:** These handlers are open source because they are generic infrastructure — they deploy
files and run commands without any knowledge of what the files contain. The Pro+ value is in
the server-side Cython modules that *generate* the config files (firewall rules, AV configs,
VM definitions, OTEL configs, etc.).

- [ ] i18n/l10n for all 14 languages
- [ ] Unit tests for all new handlers

#### 8.7 Pro+ Professional Tier Enhancements

**Priority:** Medium
**Effort:** Medium

- [ ] Custom report templates (reporting_engine) — allow admins to define custom report layouts and field selections beyond the built-in reports
- [ ] Report branding/customization (reporting_engine) — add organization logo, company name, and color scheme to generated PDF/HTML reports
- [ ] Dynamic secret generation (secrets_engine) — generate short-lived, on-demand credentials via OpenBAO/Vault that automatically expire
- [ ] i18n/l10n for all 14 languages

### Deliverables

- [ ] All Foundation features implemented and tested
- [ ] Agent generic deployment handlers implemented and tested (prerequisite for Phase 3/5/10 Pro+)
- [ ] Pro+ Professional tier enhancements implemented
- [ ] API documentation updated
- [ ] User documentation updated

---

## Phase 9: Stabilization RC2

**Target Release:** v2.1.0.0
**Focus:** Final polish, documentation completion, i18n verification

### Goals

1. **Test Coverage Push** (+5% from Phase 7)
   - [ ] Backend coverage: Target 80%
   - [ ] Agent coverage: Target 80%
   - [ ] Pro+ coverage: Target 85%

2. **Documentation Completion**
   - [ ] All features documented
   - [ ] API reference 100% complete
   - [ ] Deployment guides for all platforms
   - [ ] Troubleshooting guides
   - [ ] Migration guides

3. **i18n Verification**
   - [ ] All 14 languages complete
   - [ ] Professional review of translations (if budget allows)
   - [ ] UI screenshot verification per language

4. **UI/UX Polish**
   - [ ] Consistent styling across all pages
   - [ ] Accessibility audit (WCAG 2.1 AA)
   - [ ] Mobile responsiveness verification
   - [ ] Loading state improvements

5. **Performance Optimization**
   - [ ] Database query optimization
   - [ ] Frontend bundle optimization
   - [ ] API response time optimization
   - [ ] WebSocket efficiency improvements

### Exit Criteria

- Backend test coverage: ≥80%
- Agent test coverage: ≥80%
- Pro+ test coverage: ≥85%
- All documentation complete
- All translations verified
- Accessibility audit passed
- Performance targets met

---

## Phase 10: Pro+ Enterprise Tier - Part 3

**Target Release:** v2.2.0.0
**Focus:** Final Pro+ Enterprise-tier modules (largest/most complex)

### Modules to Migrate

#### 10.1 virtualization_engine (Enterprise)

**Server-Side Source Files (to migrate to Cython):**
- `backend/api/child_host_virtualization.py`
- `backend/api/child_host_virtualization_enable.py`
- `backend/api/handlers/child_host/control.py`
- `backend/api/child_host_control.py`
- `backend/api/child_host_crud.py`

**Agent-Side Source Files (VM management logic to move to server):**
- KVM/QEMU (~4,500 lines across 8 files):
  - `sysmanage_agent/operations/child_host_kvm.py` — KVM orchestrator
  - `sysmanage_agent/operations/child_host_kvm_create.py` — VM creation
  - `sysmanage_agent/operations/child_host_kvm_network.py` — NAT/bridge networking
  - `sysmanage_agent/operations/child_host_kvm_storage.py` — disk/image management
  - `sysmanage_agent/operations/child_host_kvm_cloudinit.py` — cloud-init ISO generation
  - `sysmanage_agent/operations/child_host_kvm_control.py` — lifecycle control
  - `sysmanage_agent/operations/child_host_kvm_listing.py` — VM listing
  - `sysmanage_agent/operations/child_host_kvm_delete.py` — VM deletion
- bhyve (~4,600 lines across 10 files):
  - `sysmanage_agent/operations/child_host_bhyve.py` — bhyve orchestrator
  - `sysmanage_agent/operations/child_host_bhyve_create.py` — VM creation
  - `sysmanage_agent/operations/child_host_bhyve_network.py` — NAT with pf
  - `sysmanage_agent/operations/child_host_bhyve_storage.py` — ZFS zvol management
  - `sysmanage_agent/operations/child_host_bhyve_uefi.py` — UEFI boot
  - `sysmanage_agent/operations/child_host_bhyve_control.py` — lifecycle control
  - `sysmanage_agent/operations/child_host_bhyve_listing.py` — VM listing
  - `sysmanage_agent/operations/child_host_bhyve_delete.py` — VM deletion
  - `sysmanage_agent/operations/child_host_bhyve_cloudinit.py` — cloud-init
  - `sysmanage_agent/operations/child_host_bhyve_freebsd.py` — FreeBSD guest
- VMM/vmd (~6,800 lines across 17 files):
  - `sysmanage_agent/operations/child_host_vmm*.py` — OpenBSD VMM management
- Guest provisioning (~6,253 lines):
  - `sysmanage_agent/operations/child_host_ubuntu*.py` — Ubuntu autoinstall
  - `sysmanage_agent/operations/child_host_debian*.py` — Debian preseed
  - `sysmanage_agent/operations/child_host_alpine*.py` — Alpine setup
  - `sysmanage_agent/operations/child_host_freebsd*.py` — FreeBSD install

**Agent-Side Collection (stays in agent, open source):**
- `sysmanage_agent/operations/child_host_listing_*.py` — read-only VM/container listing

**Features:**
- [ ] KVM/QEMU VM management (Linux)
  - [ ] VM creation with cloud-init
  - [ ] VM lifecycle (start, stop, restart, delete)
  - [ ] Network configuration (NAT, bridge)
  - [ ] Multi-distro support (Ubuntu, Debian, Fedora, Alpine, FreeBSD)
- [ ] bhyve VM management (FreeBSD)
  - [ ] UEFI and bhyveload boot support
  - [ ] ZFS zvol or file-based storage
  - [ ] NAT networking with pf
- [ ] VMM/vmd VM management (OpenBSD)
  - [ ] vm.conf generation
  - [ ] Autoinstall support
- [ ] Cloud-init provisioning (all hypervisors)
- [ ] Multi-hypervisor networking
- [ ] Guest OS autoinstall (Ubuntu, Debian, Alpine, FreeBSD)
- [ ] **Safe Parent Host Reboot (VM extension):** Extend the safe parent host reboot orchestration (introduced in Phase 2 for LXD/WSL) to KVM/QEMU, bhyve, and VMM/vmd virtual machines — cleanly shut down running VMs before parent reboot, track which VMs were running, and automatically restart them after the parent boots back up

**Keep in Open Source:**
- Read-only VM/container listing and status

**Migration Steps:**
1. [ ] Create `module-source/virtualization_engine/` structure
2. [ ] Create `virtualization_engine.pyx` Cython module
3. [ ] Extract VM creation/provisioning logic from agent into server-side Cython module
4. [ ] Implement platform-specific VM config builders on server (KVM XML, bhyve config, vm.conf)
5. [ ] Extract cloud-init/autoinstall generation from agent to server
6. [ ] Extract network configuration generation from agent to server
7. [ ] Define message protocol for "deploy VM config" commands
8. [ ] Remove VM management code from agent (~22,153 lines)
9. [ ] Create frontend plugin bundle
10. [ ] Update open source to read-only listing
11. [ ] Update documentation
12. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~24,000 lines (server-side Cython: ~22,153 from agent + ~1,850 server API)

#### 10.2 observability_engine (Enterprise)

**Server-Side Source Files (to migrate to Cython):**
- `backend/api/graylog_integration.py`
- `backend/services/graylog_integration.py`
- `backend/api/grafana_integration.py`
- `backend/services/grafana_integration.py`
- `backend/api/opentelemetry/*`

**Agent-Side Source Files (deployment logic to move to server):**
- `sysmanage_agent/operations/graylog_operations.py` (~662 lines) — Graylog sidecar/forwarder deployment
- `sysmanage_agent/operations/opentelemetry_operations.py` (~900 lines) — OTEL collector deployment
- `sysmanage_agent/operations/opentelemetry_config.py` (~774 lines) — OTEL config generation

**Agent-Side Collection (stays in agent, open source):**
- Prometheus metrics endpoint (if applicable)

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

**Migration Steps:**
1. [ ] Create `module-source/observability_engine/` structure
2. [ ] Create `observability_engine.pyx` Cython module
3. [ ] Extract Graylog deployment/config logic from agent (~662 lines) to server-side Cython
4. [ ] Extract OpenTelemetry deployment/config logic from agent (~1,674 lines) to server-side Cython
5. [ ] Implement server-side config generation for OTEL collector, Graylog sidecar, Grafana datasources
6. [ ] Define message protocol for "deploy observability config" commands
7. [ ] Remove deployment code from agent (~2,336 lines)
8. [ ] Create frontend plugin bundle
9. [ ] Update documentation
10. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~6,300 lines (server-side Cython: ~2,336 from agent + ~4,000 server API/services)

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

- [ ] virtualization_engine module (~24,000 lines, largest single module)
- [ ] observability_engine module (~6,300 lines)
- [ ] ~24,489 lines of agent code migrated to server-side Cython
- [ ] MFA implementation
- [ ] Repository mirroring
- [ ] External IdP support

---

## Phase 11: Air-Gapped Environment Support (Enterprise)

**Target Release:** v2.3.0.0
**Focus:** Dual-server architecture for managing hosts on isolated, air-gapped networks

### Overview

Many enterprise and government environments operate air-gapped networks that have no connection to the public internet. This phase introduces a dual-server architecture that enables full SysManage management capabilities across the air gap, including OS patching, vulnerability assessment, and compliance reporting with appropriate context for the isolated environment.

### Architecture

**Public-Side SysManage Server ("Collector")**
- Connected to the public internet
- Configured with a list of target operating systems and versions to track
- Periodically captures all available OS updates (packages, patches, security fixes)
- Captures current CVE/vulnerability data from public databases (NVD, vendor advisories)
- Captures compliance framework updates (CIS benchmarks, STIG updates)
- Burns collected data to optical media (CD/DVD/Blu-ray) for physical transfer
- Generates manifest and integrity checksums for each media set

**Private-Side SysManage Server ("Repository")**
- Connected only to the air-gapped network
- Reads optical media produced by the public-side server
- Imports updates into a local package repository
- Acts as the authoritative update source for all managed hosts on the private network
- Hosts see the private repository as their normal OS update mirror
- Imports CVE data to enable vulnerability scanning with point-in-time context
- Reports compliance based on what is available in the private repository

### Modules

#### 11.1 airgap_collector_engine (Enterprise)

**Features:**
- [ ] Configurable OS/version tracking list (Ubuntu, Debian, RHEL, FreeBSD, etc.)
- [ ] Automated package mirror capture (APT, DNF/YUM, pkg, etc.)
- [ ] CVE/NVD data snapshot capture at time of collection
- [ ] Compliance framework data capture (CIS, DISA STIG baselines)
- [ ] Optical media ISO image generation with integrity checksums (SHA-256)
- [ ] Multi-disc spanning for large update sets
- [ ] Disc burning integration (cdrecord/growisofs/xorriso)
- [ ] Collection scheduling (daily, weekly, on-demand)
- [ ] Manifest generation with package counts, CVE counts, and timestamps
- [ ] Delta collection mode (only new packages since last burn)
- [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~4,000 lines

#### 11.2 airgap_repository_engine (Enterprise)

**Features:**
- [ ] Optical media ingestion with integrity verification
- [ ] Local APT/DNF/YUM/pkg repository hosting
- [ ] Repository metadata generation (Packages.gz, repodata, etc.)
- [ ] Automatic agent repository configuration (point hosts to private mirror)
- [ ] CVE data import and synchronization with point-in-time context
- [ ] Compliance assessment relative to available updates (not public state)
- [ ] Gap analysis reporting (what patches exist publicly but are not yet transferred)
- [ ] Transfer history and audit trail
- [ ] Multi-OS repository support (serve updates for multiple OS families)
- [ ] Repository statistics and dashboard
- [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~5,000 lines

#### 11.3 Air-Gapped Compliance Context

**Features:**
- [ ] Point-in-time vulnerability context (CVE data as of last media transfer)
- [ ] Compliance scoring relative to available private-side patches
- [ ] Reporting that distinguishes between "patch available but not applied" vs "patch not yet transferred"
- [ ] Transfer freshness indicators (how old is the latest media import)
- [ ] Risk assessment that accounts for the air-gap transfer cadence
- [ ] Integration with existing compliance_engine and vuln_engine modules

### Migration Steps

1. [ ] Create `module-source/airgap_collector_engine/` structure
2. [ ] Create `airgap_collector_engine.pyx` Cython module
3. [ ] Create `module-source/airgap_repository_engine/` structure
4. [ ] Create `airgap_repository_engine.pyx` Cython module
5. [ ] Create frontend plugin bundles for both modules
6. [ ] Update documentation with air-gapped deployment guide
7. [ ] i18n/l10n for all 14 languages

### Deliverables

- [ ] 2 new Pro+ modules (airgap_collector_engine, airgap_repository_engine)
- [ ] Air-gapped deployment guide
- [ ] Optical media transfer procedures documentation
- [ ] Integration tests for collection and ingestion workflows

### Exit Criteria

- Public-side collection captures all configured OS updates and CVE data
- Optical media generation and integrity verification working
- Private-side ingestion creates functional package repositories
- Managed hosts can install updates from private repository
- Vulnerability scanning works with point-in-time CVE context
- Compliance reporting accounts for air-gap transfer state

---

## Phase 12: Multi-Site Federation (Enterprise)

**Target Release:** v2.4.0.0
**Focus:** Hierarchical multi-server architecture for geographically distributed enterprise deployments

### Overview

Large enterprises operate data centers, branch offices, and cloud regions across multiple geographic locations. Managing thousands of hosts from a single SysManage server creates scalability bottlenecks, network latency issues, and single-point-of-failure risk. This phase introduces a federation architecture where multiple subordinate SysManage servers operate independently at each site while a coordinating Federation Controller aggregates data and dispatches commands across the entire enterprise.

### Architecture

**Federation Controller ("Coordinator")**
- Sits at the top of the hierarchy, providing a unified enterprise-wide view
- Does NOT communicate directly with agents — all agent communication flows through subordinate site servers
- Aggregates host inventory, health status, compliance posture, and vulnerability data from all subordinate servers
- Provides rollup reporting and dashboards across all sites (total hosts, compliance scores, patch status, etc.)
- Dispatches commands (reboot, update, deploy, etc.) to the appropriate subordinate server, which then forwards them to the target agent
- Manages enterprise-wide policies (update profiles, firewall roles, compliance baselines) and pushes them to subordinates
- Handles user authentication centrally — users log in to the coordinator and can view/manage any site they have permissions for
- Maintains its own PostgreSQL database with federated metadata (site registry, rollup statistics, policy definitions)
- Can itself be made highly available with standard PostgreSQL replication and a load balancer

**Subordinate Site Server ("Site Server")**
- A standard SysManage server instance running at each physical location
- Manages agents at its site using the normal WebSocket communication
- Operates autonomously if the coordinator is unreachable (agents continue reporting, commands continue working locally)
- Periodically syncs summary data upstream to the coordinator (host counts, compliance scores, alert summaries)
- Receives policy pushes and dispatched commands from the coordinator
- Maintains its own full database — the coordinator does NOT need direct database access to subordinate servers
- Registered with the coordinator via a secure enrollment process (mutual TLS + enrollment token)

### Communication Model

- **Coordinator ↔ Site Server:** REST API over mutual TLS, with periodic sync intervals (configurable, default 5 minutes)
- **Site Server ↔ Agents:** Existing WebSocket protocol (unchanged)
- **Coordinator → Agent:** Not direct — coordinator sends command to site server via REST, site server queues it for the agent
- **Data flow upstream:** Site servers push summary/rollup data to coordinator on a schedule
- **Data flow downstream:** Coordinator pushes policy changes and dispatched commands to site servers
- **Offline resilience:** Site servers cache pending upstream syncs and replay them when connectivity is restored

### Modules

#### 12.1 federation_controller_engine (Enterprise)

**Features:**
- [ ] Site server registry (add, remove, suspend, monitor subordinate servers)
- [ ] Secure site enrollment workflow (enrollment token + mutual TLS certificate exchange)
- [ ] Site server health monitoring (last sync time, connectivity status, host count)
- [ ] Enterprise-wide host inventory rollup (aggregated from all sites)
- [ ] Enterprise-wide dashboard with per-site breakdown
- [ ] Cross-site search (find a host by name, IP, or tag across all sites)
- [ ] Rollup compliance reporting (aggregate CIS/STIG scores across sites)
- [ ] Rollup vulnerability reporting (aggregate CVE exposure across sites)
- [ ] Rollup alerting (enterprise-wide alert rules that trigger on cross-site conditions)
- [ ] Enterprise-wide update policy management (define policies centrally, push to sites)
- [ ] Enterprise-wide firewall role management (define roles centrally, push to sites)
- [ ] Command dispatch to subordinate servers (reboot, update, deploy, script execution)
- [ ] Batch command dispatch (target hosts across multiple sites in a single operation)
- [ ] Conflict resolution for policy changes (coordinator wins, with audit trail)
- [ ] Federation audit log (all cross-site operations logged centrally)
- [ ] Site server version tracking (ensure all sites run compatible SysManage versions)
- [ ] Configurable sync intervals per site (bandwidth-constrained sites can sync less frequently)
- [ ] Data retention policies for rollup data
- [ ] REST API for all federation operations (enabling automation and CI/CD integration)
- [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~8,000 lines

#### 12.2 federation_site_engine (Enterprise)

**Features:**
- [ ] Coordinator enrollment and registration (exchange TLS certificates, receive site ID)
- [ ] Upstream data sync (push host summaries, compliance scores, alert summaries to coordinator)
- [ ] Downstream policy sync (receive and apply update policies, firewall roles, compliance baselines)
- [ ] Command reception from coordinator (receive dispatched commands and queue for local agents)
- [ ] Command result reporting (send command outcomes back to coordinator)
- [ ] Offline queue for upstream data (buffer syncs when coordinator is unreachable)
- [ ] Offline queue replay with deduplication when connectivity is restored
- [ ] Local autonomy mode (full local operation continues when coordinator is unavailable)
- [ ] Sync status dashboard (show last sync time, pending items, connectivity health)
- [ ] Coordinator connection health monitoring with automatic reconnection
- [ ] Site metadata reporting (site name, location, host count, server version)
- [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~5,000 lines

#### 12.3 Federation Frontend

**Features:**
- [ ] Enterprise dashboard with site map/list view showing all subordinate sites
- [ ] Per-site drill-down (click a site to see its hosts, compliance, alerts)
- [ ] Cross-site host search and filtering
- [ ] Enterprise-wide compliance and vulnerability rollup charts
- [ ] Policy management UI (create/edit/push policies to sites)
- [ ] Command dispatch UI (select hosts across sites, dispatch commands)
- [ ] Site server management UI (add/remove/monitor sites)
- [ ] Federation audit log viewer
- [ ] Site connectivity status indicators
- [ ] Sync status and history per site

**Estimated Size:** ~4,000 lines (frontend plugin bundle)

#### 12.4 Database Schema

**Coordinator-side tables:**
- [ ] `federation_sites` — registered subordinate servers (id, name, location, url, tls_cert, status, last_sync)
- [ ] `federation_host_rollup` — aggregated host data from all sites (site_id, host_count, active_count, os_breakdown)
- [ ] `federation_compliance_rollup` — aggregated compliance scores per site
- [ ] `federation_vulnerability_rollup` — aggregated CVE exposure per site
- [ ] `federation_policies` — centrally defined policies (update profiles, firewall roles)
- [ ] `federation_policy_assignments` — which policies are pushed to which sites
- [ ] `federation_dispatched_commands` — commands sent from coordinator to sites (tracking status)
- [ ] `federation_audit_log` — all federation operations

**Site-side tables:**
- [ ] `federation_coordinator` — coordinator connection details (url, tls_cert, site_id, enrollment_status)
- [ ] `federation_sync_queue` — pending upstream data pushes
- [ ] `federation_received_policies` — policies received from coordinator
- [ ] `federation_received_commands` — commands received from coordinator

**Estimated Size:** ~1,000 lines (Alembic migrations, idempotent, sqlite + postgresql compatible)

### Security Considerations

- All coordinator ↔ site server communication uses mutual TLS (both sides present certificates)
- Enrollment tokens are single-use and time-limited
- Site servers authenticate to the coordinator using their enrolled TLS certificate
- The coordinator never stores agent credentials — it cannot communicate with agents directly
- Command dispatch is audited on both coordinator and site server
- RBAC extends to federation: users can be granted access to specific sites or all sites
- Site servers can be suspended from the coordinator without affecting local operations

### Scalability Considerations

- Each site server handles its own agent WebSocket connections (horizontal scaling by adding sites)
- The coordinator only processes summary/rollup data, not raw agent telemetry
- Sync intervals are configurable to manage bandwidth (remote offices with slow links can sync less often)
- Rollup data is pre-aggregated at the site level before being sent to the coordinator
- The coordinator database grows linearly with the number of sites, not the number of hosts
- Target: support up to 100 subordinate sites, each managing up to 10,000 hosts (1M hosts enterprise-wide)

### Migration Steps

1. [ ] Create `module-source/federation_controller_engine/` structure
2. [ ] Create `federation_controller_engine.pyx` Cython module
3. [ ] Create `module-source/federation_site_engine/` structure
4. [ ] Create `federation_site_engine.pyx` Cython module
5. [ ] Create coordinator database migrations (idempotent, sqlite + postgresql)
6. [ ] Create site-side database migrations (idempotent, sqlite + postgresql)
7. [ ] Create frontend plugin bundle for federation UI
8. [ ] Implement mutual TLS enrollment workflow
9. [ ] Implement upstream/downstream sync protocol
10. [ ] Implement command dispatch and result tracking
11. [ ] Create federation deployment guide
12. [ ] i18n/l10n for all 14 languages

### Deliverables

- [ ] 2 new Pro+ modules (federation_controller_engine, federation_site_engine)
- [ ] Federation frontend plugin bundle
- [ ] Database migrations for coordinator and site schemas
- [ ] Federation deployment and operations guide
- [ ] Mutual TLS enrollment procedures documentation
- [ ] Integration tests for sync, dispatch, and offline resilience
- [ ] Performance tests validating 100-site / 1M-host target

### Exit Criteria

- Coordinator can enroll and monitor multiple subordinate site servers
- Host inventory, compliance, and vulnerability data rolls up correctly across all sites
- Enterprise-wide dashboards and reports display accurate cross-site data
- Commands dispatched from coordinator reach target agents via the correct site server
- Site servers continue full local operation when coordinator is unreachable
- Pending upstream syncs are replayed correctly when connectivity is restored
- Policy changes pushed from coordinator are applied at subordinate sites
- All federation operations are audited on both sides
- RBAC correctly restricts per-site access for federated users

---

## Phase 13: Enterprise GA (v3.0.0.0)

**Target Release:** v3.0.0.0
**Focus:** Multi-tenancy, API completeness, GA release

### Features

#### 12.1 Multi-Tenancy (Enterprise)

- [ ] Account model with isolation
- [ ] Account switching for users with multiple accounts
- [ ] Per-account settings and limits
- [ ] Data isolation verification

#### 12.2 API Completeness

- [ ] Audit all features for missing endpoints
- [ ] API versioning (/api/v1/, /api/v2/)
- [ ] ApiKey model for automation
- [ ] Rate limiting middleware
- [ ] Complete OpenAPI documentation

#### 12.3 Additional Polish Items

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
| 0 | v1.1.0.0 | Current | Core platform + virtualization code (moving to Pro+) |
| 1 | v1.2.0.0 | Stabilization | Test coverage, SonarQube cleanup |
| 2 | v1.3.0.0 | Pro+ Professional | reporting, audit, secrets, container (LXD/WSL) + ~3,504 lines agent migration |
| 3 | v1.4.0.0 | Pro+ Enterprise 1 | AV management, firewall orchestration + ~13,800 lines agent migration |
| 4 | v1.5.0.0 | Stabilization | Pro+ integration testing, license verification |
| 5 | v1.6.0.0 | Pro+ Enterprise 2 | automation, fleet engines + ~328 lines agent migration |
| 6 | v1.7.0.0 | Stabilization | Performance baseline, i18n audit |
| 7 | v1.8.0.0 | Stabilization RC1 | Integration tests, load tests, security |
| 8 | **v2.0.0.0** | Foundation | Access groups, update profiles, compliance, agent generic handlers |
| 9 | v2.1.0.0 | Stabilization RC2 | Final polish, docs complete |
| 10 | v2.2.0.0 | Pro+ Enterprise 3 | virtualization, observability, MFA + ~24,489 lines agent migration |
| 11 | v2.3.0.0 | Air-Gapped Support | Dual-server architecture, optical media transfer, offline CVE |
| 12 | v2.4.0.0 | Multi-Site Federation | Coordinator + site servers, rollup reporting, command dispatch |
| 13 | **v3.0.0.0** | Enterprise GA | Multi-tenancy, API complete, full feature set |

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

| Module | Tier | Phase | Server Lines | Agent Migration | Total Est. | Priority |
|--------|------|-------|-------------|-----------------|------------|----------|
| reporting_engine | Professional | 2 | ~1,500 | — | ~1,500 | High |
| audit_engine | Professional | 2 | ~2,000 | — | ~2,000 | High |
| secrets_engine | Professional | 2 | ~800 | ~509 | ~1,300 | High |
| container_engine (LXD, WSL) | Professional | 2 | ~700 | ~2,995 | ~3,700 | High |
| av_management_engine | Enterprise | 3 | ~700 | ~5,800 | ~6,500 | High |
| firewall_orchestration_engine | Enterprise | 3 | ~1,500 | ~8,000 | ~9,500 | High |
| automation_engine | Enterprise | 5 | ~2,000 | ~328 | ~2,300 | High |
| fleet_engine | Enterprise | 5 | ~1,500 | — | ~1,500 | High |
| virtualization_engine (KVM, bhyve, VMM) | Enterprise | 10 | ~1,850 | ~22,153 | ~24,000 | Medium |
| observability_engine | Enterprise | 10 | ~4,000 | ~2,336 | ~6,300 | Medium |
| airgap_collector_engine | Enterprise | 11 | ~4,000 | — | ~4,000 | Medium |
| airgap_repository_engine | Enterprise | 11 | ~5,000 | — | ~5,000 | Medium |
| federation_controller_engine | Enterprise | 12 | ~8,000 | — | ~8,000 | Medium |
| federation_site_engine | Enterprise | 12 | ~5,000 | — | ~5,000 | Medium |
| Agent generic handlers | Open Source | 8 | — | ~1,500 (new) | ~1,500 | High |

### Virtualization Tiering

| Feature | Tier | Description |
|---------|------|-------------|
| VM/container listing (read-only) | Open Source | View existing VMs and status |
| LXD container management | Professional | Create/manage LXD containers (Ubuntu) |
| WSL instance management | Professional | Create/manage WSL instances (Windows) |
| KVM/QEMU VM management | Enterprise | Full VM lifecycle on Linux |
| bhyve VM management | Enterprise | Full VM lifecycle on FreeBSD |
| VMM/vmd VM management | Enterprise | Full VM lifecycle on OpenBSD |
| Cloud-init provisioning | Enterprise | Automated guest OS setup |
| Multi-hypervisor networking | Enterprise | NAT, bridge, host-only modes |

### Total Migration Estimate

- **Professional Tier:** ~8,500 lines (Phase 2: reporting + audit + secrets + container, includes ~3,504 from agent)
- **Enterprise Tier - Part 1:** ~16,000 lines (Phase 3: AV + firewall, includes ~13,800 from agent)
- **Enterprise Tier - Part 2:** ~3,800 lines (Phase 5: automation + fleet, includes ~328 from agent)
- **Enterprise Tier - Part 3:** ~30,300 lines (Phase 10: virtualization + observability, includes ~24,489 from agent)
- **Air-Gapped Support:** ~9,000 lines (Phase 11: collector + repository)
- **Multi-Site Federation:** ~17,000 lines (Phase 12: controller + site engine + frontend plugin + migrations)
- **Open Source Agent Handlers:** ~1,500 lines (Phase 8: generic deployment infrastructure)

**Grand Total:** ~86,100 lines of Pro+ code + ~1,500 lines open source agent infrastructure

**Agent Code Migration Summary:** ~42,121 lines of config construction, VM management,
deployment, and provisioning code will be migrated from the agent to server-side Cython
modules. The agent retains ~6,231 lines of open source operations (package management,
updates, user management, system control, repositories, Ubuntu Pro) plus gains ~1,500 lines
of new generic deployment handlers.

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

### Quality Metrics (Final Targets by v3.0.0.0)

- **Test Coverage:** Backend ≥80%, Agent ≥80%, Pro+ ≥85%
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

*Document Version: 1.1*
*Last Updated: February 2026*
*Current Product Version: v1.1.0.0*
*Based on: docs/planning/FEATURES-TODO.md, docs/planning/FEATURE-TIERING-ANALYSIS.md, docs/planning/VMM-VMD.md, docs/planning/BHYVE.md, docs/planning/KVM-QEMU.md*
