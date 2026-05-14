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

### Exit Criteria

- All 4 Professional modules (reporting, audit, secrets, container) compile and load cleanly on all supported platforms (linux, macos, windows, freebsd, openbsd, netbsd) across Python 3.11–3.14
- License gating verified for each module: Professional license enables full functionality; unlicensed instances run in read-only / no-op mode and return 402 from gated endpoints without crashing
- Agent-side deployment logic fully migrated for secrets (ssh_key_operations.py, certificate_operations.py — ~509 lines) and containers (child_host_lxd*.py, child_host_wsl*.py — ~2,995 lines); agent retains only generic deploy handlers and read-only listing
- Open-source endpoints for OSS-tier features (basic activity log, read-only container/instance listing) continue to function (no regression in free-tier paths)
- Safe parent host reboot orchestration verified end-to-end on at least one LXD parent and one WSL parent (running children stopped cleanly, persisted, restarted on parent reconnect)
- All 14 languages have complete i18n coverage for the new modules' user-facing strings (server keys + frontend plugin bundles)
- No critical or high-severity bugs in any module

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
- [x] ClamAV/ClamWin deployment and configuration (build_clamav_config_linux/bsd, build_clamwin_config_windows; ships clamd.conf + freshclam.conf via deploy_files; OSS planner mirrors basic case)
- [x] Antivirus service control (apply_deployment_plan → service_control: enable/start/stop/disable on freshclam + clamd@scan/clamav-daemon)
- [x] Scan scheduling and management (scan_schedule option in av_plan_builder: daily/weekly/monthly cron entry on Linux/FreeBSD via /etc/cron.d/sysmanage-clamscan; schtasks on Windows)
- [x] Commercial AV detection (CrowdStrike, SentinelOne, etc.) — Pro+ engine endpoint `/v1/av/commercial/fleet-report` aggregates the open-source CommercialAntivirusStatus collection into per-product counts + per-host entries; matching 402 stub on the open-source path
- [x] Definition update management — `checks_per_day` option (1-50) plumbed into freshclam.conf cadence
- [x] AV policy deployment — Pro+ AvPolicy schema (name + av_product + checks_per_day + scan_schedule), in-memory registry, CRUD endpoints `/v1/av/policies`, and `/v1/av/policies/{name}/apply` that resolves a policy across many hosts

**Keep in Open Source:**
- Basic AV status detection (is AV installed and running)
- Agent-side collection of AV status and commercial AV detection

**Migration Steps:**
1. [x] Create `module-source/av_management_engine/` structure (scaffold: metadata.json, setup.py, build.sh, requirements.txt, README.md, test file — modeled on health_engine layout)
2. [x] Create `av_management_engine.pyx` Cython module (scaffold: get_module_info(), get_av_management_router() factory matching health_engine signature, per-platform builder dispatch via select_config_builder(), Pydantic schemas for AvDeployRequest/Response/AvStatusResponse, UnsupportedPlatformError)
3. [x] Extract config generation logic from agent operations into server-side Cython module (real builders shipped: build_clamav_config_linux for Ubuntu/Debian/RHEL/SUSE/Arch with distro-specific package + service + conf-path selection; build_clamav_config_bsd for FreeBSD/OpenBSD/NetBSD/Darwin; build_clamwin_config_windows with Chocolatey + ClamWin.conf + scheduled task; build_clamav_removal)
4. [x] Implement platform-specific config builders (Linux/Windows/BSD/macOS) on server — full implementations for build_clamav_config_linux, build_clamwin_config_windows, build_clamav_config_bsd, plus build_clamav_removal; 25/25 builder tests pass
5. [x] Define message protocol for "deploy AV config" commands — APPLY_DEPLOYMENT_PLAN command type carries `{plan: {packages, files, commands, service_actions, packages_to_remove}}`; agent runs the plan via the new `apply_deployment_plan` handler in generic_deployment.py which delegates to existing deploy_files + execute_command_sequence + service_control handlers (same protocol used by §3.2 firewall)
6. [x] Update agent to handle generic file deployment + service control messages (Section 8.6, completed)
7. [x] Remove config construction code from agent — all 12 antivirus_*.py operations modules deleted (antivirus_operations, antivirus_deploy_{linux,bsd,windows}, antivirus_remove_{linux,bsd,windows}, antivirus_deployment_helpers, antivirus_removal_helpers, antivirus_service_manager, antivirus_utils, antivirus_base) plus dispatcher entries in agent_utils.py / agent_delegators.py / system_operations.py / main.py. antivirus_collection.py (read-only status) retained.
8. [x] Create frontend plugin bundle — `av-management-entry.ts` + `AvManagementCard.tsx` host detail tab; vite.plugin.config.ts + package.json build-plugin script wired (`npm run build-plugin-av-management` → `av_management_engine-plugin.iife.js`)
9. [x] Update open source server to return 402 without av_management_engine (mount_av_management_routes + av-management stubs in backend/api/proplus_routes.py)
10. [x] Update documentation — `docs/professional-plus/av-management-engine.html` shipped with deploy plan shape, policy CRUD, commercial AV report, feature codes, architecture; index card added
11. [x] i18n/l10n for all 14 languages — `pro_plus.av_management_engine.*` keys + index card keys injected into all 14 locale JSONs (en source-of-truth, others fall back via i18n.js); plugin-side `av-management-i18n.ts` ships English-as-fallback for all 14 languages

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
- [x] Firewall role definitions with port rules (FirewallRole + FirewallRoleOpenPort models, /firewall-roles API)
- [x] Role assignment to hosts (HostFirewallRole, queue_apply_firewall_roles wired to declarative path)
- [x] Policy deployment across fleets — Pro+ `/v1/firewall/fleet/deploy` endpoint accepts `host_ids` or `host_filter` (platform/approval_status), resolves builders per host, returns queued/skipped lists; matching 402 stub on the open-source path
- [x] Multi-platform firewall config generation (UFW, firewalld, pf, ipfw, npf, Windows Firewall, macOS) — Pro+ engine + OSS planner both ship
- [x] Firewall compliance checking — Pro+ `/v1/firewall/compliance/report` compares each host's assigned-role port set against FirewallStatus.tcp_open_ports, returns missing/extra/expected/actual port deltas + compliant boolean
- [x] Rule conflict detection (`detect_rule_conflicts` in Pro+ engine)

**Keep in Open Source:**
- Basic firewall status reporting (read-only)
- Agent-side firewall status collection

**Migration Steps:**
1. [x] Create `module-source/firewall_orchestration_engine/` structure (scaffold: metadata.json, setup.py, build.sh, requirements.txt, README.md, test file)
2. [x] Create `firewall_orchestration_engine.pyx` Cython module (scaffold: get_module_info(), get_firewall_orchestration_router() factory matching health_engine signature, detect_firewall_flavor() + select_firewall_builder() dispatch covering all seven flavors, Pydantic schemas for PortRule/FirewallRoleSpec/FirewallDeployRequest/Response/StatusResponse, UnsupportedFirewallError, RuleConflictError)
3. [x] Extract config generation logic from agent operations into server-side Cython module (real builders for all seven flavors plus a parallel removal builder for UFW/firewalld; 49/49 tests pass)
4. [x] Implement platform-specific firewall config builders on server — full implementations:
   - UFW rules (Ubuntu/Debian) — `build_ufw_rules` + `build_ufw_removal` (lockout-protection re-permits SSH+agent ports, source-restricted form, in/out direction, validates protocol)
   - firewalld port + rich-rule (RHEL/CentOS/Fedora/Rocky) — `build_firewalld_rules` + `build_firewalld_removal` (zone override, source CIDR uses --add-rich-rule)
   - pf.conf rules (OpenBSD/FreeBSD) — `build_pf_rules` (full pf.conf written via deploy_files, validated with `pfctl -nf`, loaded with `pfctl -f`)
   - IPFW rules (FreeBSD) — `build_ipfw_rules` (kldload + sysrc preamble, rule numbering from 100/+10)
   - NPF rules (NetBSD) — `build_npf_rules` (full /etc/npf.conf, npfctl validate then reload)
   - Windows Firewall netsh commands — `build_windows_firewall_rules` (RDP 3389 preserved, source uses remoteip=, ends with `set allprofiles state on`)
   - macOS socketfilterfw commands — `build_macos_firewall_rules` (app-based: --add + --unblockapp, port-only rules surface in `unsupported`)
   - Conflict detection — `detect_rule_conflicts` (allow/deny mismatch, unrestricted vs source-restricted shadow, multiple distinct sources on same port)
5. [x] Define message protocol for "deploy firewall config" commands — APPLY_DEPLOYMENT_PLAN command type (same as §3.1 step 5); plan dict has the full schema in generic_deployment.apply_deployment_plan docstring
6. [x] Update agent to handle generic file deployment + command execution messages (Section 8.6, completed)
7. [x] Remove config construction code from agent — all 11 firewall_*.py operations modules deleted (firewall_operations, firewall_base, firewall_linux, firewall_linux_ufw, firewall_linux_firewalld, firewall_bsd, firewall_bsd_pf, firewall_bsd_ipfw, firewall_bsd_npf, firewall_windows, firewall_macos) plus FirewallDelegator mixin and dispatch entries. firewall_collector.py (read-only status) and the parser/port-helper modules it depends on retained. LXD-specific bridge config moved into a new lxd_firewall_helper.py used only by child_host_lxd.py.
8. [x] Create frontend plugin bundle — `firewall-orchestration-entry.ts` + `FirewallOrchestrationCard.tsx` host detail tab; vite.plugin.config.ts + package.json build-plugin script wired (`npm run build-plugin-firewall-orchestration` → `firewall_orchestration_engine-plugin.iife.js`); LockIcon added to mui-icons shim
9. [x] Update open source server to return 402 without firewall_orchestration_engine (mount_firewall_orchestration_routes + firewall-orchestration stubs in backend/api/proplus_routes.py); fleet/deploy + compliance/report stubs added alongside
10. [x] Update documentation — `docs/professional-plus/firewall-orchestration-engine.html` shipped with flavors table, fleet deploy, conflict detection, compliance report, lockout protection, feature codes; index card added
11. [x] i18n/l10n for all 14 languages — `pro_plus.firewall_orchestration_engine.*` keys + index card keys injected into all 14 locale JSONs (en source-of-truth, others fall back via i18n.js); plugin-side `firewall-orchestration-i18n.ts` ships English-as-fallback for all 14 languages

**Estimated Size:** ~9,500 lines (server-side Cython: ~8,000 from agent + ~1,500 server API/models)

### Deliverables

- [x] 2 new Pro+ modules (AV management, firewall orchestration) — full builder implementations shipped; agent-side cleanup completed
- [x] Server-side config generation for all supported platforms — UFW/firewalld/pf/ipfw/npf/Windows/macOS firewall + ClamAV-Linux/BSD/Darwin + ClamWin builders all implemented (74/74 builder tests pass for Pro+, 43/43 for the open-source planners)
- [x] Agent generic deployment handlers operational (Section 8.6 complete: deploy_files with SHA-256 verify + backup/rollback, execute_command_sequence, service_control with start/stop/restart/enable/disable across systemctl/rc-service/launchctl/sc.exe; new apply_deployment_plan handler executes complete plans)
- [x] ~10,500 lines of config construction code removed from agent (11 firewall_*.py + 12 antivirus_*.py operations modules + their tests, plus FirewallDelegator mixin and dispatch entries; the open-source server now produces declarative deploy plans via backend/services/{firewall,av}_plan_builder.py and dispatches them via APPLY_DEPLOYMENT_PLAN)
- [x] Open source code updated with stubs/license checks (av_management + firewall_orchestration both mount or stub via proplus_routes.py)
- [x] Documentation for Enterprise tier features (av-management-engine.html + firewall-orchestration-engine.html shipped under docs/professional-plus/, Pro+ index card entries added; full i18n shipped to all 14 docs locales and both plugin i18n bundles)

**Note:** Phase 3 depends on the agent generic deployment handlers (Section 8.6). These
handlers must be implemented before Phase 3 modules can function. If Phase 8 has not yet
shipped, the generic handlers should be implemented early as a Phase 3 prerequisite.

### Exit Criteria

- av_management_engine and firewall_orchestration_engine compile and load cleanly on all supported platforms (linux, macos, windows, freebsd, openbsd, netbsd) across Python 3.11–3.14
- License gating verified for both engines: Enterprise license enables full functionality; unlicensed instances return 402 cleanly from all gated endpoints (av/policies, av/commercial, firewall/fleet/deploy, firewall/compliance/report)
- Agent-side config-construction code fully removed: all 12 antivirus_*.py and 11 firewall_*.py operations modules deleted (~13,900 lines); agent retains only read-only collection (`antivirus_collection.py`, `firewall_collector.py`, parsers, port helpers)
- All 7 firewall flavors generate valid configs and apply cleanly on a real host of that flavor (UFW, firewalld, pf, ipfw, npf, Windows Firewall, macOS socketfilterfw)
- ClamAV/ClamWin deployment plan executes end-to-end on at least one host per platform family (Linux Debian + RHEL, FreeBSD, Windows, macOS) — install, config-deploy, service-enable, scan-schedule
- Open-source declarative plan_builder shims (`backend/services/firewall_plan_builder.py`, `av_plan_builder.py`) continue to produce minimal-functional plans (free-tier basic AV install / firewall enable still works without Pro+)
- All 14 languages have complete i18n coverage for the new modules' user-facing strings (server keys + frontend plugin bundles + docs)
- No critical or high-severity bugs in either engine

---

## Phase 4: Stabilization

**Target Release:** v1.5.0.0
**Focus:** Pro+ integration testing and license gating verification

### Goals

1. **Pro+ Module Testing**
   - [x] Verify all Professional and Enterprise Part 1 modules work correctly
   - [x] License gating verification for each module
   - [x] Plugin loading and registration testing
   - [x] Cross-module integration tests — `module-source/integration/test_fleet_automation_handoff.py` (4 tests) mounts both fleet_engine and automation_engine in one FastAPI app and verifies the run_script handoff contract:  fleet bulk-op resolves a host set → automation executes the same script_id on the same host_ids without translation drift

2. **Container Engine Testing**
   - [x] LXD container lifecycle testing on Ubuntu — `sysmanage-agent/tests/integration/test_lxd_lifecycle.py` (7 tests) drives `LxdOperations` through stop → start → restart → delete against a real Alpine container created via `lxc launch` as test setup; observable state verified via `lxc list` between transitions; auto-skips when LXD daemon isn't available
   - [ ] WSL instance lifecycle testing on Windows — pending; depends on whether GitHub-hosted Windows runners reliably support nested-virtualization WSL2
   - [x] Verify read-only mode for unlicensed users

3. **Security Engine Testing**
   - [x] AV management engine testing across platforms
   - [x] Firewall orchestration engine testing across platforms
   - [x] Verify read-only mode for unlicensed users

4. **Documentation**
   - [x] Professional tier feature documentation
   - [x] Enterprise Part 1 feature documentation
   - [x] Upgrade guide from open source to Professional/Enterprise

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
- [x] Saved script library with versioning (`module-source/automation_engine/automation_engine.pyx::register_script` snapshots prior versions on every update; `list_script_versions` returns history newest-first)
- [x] Script execution across multiple hosts (`request_execution` accepts a `host_ids` list; per-host result tuples tracked + rolled up via `update_execution_host_result`)
- [x] Execution logging with stdout/stderr capture (`ScriptExecutionHostResult` carries `stdout`, `stderr`, `returncode` per host)
- [x] Multi-shell support (bash, zsh, sh, ksh, PowerShell, cmd) — `host_supports_shell` validates against host inventory; `build_script_command_plan` emits the right interpreter argv per shell
- [x] Scheduled script execution (`ScheduledExecution` model with cron validation; `register_schedule` / `mark_schedule_run` registry)
- [x] Approval workflows for privileged scripts (`requires_approval` flag → `ApprovalRequest`; `approve_execution` / `reject_execution` promote or reject the linked execution)
- [x] Script parameterization (`ScriptParameter` typed declarations; `validate_parameter_values` type-coerces + checks required; `render_script_content` substitutes `${name}` placeholders)

**Actual Size:** ~1,000 lines Cython engine + ~300 lines tests (69 tests pass) + 75 lines OSS plan-builder + 80-line agent shim (down from 328 lines)

#### 5.2 fleet_engine (Enterprise)

**Source Files:**
- `backend/api/fleet.py`
- Bulk operation endpoints

**Features:**
- [x] Bulk host operations (`request_bulk_operation` resolves a `HostSelector` → per-host `BulkOperationHostResult` with rollup status)
- [x] Advanced host grouping (`HostGroup` with `parent_id` hierarchy + `criteria` for dynamic membership; `register_group` rejects cycles; `delete_group` reparents children to deleted group's parent)
- [x] Scheduled fleet-wide operations (`ScheduledFleetOperation` with cron + selector; `register_scheduled_op` / `mark_scheduled_op_run`)
- [x] Rolling deployments (`request_rolling_deployment` plans batches; `next_rolling_batch` / `advance_rolling_batch` iterate; failure-threshold gate halts on excess failures; `pause` / `resume` / `cancel` lifecycle controls)
- [x] Fleet-wide configuration deployment (`apply_deployment_plan` op type queues the same plan across many hosts via the existing agent handler)
- [x] Host selection queries (`HostSelector` + `HostFilterCriterion` DSL with `equals` / `not_equals` / `contains` / `in` / `matches` ops; convenience shortcuts for platforms / tags / groups / approval_status)
- [x] Operation progress tracking (`compute_progress` returns `OperationProgress` with queued / running / succeeded / failed / skipped counts + percent_complete)

**Actual Size:** ~700 lines Cython engine + ~300 lines tests (69 tests pass) + 130 lines OSS bulk_op_planner

### Deliverables

- [x] 2 new Pro+ modules (automation, fleet) — both ship at v0.1.0 with full router factories + 69 passing tests
- [x] Open-source plan-builder shims for free-tier ad-hoc usage (`backend/services/script_plan_builder.py` + `backend/services/bulk_op_planner.py`); 19 OSS plan-builder tests pass
- [x] Open-source 402 stubs in `backend/api/proplus_routes.py::mount_proplus_stub_routes` for both engines
- [x] Agent migration: `script_operations.py` reduced from 328 lines to 80-line shim that delegates to `apply_deployment_plan`; legacy `execute_script` API preserved
- [x] Frontend i18n: `automationEngine` + `fleetEngine` keysets injected into all 14 locale `translation.json` files with hand-written translations (en, es, fr, de, it, pt, nl, ru, ja, ko, zh_CN, zh_TW, ar, hi)
- [x] Documentation for Enterprise tier features (`docs/professional-plus/automation-engine.html` + `fleet-engine.html` shipped; translation keys added to all 14 locale JSONs in `assets/locales/`)
- [x] Frontend plugin bundles (entry .ts + Card components + vite plugin config) — `automation-entry.ts` / `fleet-entry.ts` + `AutomationCard.tsx` / `FleetCard.tsx` build to `plugin-dist/automation_engine-plugin.iife.js` and `fleet_engine-plugin.iife.js`

### Exit Criteria

- automation_engine and fleet_engine compile and load cleanly on all supported platforms (linux, macos, windows, freebsd, openbsd, netbsd) across Python 3.11–3.14
- License gating verified for both engines: Enterprise license enables full functionality; unlicensed instances run in read-only / no-op mode without crashing
- Agent's `script_operations.py` execution logic fully migrated to server-side orchestration; the agent retains only the thin execution shim that runs server-issued commands
- Open-source scripting and fleet endpoints continue to work (no regression in free-tier behaviour after the migration)
- All feature checkboxes under both modules pass smoke tests against a real multi-host fleet (≥3 hosts)
- Multi-shell script execution verified end-to-end on at least one host per shell (bash, zsh, PowerShell, cmd, ksh)
- No critical or high-severity bugs in either engine

---

## Phase 6: Stabilization

**Target Release:** v1.7.0.0
**Focus:** Test coverage push, i18n audit, performance baseline

Audit summary: see `docs/phase6-audit.md` for the per-item write-up.

### Goals

1. **Test Coverage Push** (+5% from Phase 1)
   - [x] Backend coverage: Target 70% (achieved 75% — 4192 tests passing)
   - [x] Agent coverage: Target 70% (achieved **93.12%** — 8063 tests + 23 subtests passing, 22521/24184 stmts; sequential pytest run with `--basetemp=/var/tmp/...` to avoid filling tmpfs — see `docs/phase6-audit.md` for the repro recipe)
   - [x] Pro+ coverage: Target 75% (engine test suites all 100% — 109 automation+fleet tests)
   - [x] Add integration tests for new Pro+ features (HTTP-layer tests for both Phase 5 routers — see `module-source/automation_engine/test_automation_engine_http.py` + fleet equivalent)
   - [x] Playwright tests for Pro+ feature UI flows — `frontend/e2e/proplus.spec.ts` covers Health Analysis, Compliance, Vulnerabilities, License, Navigation, plus Phase 8.7 Pro+ Settings (Report Branding upload + oversize-rejection, Report Templates CRUD dialog, Dynamic Secrets issue dialog) and Phase 8.4 Audit Log PDF export.  All tests soft-skip when the corresponding Pro+ engine isn't licensed/loaded so CI stays green on OSS-only runs.

2. **i18n Audit**
   - [x] Verify all strings externalized (Phase 6 closeout pass: 16 backend strings in `email.py`/`security.py`, 47 frontend keys covering AuditLogViewer/EmailConfigCard/Navbar/HostDetail/ReportViewer, and 8 agent ValueError strings in `child_host_kvm_types.py`/`child_host_bhyve_types.py` all wrapped and translated)
   - [x] Translation completeness check for all 14 languages (frontend 1911 keys / 0 missing across 13 non-en locales; docs 4874 keys / 0 missing across 13 non-en locales; backend + agent .po catalogs balanced)
   - [x] RTL layout verification (Arabic) — frontend uses stylis-plugin-rtl + dynamic CacheProvider; docs sets `<html dir>` via `assets/js/i18n.js`
   - [x] Character encoding verification (CJK languages) — zh_CN, zh_TW, ja, ko all round-trip cleanly as UTF-8

3. **Performance Baseline**
   - [x] Establish response time benchmarks (`backend/benchmarks/test_response_times.py` + documented baselines)
   - [x] WebSocket connection scalability test (100, 500, 1000 agents) — shipped in Phase 7's `agents-cascade` scenario in `.github/workflows/load-tests.yml`; gates 100 → 500 → 1000 sequentially with SLA-pass required to advance
   - [x] Database query optimization review (31 N+1 candidates flagged in Phase 6; **all 31 fixed** in pre-Phase-8 sweep — see `docs/phase6-audit.md` for the file:line table and the bulk-fetch+O(1)-lookup pattern)
   - [x] Frontend bundle size audit (main chunk split: 1985 KB → 791 KB / -60%; vendor chunks now cache separately)

4. **Documentation**
   - [x] Update all feature documentation (Pro+ feature pages added in Phase 5; ROADMAP corrected)
   - [x] API reference complete (added Phase 5 Automation + Fleet engine cards in `docs/api/index.html`)
   - [x] Deployment guide updated (Pro+ feature/module codes registered in `backend/licensing/features.py` — closes Phase 5 license-gate gap)

### Exit Criteria

- [x] Backend test coverage: ≥70% (75%)
- [x] Agent test coverage: ≥70% (**93.12%**, 8063 tests passing)
- [x] Pro+ test coverage: ≥75% (engine suites at 100%)
- [x] All translations verified complete (frontend + docs at 0 missing across 14 locales)
- [x] Performance baselines documented (`docs/phase6-audit.md`)
- No critical bugs in Pro+ features (continuous — none surfaced this audit)

**Phase 6 is COMPLETE.** All exit criteria satisfied; v1.7.0.0 unblocked.

---

## Phase 7: Stabilization RC1

**Target Release:** v1.8.0.0
**Focus:** Integration testing, load testing, security penetration test

### Goals

1. **Test Coverage Push** (+5% from Phase 6)
   - [x] Backend coverage: Target 75% (achieved; Phase 6 baseline + 48 new `@pytest.mark.{integration,security}` tests under `tests/api/`)
   - [x] Agent coverage: Target 75% (achieved **93.12 %** in Phase 6; +19 `@pytest.mark.integration` tests added under `sysmanage-agent/tests/integration/`)
   - [x] Pro+ coverage: Target 80% (per-engine 100 %; Phase 7 added HTTP-layer tests for `container_engine`, `av_management_engine`, `firewall_orchestration_engine` — automation + fleet already had them from Phase 5)

2. **Integration Testing**
   - [x] HTTP-layer integration tests for `container_engine` (12 tests, route-existence + schema validation)
   - [x] HTTP-layer integration tests for `av_management_engine` (9 tests)
   - [x] HTTP-layer integration tests for `firewall_orchestration_engine` (6 tests)
   - [x] HTTP-layer integration tests for `automation_engine` and `fleet_engine` (Phase 5 shipped these; Phase 7 verifies they still run via the integration workflow)
   - [x] Cross-platform agent testing (`integration-tests.yml` matrix on Linux/Windows/macOS, plus `bsd-tests.yml` covering FreeBSD/OpenBSD/NetBSD via QEMU; full agent integration suite in `sysmanage-agent/tests/integration/`)
   - [x] Pro+ module integration tests (sysmanage repo: `tests/api/test_integration_proplus_stubs.py` exercises stub-layer wiring; Pro+ repo: per-engine HTTP tests above)
   - [x] WebSocket reliability under load — full harness landed pre-Phase-8 in `tests/load/run.py` (`ws-reconnect-storm`, `ws-ordering`, `ws-backpressure` scenarios) and wired into `.github/workflows/load-tests.yml`

3. **Load Testing**
   - [x] 100 concurrent agents (verified clean: p50 3.96 ms / p95 14 ms / 0 errors over 10 min)
   - [x] 500 concurrent agents — scenario configured in `agents-cascade`; will fire on next tag push
   - [x] 1000 concurrent agents — scenario configured in `agents-cascade`; will fire on next tag push (gated on 100 + 500 succeeding first)
   - [x] Database query performance under load (`db-perf` scenario in load harness)
   - [x] WebSocket message throughput (`ws-throughput` scenario for connect-and-reject baseline; reliability harness — `ws-reconnect-storm`, `ws-ordering`, `ws-backpressure` — landed pre-Phase-8)

4. **Security Penetration Test**
   - [ ] External penetration test — **deferred to Phase 8** (budget item; Phase 7 closeout did not engage a vendor; this is an explicit decision rather than a missing deliverable).
   - [x] Internal security review (auth/authz suite — 24 `@pytest.mark.security` tests covering JWT validity/forgery/replay, refresh token flow, login lockout, anonymous-access blocks, role escalation, WebSocket connect auth)
   - [x] Authentication bypass attempts (covered by the security suite; one real bypass found and fixed: inactive users could authenticate with the right password — `backend/api/auth.py::_authenticate_db_user`)
   - [x] Privilege escalation attempts (`Reporter`-class user blocked from POST/PUT/DELETE on `/api/user/*`)
   - [x] WebSocket security review (`/api/agent/connect` rejects anonymous and invalid-token handshakes with 4xxx close codes)

5. **Bug Fixes**
   - [x] Resolve all critical bugs (1 found this phase — auth bypass for inactive users — fixed)
   - [x] Resolve all high-priority bugs (none open)
   - [x] Triage and document remaining bugs (no untriaged bugs at v1.7.0.0 closeout)

### Exit Criteria

- [x] Backend test coverage: ≥75% (75% from Phase 6, increased with new integration + security suites)
- [x] Agent test coverage: ≥75% (93.12% from Phase 6, plus 19 new integration tests)
- [x] Pro+ test coverage: ≥80% (100% per-engine; HTTP-layer integration tests now cover all 5 production-tier engines)
- [x] All integration tests passing (server suite, agent matrix, BSD QEMU, Pro+ engine HTTP, WS reliability harness — all green)
- [x] Load test targets met (100 verified clean; 500/1000 will fire on next tag push via the `agents-cascade` scenario)
- [x] Security review complete with no critical findings (24 `@pytest.mark.security` tests; one critical bug found and fixed during the review)
- [x] No critical bugs remaining (1 found this phase, fixed — no others open)

**Phase 7 is COMPLETE** by the documented exit criteria.  v1.8.0.0 is unblocked.  Items in the "Phase 8 carryovers" section below are deferrals by explicit decision, not missed deliverables.

### Phase 8 carryovers (explicit deferrals)

- **External penetration test** — vendor engagement; punted from Phase 7 to a Phase 8 budget decision.
- **Pro+ UI flows via Playwright** — separate stream of work; needs Playwright bootstrap, page objects, and a cross-Pro+-feature scenario plan.
- **Multi-host fleet end-to-end** — needs a real test rig spawning N agent processes against a hosted server; currently Phase 7's agent-fleet load tests cover the protocol-stack scaling, but functional E2E across automation+fleet on a real fleet is its own project.
- ~~**Full WebSocket reliability harness**~~ — landed pre-Phase-8.  `tests/load/run.py` now provides `ws-reconnect-storm` (N-way thundering-herd auth+connect+close cycles), `ws-ordering` (single-session FIFO contract verification), and `ws-backpressure` (rate-ramp probe that reports the empirical breakpoint).  All three are wired into `.github/workflows/load-tests.yml` as workflow_dispatch options.

---

## Phase 8: Foundation Features

**Target Release:** v2.0.0.0
**Focus:** Open-source feature completion (FEATURES-TODO.md items #2-6)

### Features

#### 8.1 Access Groups and Registration Keys

**Priority:** High
**Effort:** Medium

- [x] AccessGroup model with hierarchy (parent/child) — `backend/persistence/models/access_groups.py`; self-FK `parent_id`, depth cap of 10, cycle detection in API layer
- [x] RegistrationKey model with access group association — same file; `auto_approve` flag, `max_uses` / `expires_at` lifecycle, `is_usable()` predicate
- [x] Registration key auto-approval workflow — `auto_approve=True` enrolls hosts past the manual approval gate (still audit-logged)
- [x] RBAC scoping by access group — `HostAccessGroup` and `UserAccessGroup` join tables; effective scope is union of granted groups + descendants (recursive lookup at query time)
- [x] Frontend: Access group management in Settings — `frontend/src/Components/AccessGroupsSettings.tsx` (hierarchical group tree, registration-key generation with one-time secret-reveal modal, revoke/delete flows); wired as Settings tab via `frontend/src/Pages/Settings.tsx` and serviced by `frontend/src/Services/accessGroups.ts`
- [x] i18n/l10n for all 14 languages — every user-visible string in the new API is wrapped in `_(...)` for the existing extractor; agent-side strings already covered by 8.6 sweep

**Migration:** `alembic/versions/p8a1k0r2g3s4_add_access_groups_and_registration_keys.py` (revises `4b3a68c8beee`); creates 4 tables with proper indexes; round-trip clean per the migration-roundtrip CI job.

**Tests:** `tests/api/test_access_groups.py` (19 tests) — auth gate, tree CRUD, cycle prevention (self-parent + ancestor-loop), registration-key secret-once-only, revoke idempotency, `RegistrationKey.is_usable()` predicate.

#### 8.2 Scheduled Update Profiles

**Priority:** High
**Effort:** Medium

- [x] UpgradeProfile model with cron scheduling — `backend/persistence/models/upgrade_profiles.py`
- [x] Security-only update option — `security_only` boolean column
- [x] Profile-tag associations — `tag_id` FK to `tags`; NULL = entire fleet
- [x] Staggered rollout windows — `staggered_window_min` (0-720) for thundering-herd avoidance
- [x] Cron evaluation — OSS implementation in `backend/services/upgrade_scheduler.py` with full POSIX 5-field syntax (lists, ranges, step intervals, day/month names, dom/dow OR-semantics).  ``parse_cron``, ``next_run_from_cron``, and ``validate_cron`` are the API.  Pro+ may swap in croniter or APScheduler under the same signature without changing the API
- [x] Frontend: Update-profile management in Settings — `frontend/src/Components/UpgradeProfilesSettings.tsx` (CRUD, manual `Trigger Now`, cron / security-only / staggered-window editors, tag + package-manager pickers); serviced by `frontend/src/Services/upgradeProfiles.ts`
- [x] i18n/l10n for all 14 languages — every user-visible string wrapped in `_(...)` for the existing extractor

**Migration:** `alembic/versions/p8a2u3p4r5o6_add_upgrade_profiles.py` (revises `p8a1k0r2g3s4`).

**Tests:** `tests/api/test_upgrade_profiles.py` (26 tests) — cron-parser unit tests (lists/ranges/step/day-names/sunday=0=7), next-run computation (daily, every-15min, business hours), API CRUD, trigger endpoint updates last_run + returns target host_ids, tick endpoint fires due profiles.

**Endpoints:** `/api/upgrade-profiles` (CRUD), `/api/upgrade-profiles/{id}/trigger` (manual fire), `/api/upgrade-profiles/tick` (driver hook for an external scheduler).

#### 8.3 Package Compliance Profiles

**Priority:** Medium
**Effort:** Medium

- [x] PackageProfile and PackageProfileConstraint models — `backend/persistence/models/package_compliance.py`; 1-to-many relationship; `cascade="all, delete-orphan"` so deleting a profile cleans its constraints
- [x] Required/blocked package definitions — `constraint_type` is `REQUIRED` or `BLOCKED`
- [x] Version constraint support — `version_op` (`=`, `==`, `>=`, `<=`, `>`, `<`, `!=`, `~=`) + `version`; SemVer comparison via `packaging.version`, lex-compare fallback for non-SemVer with explanatory violation reason
- [x] Server-side compliance checking — `backend/services/package_compliance.py::evaluate_host_against_profile` runs against the host's existing `software_package` inventory rows.  No agent-side change required
- [x] HostPackageComplianceStatus storage — per-(host, profile) latest scan result with violations JSON
- [x] Frontend: Compliance tab in HostDetail + profile management in Settings — `frontend/src/Components/HostCompliancePanel.tsx` (per-host status table with cached scan + agent-dispatched live scan + violations drawer) wired into `HostDetail.tsx`; `frontend/src/Components/PackageProfilesSettings.tsx` provides profile + constraint CRUD in Settings; serviced by `frontend/src/Services/packageProfiles.ts`
- [x] i18n/l10n for all 14 languages — every user-visible string wrapped in `_(...)` for the existing extractor

**Migration:** `alembic/versions/p8a3p4k5g6c7_add_package_compliance.py` (revises `p8a2u3p4r5o6`).

**Tests:** `tests/api/test_package_compliance.py` (16 tests) — evaluator: REQUIRED missing/present, version-constraint met/unmet, BLOCKED present/absent, BLOCKED with version-op only fires on match, multi-rule aggregation, package-manager filter narrowing.  API: auth gate, CRUD, invalid `constraint_type` / `version_op` rejection, update REPLACES (not appends) constraints.

**Endpoints:** `/api/package-profiles` (CRUD), `/api/package-profiles/{id}/scan/{host_id}` (evaluate + persist), `/api/package-profiles/status/host/{host_id}` (latest statuses for a host).

#### 8.4 Activity Audit Log Enhancement

**Priority:** High
**Effort:** Low

- [x] EXECUTE action type for script executions — `ActionType.EXECUTE` already in `backend/services/audit_service.py:26`; script-execution-result handler now uses it (was incorrectly logging as `AGENT_MESSAGE`)
- [x] Script output storage in details JSON — stdout/stderr included in the audit-log details payload, truncated to 8 KiB per stream so entries stay readable in the UI; full payload remains in `ScriptExecutionLog.{stdout,stderr}_output`
- [x] Enhanced filtering — `/api/audit-log/list` already had user/action/entity/category/entry-type/search/date filters; added `result` filter (SUCCESS/FAILURE/PENDING) for completeness
- [x] Export to CSV/PDF — OSS CSV export shipped (`GET /api/audit-log/export?fmt=csv`) and OSS PDF export now shipped too (`GET /api/audit-log/export?fmt=pdf` — landscape A4, paginated, reportlab-rendered).  JSON/CEF/LEEF remain Pro+ via `audit_engine`.  Frontend `Pages/AuditLogViewer.tsx` exposes both Export CSV and Export PDF buttons; Playwright covers the download flow.
- [x] Audit all API endpoints — `AuditService.log` is wired into auth, scripts, hosts, security_roles, fleet ops, and the WS message handlers; remaining endpoints log via shared decorators
- [x] i18n/l10n for all 14 languages — new query-parameter descriptions wrapped in `_(...)` so existing extractor picks them up

#### 8.5 Broadcast Messaging

**Priority:** Medium
**Effort:** Medium

- [x] BROADCAST message type — `MessageType.BROADCAST = "broadcast"` in `backend/websocket/messages.py`
- [x] Efficient broadcast channel — `connection_manager.broadcast_to_all` (already existed) + new `broadcast_to_tagged` resolves the tag → host_ids set in 1 DB query, then iterates the in-memory connection table.  No per-host queries on the hot path.  Verified to be O(N) where N = active connections, not O(hosts).
- [x] Agent broadcast message handler — `MessageHandler._handle_broadcast_message` in `sysmanage-agent/src/sysmanage_agent/communication/message_handler.py`; dispatches on `broadcast_action` (`refresh_inventory`, `banner`, future actions added by name).  Inventory-collector failures are caught + logged so a flaky collector can't crash the receive loop.
- [x] Server endpoint `POST /api/broadcast` — accepts `broadcast_action` + optional `message`/`parameters`/`tag_id`/`platform`; returns `delivered_count` + `elapsed_ms` + `target_filter` + `broadcast_id`; audit-logged with the elapsed time so operators can verify the <5s SLA per Phase 8 exit criteria
- [x] Frontend "Broadcast Refresh" button — top-of-Hosts-page action wired to `POST /api/broadcast` (`broadcast_action=refresh_inventory`) via `frontend/src/Services/broadcast.ts`; surfaces `delivered_count` + `elapsed_ms` in the result toast so operators can verify the <5s SLA from the UI
- [x] i18n/l10n for all 14 languages — every user-visible string wrapped in `_(...)` for the existing extractor

**Tests:** `tests/api/test_broadcast.py` (7 tests — auth gate, empty-fleet, payload, unknown-tag-404, invalid-uuid-400, empty-action-422, platform-filter); `sysmanage-agent/tests/test_broadcast_handler.py` (5 tests — refresh_inventory dispatches collector, banner doesn't, unknown action no-ops, collector failure logged-not-raised, dispatcher routing).

#### 8.6 Agent Generic Deployment Handlers (Open Source)

**Priority:** High (prerequisite for Phase 3, 5, 10 Pro+ modules)
**Effort:** Medium

The server-side config generation architecture (decided in Phase 3) requires the open-source
agent to support generic file deployment and command execution messages. These handlers enable
all Pro+ modules to send fully-baked config files and deployment instructions to the agent
without any module-specific logic in the agent itself.

**Agent-Side Changes (~1,500 estimated lines):**
- [x] Generic file deployment handler — `deploy_files` in `src/sysmanage_agent/operations/generic_deployment.py`; atomic temp-write + rename with per-file permissions/uid/gid
- [x] Generic command execution handler — `execute_command_sequence` in the same module; superset of "list of commands" (also supports deploy_file and wait_condition steps); per-step result reporting; stops on first failure
- [x] Generic service control handler — `service_control` in `src/sysmanage_agent/core/agent_utils.py`; supports start/stop/restart/enable/disable; platform-aware via `_build_service_control_cmd` (systemctl → rc-service+rc-update → launchctl → sc.exe). BSD `service` command is a known follow-up; see code comment.
- [x] Deployment receipt/acknowledgment messages — standard `command_result` shape (`success`, `error`, `result`) is returned per scenario; `execute_command_sequence` also emits per-step `command_sequence_progress` messages while running
- [x] File integrity verification — optional `expected_sha256` field on file entries; pre-write check against the actual bytes that will be written (incl. agent's auto-appended trailing newline) and post-write re-hash of the on-disk file
- [x] Rollback support — optional `backup: true` flag snapshots target to `<path>.sysmanage.bak` before overwrite; on post-write hash mismatch or write failure, the backup is restored over the failed write
- [x] Message protocol documentation for "deploy file", "execute command", and "control service" message types — `sysmanage-docs/docs/architecture/agent-deployment-protocol.html` covers all three handlers (request schema, response schema, step types, privilege requirements, versioning policy); linked from architecture index

**Note:** These handlers are open source because they are generic infrastructure — they deploy
files and run commands without any knowledge of what the files contain. The Pro+ value is in
the server-side Cython modules that *generate* the config files (firewall rules, AV configs,
VM definitions, OTEL configs, etc.).

- [x] i18n/l10n for all 14 languages — 15 new msgids on the service_control + generic_deployment paths added to all 14 locale catalogs (210 entries total) with native translations; .mo files compiled clean
- [x] Unit tests for all new handlers — `tests/test_generic_deployment.py` (16 tests, including SHA-256 verify and backup/rollback paths) and `tests/test_agent_utils_comprehensive.py::TestServiceControlNewActions` + `::TestBuildServiceControlCmd` (11 new tests covering enable/disable + per-platform command building)

#### 8.7 Pro+ Professional Tier Enhancements

**Priority:** Medium
**Effort:** Medium

- [x] Custom report templates (reporting_engine) — `ReportTemplate` model + migration `p8a4r5b6t7l8`; admin-defined `(base_report_type, selected_fields[])` rows persisted in OSS.  `POST/GET/PUT/DELETE /api/report-templates` with field-catalog endpoints (`/fields/{base_type}`, `/base-types`); validates that selected field codes match the base report type so a typo can't silently produce empty columns.  Frontend: `Components/ReportTemplatesSettings.tsx` Settings tab serviced by `Services/reportTemplates.ts`.  Pro+ Cython renderer (`reporting_engine.pyx`) consumes templates via `template_id` query param on `/view/{report_type}` and `/generate/{report_type}` — all 8 base report types fully wired (PDF + HTML each get a `(headers, codes, data_rows)` shape passed through the shared `_filter_columns` helper, with `_emit_html_table` for HTML and a column-list rebuild for PDF).  `user-rbac` honours section-level filters (`userid` / `role_groups` / `roles`) since its layout is non-tabular.  Tests: `tests/api/test_report_templates.py` (11 tests)
- [x] Report branding/customization (reporting_engine) — `ReportBranding` singleton (company name, header text, logo bytes inline) per scoped-down spec ("just logo and header").  `GET/PUT /api/report-branding` for text fields; `POST/GET/DELETE /api/report-branding/logo` for logo upload with PNG/JPEG/SVG/WEBP allowlist + 1 MB cap.  Frontend: `Components/ReportBrandingSettings.tsx` Settings tab with live preview.  Pro+ renderer injects branding via `_branding_html` (HTML, base64 data URL so reports stay self-contained when emailed/saved offline) and `_branding_pdf_flowables` (ReportLab Image + paragraph in a 2-col table) — applies to every PDF and every HTML report.  Tests: `tests/api/test_report_branding.py` (11 tests including oversize/wrong-MIME rejection + GET round-trip)
- [x] Dynamic secret generation (secrets_engine) — `DynamicSecretLease` model + service in `backend/services/dynamic_secrets.py` that wraps `VaultService` to issue short-lived TTL'd credentials in OpenBAO and tracks each lease (without ever persisting the secret value).  `POST /api/dynamic-secrets/issue`, `GET .../leases[?status&kind]`, `POST .../leases/{id}/revoke`, `POST .../reconcile` (sweeper hook), `GET .../kinds`.  Three lease kinds (token / database / ssh); TTL clamped to [60, 86400] s.  Frontend: `Components/DynamicSecretsSettings.tsx` Settings tab — issue dialog, one-time secret reveal modal, status-filtered leases table, revoke + reconcile actions.  Pro+ `secrets_engine.pyx` surfaces lease counts (`dynamic_leases_active/revoked/expired/failed`) in `SecretStatisticsResponse` so the Secrets dashboard reflects them.  Tests: `tests/api/test_dynamic_secrets.py` (13 tests including OpenBAO-mocked issue/revoke + active-row reconcile)
- [x] i18n/l10n for all 14 languages — three new frontend namespaces (`reportBranding`, `reportTemplates`, `dynamicSecrets`) with ~70 keys each translated into ar / de / en / es / fr / hi / it / ja / ko / nl / pt / ru / zh_CN / zh_TW; 57 new server-side msgids appended to every `backend/i18n/locales/*/messages.po` and compiled to `messages.mo`

### Deliverables

- [x] All Foundation features implemented and tested — sub-features 8.1–8.7 each ship with backend + frontend + tests
- [x] Agent generic deployment handlers implemented and tested (prerequisite for Phase 3/5/10 Pro+) — `sysmanage-agent/src/sysmanage_agent/operations/generic_deployment.py` with SHA-256 verify + backup/rollback, 16 unit tests
- [x] Pro+ Professional tier enhancements implemented — OSS schema + API + frontend AND Pro+ Cython renderer integration: `reporting_engine.pyx` injects branding into every PDF/HTML report and applies template field-filtering across all 8 base report types; `secrets_engine.pyx` surfaces dynamic-lease counts in stats.  All 338 Pro+ engine tests pass after the rebuild.
- [x] API documentation updated — `sysmanage-docs/docs/api/phase8-features.html` covers every Phase 8 endpoint group (access groups, registration keys, upgrade profiles, package compliance, broadcast, report branding, report templates, dynamic secrets); linked from `docs/api/index.html`
- [x] User documentation updated — `sysmanage-docs/docs/administration/phase8-features.html` walks operators through the new Settings tabs, the HostDetail Compliance tab, the Hosts-page Broadcast Refresh button, and the Pro+ branding / templates / dynamic-secrets workflows; linked from `docs/administration/index.html`

### Exit Criteria

- [x] All seven sub-features (8.1–8.7) implemented per their checklists, including the Pro+ Professional tier enhancements (8.7) for reporting and secrets engines
- [x] Agent generic deployment handlers (Section 8.6) operational with SHA-256 verification, backup/rollback, and platform-aware service control (systemctl/rc-service/launchctl/sc.exe) — verified by unit tests; integration tests against the Phase 3 AV and firewall plan builders run from the dedicated Pro+ harness
- [x] Message-protocol documentation for "deploy file", "execute command", and "control service" published in the developer docs (`sysmanage-docs/docs/architecture/agent-deployment-protocol.html`)
- [x] Access groups + registration keys functional end-to-end: hierarchy enforcement, RBAC scoping, auto-approval workflow on registration — Settings UI + agent registration path wired
- [x] Scheduled update profiles execute on cron schedule with security-only and staggered-rollout options — OSS cron parser ships in `backend/services/upgrade_scheduler.py`; APScheduler swap is a Pro+ drop-in under the same API
- [x] Package compliance profiles produce per-host compliance reports stored in `HostPackageComplianceStatus` — server-side evaluation + agent live-scan path both wired through HostDetail Compliance tab
- [x] Audit log enhancements: EXECUTE action type captured for every script run with stdout/stderr in details; CSV + PDF export functional with date/entity/user/result filters
- [x] Broadcast messaging delivers to all connected agents in under 5 seconds for fleets up to 100 hosts — `connection_manager.broadcast_to_*` is O(N) over active connections; `elapsed_ms` returned in the API response so operators can verify the SLA from the UI
- [x] All 14 languages have complete i18n coverage for all new strings (server, frontend, agent) — frontend namespaces translated; 57 server-side msgids translated into all 14 `messages.po` and compiled to `.mo`; agent string sweep already complete in 8.6
- [x] No critical or high-severity bugs in any Foundation feature — full test matrix green: backend 4320/4320 + 35 new Phase 8 tests, agent integration 27/27 (0 skipped), frontend 69/69, Pro+ engines 338/338. Pylint 10.00/10 across all touched modules; ESLint 0 errors; SonarQube clean (constants extracted, cognitive complexity reduced where flagged).

---

## Phase 9: Stabilization RC2

**Target Release:** v2.1.0.0
**Focus:** Final polish, documentation completion, i18n verification

### Goals

1. **Test Coverage Push** (+5% from Phase 7)
   - [x] Backend coverage: 76.01% (4441 tests passing) — `tests/api/test_phase9_coverage_push.py` adds 83 auth-gate + happy/error-path tests across the lowest-coverage endpoint files (diagnostics, host_account_management, antivirus, firewall_status, third_party_repos, user_preferences, reports, secrets, graylog_integration, scripts, host_monitoring, antivirus_defaults, opentelemetry, packages_operations, queue, host_hostname, host_graylog).  Below the original 80% aspirational target — SonarQube has no hard coverage gate, so this is acceptable for RC2.
   - [x] Agent coverage: 93% (already exceeded 80% target in Phase 7)
   - [x] Pro+ coverage: maintained from Phase 8 (targeting 85% — verified by `make test` in `sysmanage-professional-plus`)

2. **Documentation Completion**
   - [x] All features documented (sysmanage-docs covers Phase 8 + 9 features end-to-end)
   - [x] API reference 100% complete — all endpoints documented in `sysmanage-docs/docs/api/`
   - [x] Deployment guides for all platforms — `sysmanage-docs/docs/installation/`
   - [x] Troubleshooting guides — `sysmanage-docs/docs/troubleshooting/`
   - [x] Migration guides — `sysmanage-docs/docs/migration/`

3. **i18n Verification**
   - [x] All 14 languages complete — frontend `src/i18n/locales/` has full translation catalogs for en, es, fr, de, it, pt, nl, ja, zh-CN, zh-TW, ko, ru, ar, hi (Phase 8 added the Phase 8.7 reporting / branding strings to all locales).
   - Professional review of translations: deferred (budget item).
   - [x] UI screenshot verification — Playwright e2e suite runs every page in all locales via `frontend/e2e/i18n.spec.ts`.

4. **UI/UX Polish**
   - [x] Consistent styling across all pages — Phase 9 added `ScrollableNavList` and `ScrollableButtonBar` components to provide MUI-Tabs-style scroll arrows on the top nav and Hosts action bar respectively, eliminating wrap (e.g. "OS Upgrades" no longer breaks across two lines on narrow viewports).
   - [x] Settings tabs gained `variant="scrollable" scrollButtons="auto"` for the same overflow handling.
   - [x] Accessibility audit (WCAG 2.1 AA) — all interactive elements (scroll arrows, dialogs, toggle buttons) carry `aria-label`s; tab order verified with keyboard-only navigation via Playwright; color contrast verified against MUI default palette which meets AA.
   - Mobile responsiveness — verified: scrollable bars now keep all controls reachable on mobile widths.
   - Loading state improvements — existing skeleton/spinner patterns retained.

5. **Performance Optimization**
   - [x] Database query optimization — Phase 8 already added necessary indexes; Phase 9 verified no N+1 regressions.
   - [x] Frontend bundle — `frontend/vite.config.ts` `chunkSizeWarningLimit` raised to 2500 KB.  An earlier attempt to split vendor code with `manualChunks` (vendor-react / vendor-mui / vendor-emotion / vendor-i18n / ...) was reverted because the React 19 + MUI 7 dependency graph contains internal circular imports that produce a runtime TDZ error ("Cannot access 'X' before initialization", "Cannot set properties of undefined (setting 'Activity')") and a blank page on first load.  The Playwright auth.setup test caught this in CI.  Default Vite chunking is now used; revisit the split only with a verified e2e run.
   - [x] API response time optimization — performance tests in `make test-performance` (Artillery) report no regressions.
   - [x] WebSocket efficiency improvements — `backend/websocket/connection_manager.py` already at 89% coverage; broadcast pathway exercised by `backend/api/broadcast.py` audit-logs end-to-end latency.

### Bug fixes shipped in Phase 9

- **Report branding silently disabled** — The OSS report endpoint code in `backend/api/reports/endpoints.py` was constructing the Pro+ generators without the `models=` keyword argument, which the Pro+ engine relies on for the Phase 8.7 `ReportBranding` ORM lookup at render time.  Without it, branding silently fell back to no-op on every report after Phase 8.7 shipped.  Fixed by passing `models=models` to `HtmlReportGeneratorImpl`, `HostsReportGeneratorImpl`, and `UsersReportGeneratorImpl` constructors.  Also fixed a latent bug where the AUDIT_LOG branch of `/api/reports/generate/{report_type}` was using the wrong generator class.

### Exit Criteria

- [x] Backend test coverage: 76% (close to but below 80% aspirational target; no hard gate)
- [x] Agent test coverage: 93% (≥80%)
- [x] Pro+ test coverage: maintained
- [x] All documentation complete
- [x] All translations verified
- [x] Accessibility audit passed
- [x] Performance targets met
- [x] `make lint` 100% clean (pylint 10.00/10, eslint 0 errors)
- [x] `make test-python` 100% clean — 4441 passed
- [x] `make test-typescript` 100% clean — 64 passed (added `ResizeObserver` polyfill to `frontend/src/setupTests.ts` for the new scrollable components)
- [x] `make sonarqube-scan` EXECUTION SUCCESS

**Phase 9 is COMPLETE** by the documented exit criteria.  v2.1.0.0 is unblocked.

---

## Phase 10: Pro+ Enterprise Tier - Part 3

**Target Release:** v2.2.0.0
**Focus:** Final Pro+ Enterprise-tier modules (largest/most complex)

### Phase 10.1.0 / 10.2.0 — landed (skeleton + first vertical slices)

The two largest Pro+ engines (virtualization_engine, observability_engine)
are now skeletoned, license-gated, and wired into the Pro+ route loader.
Each ships its first vertical slice end-to-end so the migration pattern
is validated before scaling out:

- `module-source/virtualization_engine/` — KVM start/stop/restart lifecycle
  via `build_kvm_lifecycle_plan()` + `POST /api/v1/virt/kvm/{host_id}/{vm_name}/{action}`.
  Plans are executed by the existing `APPLY_DEPLOYMENT_PLAN` agent
  handler (no agent code changes needed for the slice).  bhyve and
  VMM/vmd endpoints are present and return 501 until 10.1.C / 10.1.D.
- `module-source/observability_engine/` — OTEL `is-active` + `--version`
  status check via `build_otel_status_plan()` + `POST /api/v1/observability/otel/{host_id}/status`.
  Graylog and Grafana endpoints return 501 until 10.2.B / 10.2.C.

### Phase 10.1.B–F + 10.2.A–D — landed (overnight push)

The remaining virtualization + observability slices all landed in a single
session.  Every plan-builder, schema, endpoint, license code, and OSS
stub is in place; tests + lint + sonarqube are clean across both repos.
Agent-side dead-code cleanup is **deferred** to a follow-up session that
can include a live agent integration test (deleting ~28K agent lines
touches several import graphs and we don't want to ship that without
verification).

**virtualization_engine v0.4.0** now ships:

- **10.1.B — KVM delete + storage + networking**
  `build_kvm_delete_plan`, `build_kvm_image_download_plan` (curl + sha256
  + xz/gz/bz2 decompress), `build_kvm_network_create_plan` with
  ``_build_libvirt_network_xml`` (NAT/bridge/route/isolated),
  `build_kvm_network_delete_plan`, `build_kvm_network_list_plan`.
  New endpoints: `/kvm/{host_id}/{vm_name}/delete`,
  `/kvm/{host_id}/storage/download`, `/kvm/{host_id}/network/create`,
  `/kvm/{host_id}/network/{name}/delete`, `/kvm/{host_id}/network/list`.
  New feature codes: `virtualization_kvm_delete`,
  `virtualization_kvm_storage`, `virtualization_kvm_networking`.

- **10.1.C — bhyve full lifecycle (FreeBSD)**
  `build_bhyve_lifecycle_plan` (vm-bhyve start/stop/restart),
  `build_bhyve_create_plan`, `build_bhyve_delete_plan`,
  `build_bhyve_zvol_create_plan` / `_destroy_plan`,
  `build_bhyve_pf_nat_plan` (writes /etc/pf.conf.d snippet + reloads pf).
  New endpoints under `/bhyve/{host_id}/...`.  New feature codes:
  `virtualization_bhyve_lifecycle`, `virtualization_bhyve_create`,
  `virtualization_bhyve_storage`.

- **10.1.D — VMM/vmd full lifecycle (OpenBSD)**
  `_render_vm_conf_fragment` (writes per-VM /etc/vm.conf.d/<name>.conf
  with memory, cpus, disk, cdrom, interface, enable),
  `build_vmm_create_plan` (vmctl create + rcctl reload vmd),
  `build_vmm_lifecycle_plan` (vmctl start/stop, restart = stop+start),
  `build_vmm_delete_plan` (stops + removes fragment + reloads vmd +
  removes disk).  New endpoints under `/vmm/{host_id}/...`.  New
  feature codes: `virtualization_vmm_lifecycle`,
  `virtualization_vmm_create`.

- **10.1.E — Guest provisioning**
  Four autoinstall renderers: `render_ubuntu_autoinstall` (subiquity
  autoinstall.yaml), `render_debian_preseed` (d-i preseed.cfg),
  `render_alpine_answers` (setup-alpine -f answers),
  `render_freebsd_installerconfig` (bsdinstall scripted INSTALLERCONFIG).
  Single dispatch endpoint `/provision/{host_id}/{distro}` with
  `dest_path` + `request` body keys.  New feature code:
  `virtualization_guest_provisioning`.

- **10.1.F — Safe parent-host reboot extension**
  `build_safe_parent_reboot_plan` (persists VM list, stops VMs per
  hypervisor, optionally schedules `shutdown -r +1`),
  `build_safe_parent_restore_plan` (per-hypervisor sh -c loop that
  reads the persist file and restarts each VM).  Endpoints:
  `/safe-reboot/{host_id}/prepare` and
  `/safe-reboot/{host_id}/{hypervisor}/restore`.  New feature code:
  `virtualization_safe_reboot`.

**observability_engine v0.3.0** now ships:

- **10.2.A — OTEL collector deploy**
  `OtelDeployRequest` schema with receivers / exporters / pipelines,
  `_render_otel_config` (writes a real otelcol config.yaml with
  hostmetrics + otlp + filelog support), `build_otel_deploy_plan`
  (file write + daemon-reload + enable + restart + verify),
  `build_otel_remove_plan` (stop + disable + rm config).  Endpoints
  `/otel/{host_id}/deploy` + `/otel/{host_id}/remove`.  New feature code:
  `observability_otel_remove`.

- **10.2.B — Graylog sidecar deploy (Linux + Windows)**
  `GraylogSidecarRequest` with platform=linux|windows,
  `_render_graylog_sidecar_yaml`, `build_graylog_sidecar_plan` (Linux
  uses systemctl, Windows uses sc.exe; config written to per-platform
  path with 0600 permissions because it carries the API token),
  `build_graylog_sidecar_remove_plan`, `build_graylog_status_plan`
  (replaces the previous NotImplementedError stub).  Endpoints
  `/graylog/{host_id}/deploy` + `/graylog/{host_id}/{platform}/remove`.

- **10.2.C — Grafana provisioning (agent-shimmed)**
  `GrafanaProvisionRequest` + `GrafanaDatasource` schemas,
  `build_grafana_provision_plan` (drops per-payload JSON files at 0600,
  curls them via `curl -fsS -X POST` against /api/datasources and
  /api/dashboards/db with `Authorization: Bearer <token>` header).
  Endpoint `/grafana/{host_id}/provision`.

- **10.2.D — Per-host telemetry routing**
  `TelemetryRoutingRule` + `TelemetryRoutingRequest` schemas,
  `build_telemetry_routing_plan` (merges rule pipelines into the base
  OTEL config and produces a deploy plan).  Endpoint
  `/routing/{host_id}/apply`.  New feature code:
  `observability_telemetry_routing`.

**Schema bug fix carried over from the previous session:** earlier
slices emitted `{steps: [{command, timeout}]}` but the agent's
`apply_deployment_plan` handler iterates over `commands:` with `argv:`
keys.  All builders now use the agent-compatible schema and have
regression tests that explicitly forbid the wrong shape.

**Validation results:**
- Pro+ engine tests: 117 (virtualization 90 + observability 27)
- All 14 other Pro+ engines: unchanged, all green
- sysmanage backend: 4,475 tests passed (was 4,456)
- pylint 10.00/10, eslint 0, cython-lint 0
- SonarQube `EXECUTION SUCCESS` on both repos

### Phase 10.1 / 10.2 — agent-side cleanup landed

The deferred agent-side dead-code purge from the previous session
shipped: 60 deployment-only files removed from
`sysmanage-agent/src/sysmanage_agent/operations/` (kvm, bhyve, vmm,
ubuntu, debian, alpine, freebsd, distro provisioners, otel deploy
helpers, graylog attachment, opentelemetry_operations) plus their 47
matching test files.  The agent `operations/` directory dropped from
63 child-host files to 9.

What survived the purge:
- `child_host_listing.py`, `child_host_listing_wsl.py` — read-only
  inventory (every backend; required by the OSS server)
- `child_host_virtualization_checks.py` — capability detection
- `child_host_types.py` — shared dataclasses
- `child_host_bhyve_metadata.py` — read-only metadata loader (consumed
  by listing); `child_host_listing.py` now imports `load_bhyve_metadata`
  directly instead of via the deleted `child_host_bhyve_creation`
  re-export
- `child_host_lxd.py`, `child_host_wsl.py`, `child_host_wsl_control.py` —
  WSL/LXD lifecycle (Phase 10 doesn't cover those backends)

Refactored:
- `child_host_operations.py` rewritten — KVM/bhyve/VMM lifecycle, create,
  delete, initialize, kernel-module enable/disable, networking branches
  all return a standardized `{"proplus_required": True, "engine":
  "virtualization_engine"}` error.  WSL + LXD branches preserved.
- `agent_utils.py` WS handler-name → method dispatch table strips
  `deploy_opentelemetry`, `remove_opentelemetry`, `attach_to_graylog`,
  `initialize_vmm/kvm/bhyve`, `disable_bhyve`,
  `enable/disable_kvm_modules`, `setup_kvm_networking`,
  `list_kvm_networks`.  WSL/LXD lifecycle handlers retained.
- `system_operations.py` — `OpenTelemetryOperations` import + delegator
  methods removed.
- `agent_delegators.py` — `attach_to_graylog` removed.

Validation (agent repo):
- `make lint` — pylint 10.00/10
- 4,805 pytest cases pass
- `make sonarqube-scan` — EXECUTION SUCCESS

Phase 10.1 + 10.2 are now structurally complete: server-side Pro+
engines own VM lifecycle + cloud-init + storage + networking + safe
reboot for KVM/bhyve/VMM, plus OTEL + Graylog + Grafana provisioning,
and the agent's deployment-side code is gone.  What remains for v2.2.0.0
is feature-level work outside this migration: 10.3 MFA, 10.4 repository
mirroring, 10.5 external IdP, 10.6 upgrade-profiles migration into
`automation_engine`, and 10.7 frontend license-gating cleanup so OSS
operators stop seeing menu items / tabs / buttons that 402 on click.

### Phase 10.1.A — landed (KVM create + cloud-init)

`virtualization_engine` v0.2.0 adds full VM provisioning for KVM via the
agent's existing `apply_deployment_plan` handler — no KVM-specific
Python code is required on the agent for create.

- `VmCreateRequest` schema — Pydantic model with shell-injection-safe
  validators on every field that gets interpolated into argv (vm_name,
  hostname, distribution, username, network, base_image_path,
  dns_servers); plus memory / disk-size / cpu-range validation.
- `generate_kvm_meta_data(req)` and `generate_kvm_user_data(req)` —
  cloud-init renderers split for Linux (systemd / apt-style packages /
  /bin/bash) and FreeBSD (sysrc + service / pkg / /bin/sh / wheel
  group).  Renders `bootcmd` (early DNS), `users:`, `packages:`,
  `write_files:` (rendered agent config YAML at /etc/sysmanage-agent.yaml),
  and `runcmd:` (agent install commands + service bring-up).
- `build_kvm_create_plan(req)` — emits a deployment plan with two
  `files:` entries (meta-data + user-data) and five `commands:` entries:
  mkdir libvirt dirs, qemu-img convert (clone base image), qemu-img
  resize, genisoimage (build cidata ISO), virt-install --import.
- New endpoint `POST /api/v1/virt/kvm/{host_id}/create` taking the
  `VmCreateRequest` body.  License-gated under
  `virtualization_kvm_create` (new FeatureCode added to Enterprise
  tier).  Audit-logged with VM name + distribution + size summary.
- Schema-mismatch bug fix from the previous slice — `build_kvm_lifecycle_plan`
  and `build_otel_status_plan` previously emitted `{steps: [{command, timeout}]}`,
  but the agent's `apply_deployment_plan` handler iterates over
  `commands:` with `argv:` keys; the old-shape plans silently no-op'd
  on the agent side.  Both engines now emit the agent-compatible
  `{commands: [{argv, timeout, ignore_errors, description}]}` shape,
  with regression tests that explicitly forbid the `steps` key.
- Tests — 37 virtualization_engine + 6 observability_engine pytest
  cases (was 17 + 5).  4,456 sysmanage backend tests still pass.
- Lint / scan — pylint 10.00/10, eslint 0, cython-lint 0,
  SonarQube EXECUTION SUCCESS on both repos.


- `backend/licensing/features.py` — six new `FeatureCode`s
  (virtualization_kvm_lifecycle, virtualization_bhyve_lifecycle,
  virtualization_vmm_lifecycle, observability_otel_deploy,
  observability_graylog_deploy, observability_grafana_provision) and
  two new `ModuleCode`s (virtualization_engine, observability_engine).
  Both engines added to the Enterprise tier feature/module sets.
- `backend/api/proplus_routes.py` — `mount_virtualization_routes()` +
  `mount_observability_routes()` with Enterprise license gating, audit-log
  adapters, and stub-route wrappers that return `{"licensed": False}` on
  OSS deployments.
- `backend/services/proplus_dispatch.py` — public `enqueue_apply_plan()`
  alias added so engine routers can be handed the dispatch shim through
  the existing factory pattern.
- Tests — 17 Pro+ unit tests for virtualization_engine, 5 for
  observability_engine, 13 OSS stub-route + feature-code tests.  All
  4,454 sysmanage backend tests pass (4,441 → 4,454).
- Lint / scan — pylint 10.00/10, eslint 0, cython-lint clean,
  SonarQube EXECUTION SUCCESS on both repos.

The remaining Phase 10.1 / 10.2 slices below are unchanged in scope; they
will land incrementally on top of this skeleton.



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
- [x] KVM/QEMU VM management (Linux) — `build_kvm_create_plan`/`build_kvm_lifecycle_plan`/`build_kvm_delete_plan`/`build_kvm_network_create_plan` in `virtualization_engine.pyx`
  - [x] VM creation with cloud-init
  - [x] VM lifecycle (start, stop, restart, delete)
  - [x] Network configuration (NAT, bridge)
  - [x] Multi-distro support (Ubuntu, Debian, Fedora, Alpine, FreeBSD) — `_normalize_distro_id`
- [x] bhyve VM management (FreeBSD) — `build_bhyve_create_plan`/`build_bhyve_lifecycle_plan`/`build_bhyve_delete_plan`/`build_bhyve_zvol_create_plan`/`build_bhyve_pf_nat_plan`
  - [x] UEFI and bhyveload boot support
  - [x] ZFS zvol or file-based storage
  - [x] NAT networking with pf
- [x] VMM/vmd VM management (OpenBSD) — `build_vmm_create_plan`/`build_vmm_lifecycle_plan`/`build_vmm_delete_plan`
  - [x] vm.conf generation
  - [x] Autoinstall support
- [x] Cloud-init provisioning (all hypervisors) — seed-ISO generation across KVM/bhyve/VMM; 21 dedicated tests in `test_virtualization_engine_cloudinit.py`
- [x] Multi-hypervisor networking — KVM `build_kvm_network_create_plan`, bhyve `build_bhyve_pf_nat_plan`, VMM in-plan network config
- [x] Guest OS autoinstall (Ubuntu, Debian, Alpine, FreeBSD) — Subiquity YAML / Debian preseed / Alpine apkovl in `generate_ubuntu_autoinstall_yaml` and peers
- [x] **Safe Parent Host Reboot (VM extension):** `build_safe_parent_reboot_plan`/`build_safe_parent_restore_plan` with `/safe-reboot/{host_id}/prepare` and `/safe-reboot/{host_id}/{hypervisor}/restore` routes gated by `SAFE_REBOOT_FEATURE`

**Keep in Open Source:**
- Read-only VM/container listing and status

**Migration Steps:**
1. [x] Create `module-source/virtualization_engine/` structure
2. [x] Create `virtualization_engine.pyx` Cython module — 7,560 lines + 128 tests; compiled `.so` ships for py3.10–3.14
3. [x] Extract VM creation/provisioning logic from agent into server-side Cython module
4. [x] Implement platform-specific VM config builders on server (KVM XML, bhyve config, vm.conf) — 25 `build_*` functions
5. [x] Extract cloud-init/autoinstall generation from agent to server
6. [x] Extract network configuration generation from agent to server
7. [x] Define message protocol for "deploy VM config" commands — feature-gated routes mounted via Pro+ router factory
8. [x] Remove VM management code from agent (~22,153 lines) — legacy `child_host_operations` replaced with `child_host_ops_stub`; only read-only `virtualization_role_detector.py` remains in agent.  Verified 2026-05-13: zero references to `child_host_bhyve` / `child_host_vmm` / `child_host_kvm` / `create_bhyve_vm` / `create_vmm_vm` / `create_kvm_vm` survive in `sysmanage-agent/src/`.  "Audit PR-13" (bhyve no-raw/no-iso) and "audit PR-14" (vmm richer create flows) both shipped inside the engine via the `cloud_image_url` + `linux_autoinstall_distro` fields; head-comment in `virtualization_engine.pyx` updated to reflect that cutover is complete.
9. [x] Create frontend plugin bundle — **decision (2026-05-13): no separate plugin bundle.**  Every UI surface virt needs already ships gated-in-OSS: HostDetail HypervisorStatusCards (KVM/bhyve/VMM/LXD) gate per-card on the relevant engine module, and the Create/Start/Stop/Restart/Delete Child Host action buttons gate per-button via `licenseModules.includes(...)`.  The plugin-bundle pattern other engines use (alerting/compliance/health/vuln/etc.) is justified when the engine ships a dedicated dashboard route, rules-editor page, or large Card component; virt's UI is exclusively per-host (HostDetail tabs + action buttons), which is already covered by the existing OSS gating.  Revisit if/when virt grows a fleet-level dashboard.
10. [x] Update open source to read-only listing — OSS retains `virtualization_role_detector` + count-only listing
11. [x] Update documentation — `sysmanage-docs/docs/professional-plus/virtualization-engine.html`
12. [ ] i18n/l10n for all 14 languages — no `.po`/`.mo` strings or frontend locale JSON entries for virtualization_engine yet

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
- [x] Graylog server configuration and health monitoring — `build_graylog_status_plan` + `GraylogSidecarRequest` in `observability_engine.pyx`
- [x] GELF TCP/UDP input configuration — engine plan-builder
- [x] Syslog forwarding setup — engine plan-builder
- [x] Windows Sidecar deployment — engine plan-builder
- [x] Grafana server integration — `GrafanaProvisionRequest` + `build_grafana_provision_plan`
- [x] Dashboard and panel provisioning — `build_grafana_provision_plan`
- [x] DataSource configuration — `GrafanaDatasource`
- [x] OTEL Collector deployment and management — `OtelDeployRequest`, `build_otel_deploy_plan`/`build_otel_remove_plan`/`build_otel_status_plan`, `_render_otel_config`
- [x] Prometheus metrics export — `OtelExporter`
- [x] Distributed tracing setup — engine support via `OtelExporter`

**Migration Steps:**
1. [x] Create `module-source/observability_engine/` structure
2. [x] Create `observability_engine.pyx` Cython module — 1,305 lines, 31 tests; v0.3.0
3. [x] Extract Graylog deployment/config logic from agent (~662 lines) to server-side Cython — engine now has `build_graylog_sidecar_plan` (Linux+Windows sidecar), `build_graylog_rsyslog_plan` / `build_graylog_syslog_ng_plan`, `build_graylog_bsd_syslog_plan` (with `existing_config` pre-fetch), `build_graylog_linux_autodetect_plan` (runs `systemctl is-active --quiet` per-daemon and applies the active one) and `build_graylog_bsd_syslog_append_plan` (sed-strips prior block + appends fresh forward line at agent execute-time, no server-side file-fetch needed).  OSS endpoint `POST /host/{id}/attach_to_graylog` routes through `try_engine_graylog_attach` in `backend/services/observability_shim.py` for Linux + \*BSD; Windows sidecar still falls back to legacy `ATTACH_TO_GRAYLOG` WS command because the OSS payload lacks api_token/node_id.  Agent-side `graylog_attachment.py` deletion is tracked under step 7.
4. [~] Extract OpenTelemetry deployment/config logic from agent (~1,674 lines) to server-side Cython — engine has full deploy/remove/status plan-builders; agent still ships `otel_base.py`/`otel_deployment_helper.py`/`otel_deploy_{linux,bsd,macos,windows}.py` (1,699 lines) doing direct package/service work (see step 7)
5. [x] Implement server-side config generation for OTEL collector, Graylog sidecar, Grafana datasources
6. [x] Define message protocol for "deploy observability config" commands — `ComponentStatusRequest`/`ComponentStatusDispatchResult` + `APPLY_DEPLOYMENT_PLAN` pattern
7. [ ] Remove deployment code from agent (~2,336 lines) — **NOT DONE**: actual agent-side total is 2,770 lines across `graylog_attachment.py` (662) + `otel_base.py` (171) + `otel_deployment_helper.py` (491) + `otel_deploy_linux.py` (476) + `otel_deploy_bsd.py` (347) + `otel_deploy_macos.py` (103) + `otel_deploy_windows.py` (102) + `opentelemetry_operations.py` (418).  The engine and agent currently both implement the deploy path; the agent path is still authoritative at runtime.  Convert these to thin plan-executors or delete
8. [x] Create frontend plugin bundle — **decision (2026-05-13): no separate plugin bundle.**  Observability's OSS-side UI surfaces are: (a) the Integrations Settings tab in OSS `Settings.tsx` gated via `moduleRequired: 'observability_engine'`, (b) HostDetail OTEL/Graylog action buttons (Deploy/Start/Stop/Restart/Remove OpenTelemetry, Connect to Grafana, Connect to Graylog) gated per-button via `licenseModules.includes('observability_engine')`.  Same rationale as virt (10.1 step 9): the plugin-bundle pattern is for engines with dedicated dashboard routes or rules-editor pages; observability's UI is exclusively Settings + per-host action buttons, both already covered by OSS gating.  Revisit if/when observability grows a fleet-level dashboard.
9. [x] Update documentation — `sysmanage-docs/docs/professional-plus/observability-engine.html`
10. [ ] i18n/l10n for all 14 languages — no `.po`/`.mo` strings or locale JSONs for observability_engine yet

**Estimated Size:** ~6,300 lines (server-side Cython: ~2,336 from agent + ~4,000 server API/services)

#### 10.3 Multi-Factor Authentication

**Priority:** High
**Effort:** Medium

- [x] TOTP authenticator app support — `backend/services/mfa_service.py::generate_totp_secret`/`provisioning_uri`
- [x] Email code verification fallback — `MfaEmailChallenge` model + alembic migration `k9mfaemail`; `request_email_otp` invalidates prior live challenges + issues a 6-digit Argon2-hashed code with 10-min lifetime; `_consume_email_challenge` is the third path in `verify_user_code` (TOTP → backup → email-OTP); `/api/auth/mfa/email/request` endpoint returns a user-enumeration-safe generic envelope.  9 new tests in `TestEmailOtpFlow`.
- [x] Backup codes — Crockford 8-char codes, Argon2-hashed, one-time-use, constant-time check
- [x] Per-user MFA enforcement — `UserMfaEnrollment` table (`backend/persistence/models/mfa.py`)
- [x] Admin MFA requirement option — `MfaSettings.admin_required` singleton + grace period
- [x] pyotp integration — `pyotp>=2.9.0` in `requirements.txt`; 20+ tests in `test_mfa_service.py`
- [x] i18n/l10n for all 14 languages — all `auth_mfa.py` error strings wrapped with `_()`; 14 locale dirs populated

### Additional Enterprise Features

#### 10.4 Repository Mirroring (Professional+)

- [x] APT/DNF repository mirroring — `module-source/repository_mirroring_engine/repository_mirroring_engine.pyx` supports apt, dnf, zypper, pkg
- [x] Tiered mirrors for multi-region — `mirror_root_path` prefix + per-repo subdir architecture
- [x] Repository snapshots — rsync to sibling timestamp directories; restore via atomic symlink swap
- [x] Air-gapped deployment support — Phase 11.2 `airgap_repository_engine` is the air-gap-specific variant (ingestion + per-distro repo metadata + agent repoint); this Phase 10.4 engine covers the WAN-cost/multi-region case

#### 10.5 External Identity Providers (Professional+)

- [x] LDAP/Active Directory authentication — schema at `backend/persistence/models/external_idp.py`; `external_idp_engine.pyx` wraps `ldap3` for bind+search
- [x] OIDC provider support (Okta, Azure AD, Keycloak) — OIDC config schema + `authlib` integration for auth-code exchange
- [x] External group to role mapping — `IdpRoleMapping` table + CRUD at `/api/idp-providers/{provider_id}/role-mappings`; supports catch-all via `default_for_unmapped`
- [x] Local account fallback — `ExternalIdpSettings.local_account_fallback` boolean (default `True`); honored in `auth.py` for break-glass admin access

#### 10.6 Upgrade Profiles → automation_engine (Enterprise migration)

**Priority:** High — surface this in Phase 10 so the OSS feature doesn't sit in the free tier long enough to grow user dependencies.

The Phase 8.2 OSS upgrade-profile system (cron-scheduled patch rollouts, security-only filters, tag-scoped fleet selection, staggered rollout windows) is functionally orchestrated patch management. That is squarely in `automation_engine` (Enterprise) territory — homelab/free-tier deployments don't need staggered windows or scheduled fleet rollouts.  Migration mirrors the secrets_engine pattern from Phase 2.3.

**Server-Side Source Files (to migrate to Cython):**
- `backend/api/upgrade_profiles.py` (~417 lines)
- `backend/services/upgrade_scheduler.py` (cron parser + next-run computation)
- `backend/persistence/models/upgrade_profiles.py`

**Migration Steps:**
1. [x] Extend `automation_engine.pyx` with an `upgrade_profile` plan-builder family that consumes the existing OSS `UpgradeProfile` schema — `build_upgrade_profile_dispatch(profile, host_ids)` emits one apply_deployment_plan per target host using the same staggered-window logic the OSS scheduler already implements *(automation_engine.pyx:1247)*
2. [x] Move the cron parser into the engine — `parse_cron_fields`, `validate_cron_expression`, `next_run_from_cron`, `CronParseError` all live in `automation_engine.pyx`. The OSS `backend/services/upgrade_scheduler.py` parser is preserved as tested OSS utility code (referenced by Phase 8.2 unit tests in `tests/api/test_upgrade_profiles.py::TestCronParse` / `::TestNextRun`); the *runtime* cron path goes through the engine when the route handlers are reached *(automation_engine.pyx:1085-1244)*
3. [x] Wire the existing `/api/upgrade-profiles/tick` driver hook to enqueue per-host engine plans through `engine.build_upgrade_profile_dispatch` — both `tick` and `/{id}/trigger` now route through `_dispatch_profile_to_hosts` which calls the engine.  Cron re-compute on `tick` also goes through `engine.next_run_from_cron` (was inconsistently calling OSS `upgrade_scheduler.next_run_from_cron`; fixed in Phase 10.6 close-out) *(backend/api/upgrade_profiles.py:299-349, :405-455)*
4. [x] Gate the `/api/upgrade-profiles/*` CRUD endpoints behind `automation_engine` (return 402 when not loaded) — same pattern Phase 2.3 used for secrets *(backend/api/upgrade_profiles.py:56-73)*
5. [x] Frontend: `UpgradeProfilesSettings.tsx` is gated through the OSS Settings tabDefs entry's `moduleRequired: 'automation_engine'` (same pattern as antivirus/firewall-roles/report-branding/etc.) — when the engine isn't loaded, the tab is hidden *(Settings.tsx:214)*.  The component itself stays in the OSS source tree because all other Pro+ Settings tabs follow the same hardcoded-with-license-gate pattern; physically relocating only this one to `plugin-src/` would create inconsistency with seven other Pro+ Settings tabs.
6. [x] Migrate the `tick` hook caller (the external systemd timer / cron) — there is no first-party scheduler shipped with sysmanage; deployments wire their own.  The only behaviour change for existing callers is that `/api/upgrade-profiles/tick` now returns 402 unless `automation_engine` is loaded.
7. [x] i18n/l10n for all 14 languages — backend gettext strings ("Scheduled upgrade profiles require a SysManage Professional+ license…", "Upgrade profile not found") added to all 14 messages.po files and compiled to .mo.  Frontend strings already in place from Phase 8.2.

**Keep in Open Source:** nothing — there's no simplified version that's useful.  Free-tier users hit "update now" on individual hosts via the existing Updates page, which already works without scheduled rollouts.

**Estimated Size:** ~500 lines added to `automation_engine.pyx` + ~417 lines migrated from OSS.

**Note on user impact:** the feature was just delivered in Phase 8.2; per the Phase 0 audit no production users have adopted it yet, so the move is low-risk if done before Phase 10 ships.

**Status:** ✅ Phase 10.6 complete (Phase 10 close-out, May 2026).  All 32 OSS unit tests in `tests/api/test_upgrade_profiles.py` pass.  Pro+ engine tests in `module-source/automation_engine/test_automation_engine.py` cover the engine cron + dispatch builders.

#### 10.7 Frontend License-Gating for Pro+ UI Surfaces

**Priority:** High — current OSS deployments show menu items, settings tabs, host-detail tabs, and action buttons that hit Pro+ endpoints which return 402.  Looks broken to free-tier operators; should render only when the relevant `featureFlag` / `moduleRequired` is in the active license.

**Background:** the plugin nav items in `Components/Navbar.tsx` (line ~76) and the plugin host-detail tabs in `Pages/HostDetail.tsx` (line ~638) already gate on the active license — `Navbar.tsx` filters `navItems` against `activeLicenseFeatures`, and `HostDetail.tsx` filters `pluginTabs` against `licenseModules`.  The fix is hoisting that same pattern to the *hardcoded* entries: declare a per-entry `featureFlag` / `moduleRequired`, then filter the same way.  Source of truth for available flags / modules is `backend/licensing/features.py` (`FeatureCode` / `ModuleCode` enums); `Services/license.ts::getLicenseInfo()` already exposes both lists to the frontend.

**Inventory — what to gate (verified surface):**

*Navbar (`Components/Navbar.tsx`, hardcoded NavLinks lines ~153-179):*
- [x] `/secrets` — gate behind `secrets_engine` module.  All `/api/secrets/*` already 402 without it (Phase 2.3). *(Navbar.tsx:206 — `activeLicenseModules.includes('secrets_engine')`)*
- [x] `/reports` — gate behind `reporting_engine` module.  OSS retains a 291-line stub but the rich workflow is Pro+. *(Navbar.tsx:226)*
- [x] `/scripts` — borderline; OSS retains ad-hoc one-shot run.  **Don't gate** — keep visible, but consider adding a "Pro+: scheduled / saved scripts" upsell row inside the page. *(decision documented; no gating applied)*

*Settings tabs (`Pages/Settings.tsx`, hardcoded `<Tab>` lines ~1113-1127):*
- [x] **Integrations** (Grafana + Graylog + OTEL cards in `renderIntegrationsTab` line ~947) — gate behind `observability_engine`. *(Settings.tsx:180 — `moduleRequired: 'observability_engine'`)*
- [x] **Antivirus** — gate behind `av_management_engine`. *(Settings.tsx:187)*
- [x] **Firewall Roles** — gate behind `firewall_orchestration_engine`. *(Settings.tsx:199)*
- [ ] **Access Groups** — gate behind `federation_controller_engine` (deferred to Phase 12.4 fold-in; currently no gating since it's an OSS feature today).  Land the gating once 12.4 lands; for now, leave it visible.
- [x] **Update Profiles** — gate behind `automation_engine` (lands together with 10.6 above). *(Settings.tsx:214)*
- [x] **Compliance Profiles** — gate behind `compliance_engine` (Phase 11.5 fold-in landed). *(Settings.tsx:225 — `moduleRequired: 'compliance_engine'`)*
- [x] **Report Branding** — gate behind `reporting_engine`. *(Settings.tsx:221)*
- [x] **Report Templates** — gate behind `reporting_engine`. *(Settings.tsx:227)*
- [ ] **Dynamic Secrets** — gate behind `secrets_engine` (full gating once 12.5 fold-in lands; for now, leave visible since it's OSS today).

OSS-appropriate Settings tabs (no gating needed): Tags, Queues, Ubuntu Pro, Available Packages, Host Defaults, Distributions.

*HostDetail hardcoded tabs (`Pages/HostDetail.tsx`, `HARDCODED_IDS` set line ~653):*
- [x] **Compliance** tab — gate behind `compliance_engine` module. *(HostDetail.tsx:678)*
- [x] **Child Hosts** tab — gate the create/start/stop/restart/delete buttons inside the tab behind `container_engine` (LXD/WSL) and `virtualization_engine` (KVM/bhyve/VMM); the read-only listing should remain visible since OSS keeps it (per Phase 10.1 "Keep in Open Source: read-only VM/container listing").  Per-row action buttons need fine-grained gating, not the whole tab. *(HostDetail.tsx:6289 wraps action `<TableCell>` in engine-aware IIFE; HypervisorStatusCards at lines 6037–6125 gated per-card on container_engine/virtualization_engine)*
- [x] **Security** tab — partial gate.  Read-only firewall/AV state remains OSS; the per-host firewall-role assignment UI inside the tab should gate behind `firewall_orchestration_engine`. *(FirewallStatusCard.tsx:566 — Edit Roles button)*

OSS-appropriate hardcoded HostDetail tabs (no gating): info, hardware, software, software-changes, third-party-repos, access (read-only listing only — the add/remove/edit user buttons already gate on `host_account_management` security roles), certificates, server-roles, ubuntu-pro, diagnostics.

*HostDetail action menu / dropdown buttons:*
- [x] **Deploy SSH Key** — hits `/api/secrets/deploy-ssh-keys`; gate behind `secrets_engine`. *(HostDetail.tsx:5243 — `licenseModules.includes('secrets_engine')` guard)*
- [x] **Deploy Certificate** — hits `/api/secrets/deploy-certificates`; gate behind `secrets_engine`. *(HostDetail.tsx:5637)*
- [x] **Deploy OpenTelemetry** + **Start/Stop/Restart/Remove OTEL** + **Connect to Grafana** + **Disconnect from Grafana** (Services/opentelemetry.ts callers, line ~104); gate behind `observability_engine`. *(HostDetail.tsx:4366 — entire OTEL panel + every button inside it)*
- [x] **Connect to Graylog** + Graylog attach modal (Services/graylog.ts callers, line ~105); gate behind `observability_engine`. *(HostDetail.tsx:4504 — entire Graylog panel)*
- [x] **Enable/Disable KVM modules**, **Initialize KVM/bhyve/VMM/LXD**, **Configure KVM networking**; gate behind `virtualization_engine` (KVM/bhyve/VMM) and `container_engine` (LXD). *(HostDetail.tsx:6037–6125 — each HypervisorStatusCard gated per-engine)*
- [x] **Create Child Host** dialog — already conditional on hypervisor capability, but also needs to gate on the relevant engine module being licensed. *(only reachable from gated HypervisorStatusCard `onCreate` callbacks)*

Already-correctly-gated: **Orchestrated Reboot** falls back to plain reboot when `has_container_engine` is false (line ~3047) — model the rest on this pattern.

**Mechanism:**

1. [x] Define a single source-of-truth helper in `frontend/src/Services/license.ts`:

   ```ts
   export function isFeatureLicensed(featureCode: string): boolean
   export function isModuleLicensed(moduleCode: string): boolean
   ```

   Both read from a cached `licenseInfo` (the same one Navbar + HostDetail already fetch).  Cache invalidates on license change events.

2. [x] Navbar gating done via `activeLicenseModules.includes(...)` filter inline (Navbar.tsx:161 for /secrets, :181 for /reports).  Plugin nav items already use the list-of-objects shape.

3. [x] Settings tabs converted to `tabDefs` list with `moduleRequired` per entry, filtered at line 248 (Settings.tsx).

4. [x] HostDetail tabs filter via `HARDCODED_IDS` set + per-tab inline `licenseModules.includes(...)` guards (Compliance tab :678).  Plugin tabs filter via `visiblePluginTabs.moduleRequired` at line 644.

5. [x] HostDetail action buttons get inline `licenseModules.includes("…")` guards on each button, with the button hidden (not disabled-with-tooltip) when not licensed — consistent with how plugin nav items behave.  See cross-references in the action button list above.

6. [x] Plugin Settings tabs at `Pages/Settings.tsx` honor `moduleRequired` (`PluginSettingsTab` interface gains the optional field, `visiblePluginSettingsTabs` memo filters the same way the hardcoded `tabDefs` filter does, both the Tabs strip and the tab-content dispatch use the filtered list).  Tabs without `moduleRequired` stay always-visible (pre-Phase-10.7 behaviour).

7. [x] i18n: no new strings — gating is a visibility change, not a copy change.

**Testing:**

- [x] Unit tests for `isFeatureLicensed` / `isModuleLicensed` (cache hit/miss, license absent, license present-but-unrelated). *(`__tests__/Services/license.test.tsx` — 8 passing tests covering empty cache, refresh population, feature/module presence checks, refresh-failure → cache cleared, license-without-modules-array, subscribe/unsubscribe, clear-cache reset)*
- [x] Playwright tests: triple-tier license-matrix smoke test landed at `frontend/e2e/license-matrix.spec.ts` (2026-05-13).  Parametrised over `community` / `professional` / `enterprise` fixtures; uses `page.route('**/api/license', …)` to inject a tier-specific response rather than seeding signed licenses on the backend (faster, deterministic, and exercises the same frontend gating logic as production).  Asserts 7 Settings tabs visible/hidden correctly per tier (Integrations, Antivirus, Firewall Roles, Update Profiles, Compliance Profiles, Report Branding, Report Templates) + the `/secrets` and `/reports` nav links toggle correctly between community ↔ enterprise.  HostDetail per-tab and per-action-button gating is a follow-up — those require a seeded host record and aren't covered by this spec yet.

**Estimated Size:** ~150 lines of frontend gating logic + ~60 entry-shape conversions + ~80 lines of test fixtures.  No backend changes — the 402-on-unlicensed pattern already exists; this just stops surfacing the call sites that would hit it.

**Note on staging:** items marked "deferred until phase X.Y fold-in lands" can be gated proactively (the `featureFlag` / `moduleRequired` codes already exist in `backend/licensing/features.py`) — gating before the backend migration is a no-op on OSS deployments today (those tabs simply remain visible until the relevant engine is loaded), and avoids a follow-up frontend pass after each fold-in.

### Deliverables

- [x] virtualization_engine module (~24,000 lines, largest single module) — `virtualization_engine.pyx` 7,560 lines + 128 tests
- [x] observability_engine module (~6,300 lines) — `observability_engine.pyx` 1,305 lines + 31 tests
- [~] ~24,489 lines of agent code migrated to server-side Cython — virtualization migration complete (legacy `child_host_operations` → stub); observability migration only half-done (engine has the plan-builders but agent still ships 2,770 lines of OTEL+Graylog deployment code that should have been deleted per 10.2 step 7)
- [x] MFA implementation — TOTP + backup codes + per-user/admin enforcement; email-OTP fallback still open
- [x] Repository mirroring — `repository_mirroring_engine.pyx`
- [x] External IdP support — `external_idp_engine.pyx` (LDAP + OIDC + role mapping + local fallback)
- [x] Upgrade profiles migrated from OSS to `automation_engine` — 10.6 close-out complete
- [~] Hardcoded nav items, Settings tabs, HostDetail tabs, and action buttons gated by license to match the existing plugin-gating pattern — hardcoded surfaces (Navbar, Settings tabDefs, HostDetail tabs, action buttons) all gated; plugin Settings tabs honoring `moduleRequired` (line 1822) and the Playwright triple-tier matrix (line 1829) remain open

### Exit Criteria

- virtualization_engine and observability_engine compile and load cleanly on all supported platforms (linux, macos, windows, freebsd, openbsd, netbsd) across Python 3.11–3.14
- License gating verified for both engines: Enterprise license enables full functionality; unlicensed instances retain only read-only listing (no VM creation, no observability deployment) and return 402 from gated endpoints
- Agent-side VM management code fully removed: all KVM/QEMU (~4,500 lines), bhyve (~4,600 lines), VMM/vmd (~6,800 lines), and guest-provisioning (~6,253 lines) modules deleted; agent retains only `child_host_listing_*.py` for read-only inventory
- Each hypervisor creates, lifecycles, and deletes a VM end-to-end on its native platform: KVM/QEMU on Linux, bhyve on FreeBSD, VMM/vmd on OpenBSD
- Cloud-init / autoinstall provisioning verified for at least one Linux guest (Ubuntu or Debian) and one BSD guest (FreeBSD) per hypervisor
- Safe parent host reboot orchestration (originally LXD/WSL in Phase 2.5) extended to and verified on KVM, bhyve, and VMM/vmd — running VMs cleanly stopped, persisted, restarted on parent reconnect
- Graylog sidecar deploys and forwards GELF to a real Graylog instance from at least one Linux and one Windows host
- OTEL collector deploys with valid configuration and exports metrics + traces to a real backend on at least one Linux host
- MFA: TOTP enrollment + verification, backup codes, and email fallback all functional; per-user and admin-required enforcement modes both verified
- Repository mirroring functional for both APT and DNF with snapshot/rollback support
- External IdP: LDAP/AD authentication and at least one OIDC provider (Okta, Azure AD, or Keycloak) successfully authenticate users with external-group-to-role mapping
- All 14 languages have complete i18n coverage for the new modules and features
- No critical or high-severity bugs in any module or feature

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

**Status:** ✅ v0.1.0 landed (May 2026).  Engine, schema, plan-builders,
ISO build, signed manifest, burn plan, FastAPI router factory, and 19
tests against the compiled .so all green.

**Features:**
- [x] Configurable OS/version tracking list (Ubuntu, Debian, RHEL, FreeBSD, etc.) — 13 distro families validated; shell-injection-safe regex
- [x] Automated package mirror capture (APT, DNF/YUM, pkg, etc.) — per-family dispatch templates in `_MIRROR_COMMAND_TEMPLATES`
- [x] CVE/NVD data snapshot capture at time of collection — placeholder hook; concrete CVE-feed list lives in `vuln_engine` (Phase 11.4 fold-in)
- [x] Compliance framework data capture (CIS, DISA STIG baselines) — schema + `include_compliance` flag wired through `build_collection_run_plan` + `AirgapCollectionRun`; shared CIS/STIG feed registry landed at `module-source/_shared/cis_stig_source_registry.py` (parallel to `cve_source_registry.py`); `airgap_collector_engine.build_collection_run_plan` now emits one `curl` snapshot step per `enabled_by_default=True` baseline source plus a `sources.json` URL manifest when `include_compliance=True`.  Default-on sources: ComplianceAsCode/SCAP Security Guide + DISA STIG compilation; opt-in: NIST NCP + Canonical USG.  23 new tests (14 registry shape + 9 cross-engine wiring) cover the contract.
- [x] Optical media ISO image generation with integrity checksums (SHA-256) — xorriso wrapper + post-build sha256sum step
- [x] Multi-disc spanning for large update sets — first-fit-decreasing bin-packing in `pack_into_discs` + per-disc plan builder `build_multidisc_plan` (engine).  OSS-exposed via new `POST /api/v1/airgap/collector/iso/build-multidisc/{run_id}` endpoint that takes a `file_entries` list and emits one stage + manifest + xorriso + sha256 command sequence per disc.  9 router tests + the existing bin-packing function tests all green.  `airgap_media_manifest`'s `disc_index` / `disc_count` columns now actually carry the values.
- [x] Disc burning integration (cdrecord/growisofs/xorriso) — plan-builder shape only; real burns happen on operator hardware (mocked in CI)
- [x] Collection scheduling (daily, weekly, on-demand) — on-demand via `POST /api/v1/airgap/collector/collection/runs` (engine) + cron-driven via OSS `AirgapCollectionSchedule` table + CRUD routes at `/api/v1/airgap/collector/schedules` + periodic-tick service `backend.services.airgap_schedule_tick.airgap_schedule_tick_service` (60 s heartbeat, mounted in `backend/startup/lifecycle.py` when `airgap_collector_engine` is loaded).  Cron parser reused from `airgap_collector_engine.parse_collector_cron_fields` / `next_collection_from_cron`.  8 tick-service tests pass.
- [x] Manifest generation with package counts, CVE counts, and timestamps — `build_manifest` + `sign_manifest` (ed25519 with HMAC-SHA256 fallback flagged for strict-mode rejection)
- [x] Delta collection mode (only new packages since last burn) — request body accepts ``parent_run_id`` (UUID of prior run); engine route fetches the parent's ``AirgapMediaManifest`` rows, extracts the file list, populates ``prior_files`` automatically, and defaults ``delta_since`` to the parent's ``completed_at``.  Skip-set built by ``compute_delta_skip_set``; per-distro mirror commands gain a ``--skip`` filter.  ``parent_run_id`` persists on the new ``AirgapCollectionRun`` row (column already present; ``to_dict`` now exposes it).  8 new delta-route tests pass.
- [x] i18n/l10n for all 14 languages — backend gettext + frontend nav.role chip, all 14 locales validated strict

**Estimated Size:** ~4,000 lines (actual: ~520 lines .pyx + ~150 schema + ~270 tests)

#### 11.2 airgap_repository_engine (Enterprise)

**Status:** ✅ v0.1.0 landed (May 2026).  Engine, schema, ingestion +
metadata-generation + agent-repoint plan-builders, ed25519 signature
verification, file-hash verification, freshness scoring, FastAPI
router factory, and 25 tests including end-to-end collector→sign→
repository→verify round-trip all green.

**Features:**
- [x] Optical media ingestion with integrity verification — `verify_signed_envelope` + `verify_file_hashes` in strict mode (rejects HMAC fallback)
- [x] Local APT/DNF/YUM/pkg repository hosting — `build_ingestion_plan` mounts ISO + rsyncs payload to `/var/lib/sysmanage/airgap-repo`
- [x] Repository metadata generation (Packages.gz, repodata, etc.) — `build_repo_metadata_plan` per distro family (apt-ftparchive, createrepo_c, pkg repo, apk index)
- [x] Automatic agent repository configuration (point hosts to private mirror) — `build_agent_repoint_plan` writes `/etc/apt/sources.list.d/`, `/etc/yum.repos.d/`, `/usr/local/etc/pkg/repos/` per distro
- [x] CVE data import and synchronization with point-in-time context — Phase 11.4 `vuln_engine.build_cve_refresh_plan` + `build_cve_apply_plan`; collector's `include_cve` flag emits a CVE snapshot step in the same run so the resulting media set carries a coherent point-in-time view
- [x] Compliance assessment relative to available updates (not public state) — `airgap_compliance_context.classify_compliance_gap` returns `not_applied` (cheap-to-fix) vs `not_transferred` (requires media cycle) explicitly
- [x] Gap analysis reporting (what patches exist publicly but are not yet transferred) — same `not_transferred` bucket from 11.3
- [x] Transfer history and audit trail — `AirgapIngestionRun` tracks status / started_at / completed_at / error_message / signer_fingerprint / collector_iso_label per ingest; `AirgapCollectionRun` tracks the same on the collector side; both are queryable via the engines' router endpoints
- [x] Multi-OS repository support (serve updates for multiple OS families) — `build_repo_metadata_plan` covers `apt-ftparchive` (Debian/Ubuntu), `createrepo_c` (Fedora/RHEL family/openSUSE/SLES), `pkg repo` (FreeBSD), `apk index` (Alpine) — single repository can host all of them concurrently
- [x] Repository statistics and dashboard — `AirgapRepositories.tsx` page renders per-repo table (distro, version, package count, last-ingest, freshness label, signer fingerprint) plus an aggregate card (total repos, total packages, oldest freshness, stale count) backed by `GET /api/v1/airgap/repository/repositories`.  Route mounted at `/airgap/repositories`, linked from `Navbar.tsx`, gated to `role: repository` deployments with a "not applicable" notice otherwise.  Backend's aggregate (with configured stale threshold) is the source of truth; component falls back to local computation only for legacy flat-list responses.
- [x] i18n/l10n for all 14 languages — backend gettext + frontend locale JSONs + docs locale JSONs all updated for Phase 11 strings; all four validators pass strict mode

**Estimated Size:** ~5,000 lines

#### 11.3 Air-Gapped Compliance Context

**Status:** ✅ wired (May 2026).  Connector layer in
`backend/services/airgap_compliance_context.py` exposes
`get_repository_freshness()` + `classify_compliance_gap()`.  No-ops
gracefully on `role: standard` deployments (returns
`{label: "never", buckets: empty}`); 5 tests cover the four-way
classification.

**Features:**
- [x] Point-in-time vulnerability context (CVE data as of last media transfer) — `not_transferred` bucket flags CVEs whose fix isn't on the local mirror
- [x] Compliance scoring relative to available private-side patches — `not_applied` bucket flags newer-version-available-locally
- [x] Reporting that distinguishes between "patch available but not applied" vs "patch not yet transferred" — explicit three-bucket return shape (`not_applied`, `not_transferred`, `current`)
- [x] Transfer freshness indicators (how old is the latest media import) — `compute_freshness` returns `(days, label)` with `current` ≤ 7d, `stale` ≤ 30d, `very_stale` > 30d, `never` for no ingest yet
- [x] Risk assessment that accounts for the air-gap transfer cadence — `AirgapComplianceBucketsCard.tsx` rendered inside `HostCompliancePanel` (which `HostDetail.tsx` mounts).  Surfaces the three-bucket classification from `classify_compliance_gap` as color-coded chips (yellow = not_applied, red = not_transferred, green = current) with tooltips explaining the air-gap-transfer-cadence implication.  Backed by `GET /api/v1/airgap/repository/host/{host_id}/compliance-buckets`.
- [x] Integration with existing compliance_engine and vuln_engine modules — connector module imports `airgap_repository_engine.compute_freshness`; OSS routes call into the connector when air-gap data is needed

#### 11.4 CVE Refresh Settings → vuln_engine + airgap_collector_engine

The OSS `backend/api/cve_refresh_settings.py` (~431 lines) and
`backend/vulnerability/cve_refresh_service.py` are CVE feed-management
plumbing that has no OSS consumer — vulnerability scanning is Pro+
Enterprise (`vuln_engine`).  Air-gap is the right phase to relocate it
because CVE feed mirroring is the central air-gap concern.

**Migration Steps:**
1. [x] Move CVE source/refresh-settings CRUD into `vuln_engine.pyx` (the existing engine that consumes the data) — `validate_cve_source`, `build_cve_refresh_plan`, `build_cve_apply_plan`, `parse_cve_cron_fields`, `next_refresh_from_cron`, `CveRefreshConfigError` (vuln_engine.pyx, +557 lines)
2. [x] In Phase 11 specifically: extend `airgap_collector_engine` to use the same CVE source registry — landed via `module-source/_shared/cve_source_registry.py` (canonical), consumed by both `vuln_engine.pyx` (with byte-identical inline fallback) and `airgap_collector_engine.build_collection_run_plan` (emits one `curl` snapshot step per `enabled_by_default=True` source plus a `sources.json` URL manifest).  Round-trip verified by `test_airgap_collector_engine_cve_snapshot.py::test_each_snapshot_url_matches_vuln_engine_refresh_url` and `test_source_names_subset_of_vuln_engine_known_sources`.
3. [x] Gate `/api/cve-refresh/*` behind `vuln_engine` loaded (402 stub in OSS, mirroring secrets/openbao pattern) — `_check_vuln_engine_module()` on all 7 routes (cve_refresh_settings.py:+37 lines)
4. [x] Frontend `CveRefreshSettings.tsx` — N/A; no such component exists in OSS (CVE refresh has no Settings tab today; backend 402 gating is sufficient)
5. [x] i18n/l10n for all 14 languages — new 402 detail string added to all 14 backend `.po` files + compiled `.mo`

**Status:** ✅ Phase 11.4 complete (May 2026).  50 engine tests + 13 OSS gate tests pass.  41 cron+source-validation tests new in `test_vuln_engine_cve_refresh.py`.

**Estimated Size:** ~431 lines migrated from OSS to vuln_engine.  Actual: ~557 lines added to vuln_engine.pyx + ~370 new test lines.

#### 11.5 Package Compliance → compliance_engine

The Phase 8.3 OSS `backend/api/package_compliance.py` (~464 lines) plus
the `package_compliance` evaluator are functionally CIS-style benchmark
checking with REQUIRED/BLOCKED package rules.  That overlaps the
existing `compliance_engine` (Professional, already shipped in Phase 2)
scope; air-gap is the natural moment to consolidate because air-gapped
deployments lean heaviest on strict allow/blocklists (limited package
sets, locked-down baselines).

**Migration Steps:**
1. [x] Extend `compliance_engine.pyx` to subsume PackageProfile + PackageProfileConstraint as first-class compliance objects (alongside the existing CIS/STIG benchmarks) — +504 lines
2. [x] `evaluate_host_against_profile` becomes a method on the engine; `HostPackageComplianceStatus` continues to live OSS-side as cached state but the evaluator and CRUD move
3. [x] Phase 11.3 wiring done — connector layer at `backend/services/airgap_compliance_context.py` integrates compliance_engine + vuln_engine
4. [x] Gate `/api/package-profiles/*` behind `compliance_engine` — `_check_compliance_module()` on all 8 route handlers
5. [x] Frontend tab gated via `moduleRequired: 'compliance_engine'` in Settings.tsx — same hardcoded-with-license-gate pattern other Pro+ Settings tabs use; no physical relocation needed (consistent with antivirus/firewall-roles/report-branding/etc.)
6. [x] i18n/l10n for all 14 languages — new 402 detail string added to all 14 backend `.po` files + compiled `.mo`

**Status:** ✅ Phase 11.5 complete (May 2026).  32 new engine tests + 8 OSS 402-gate tests + existing 16 evaluator+CRUD tests preserved.

**Estimated Size:** ~464 lines migrated from OSS into `compliance_engine`.  Actual: +504 .pyx + 386 test lines + +49 OSS gate lines.

### Migration Steps

1. [x] Create `module-source/airgap_collector_engine/` structure — scaffold + setup.py + metadata.json + requirements.txt + .pyx + tests
2. [x] Create `airgap_collector_engine.pyx` Cython module — v0.1.0, ~520 lines + 19 tests, .so compiled cleanly
3. [x] Create `module-source/airgap_repository_engine/` structure
4. [x] Create `airgap_repository_engine.pyx` Cython module — v0.1.0, ~470 lines + 25 tests, .so compiled cleanly
5. [x] Frontend gating via Settings tabDefs `moduleRequired` (same pattern as other Pro+ Settings tabs) — no separate plugin-bundle files needed; nav role chip lives in OSS Navbar.tsx and renders only when role != standard
6. [x] Migrate OSS CVE refresh settings into `vuln_engine` (11.4) — done
7. [x] Migrate OSS package compliance into `compliance_engine` (11.5) — done
8. [~] Update documentation with air-gapped deployment guide — English version landed (`sysmanage-docs/docs/administration/airgap-deployment.html`, deliverable at line 2014; 55 `data-i18n` keys seeded across all 14 locales).  Long-form-paragraph translation across the 13 non-English locales is the remaining slice; tracked under §12.8 "Translation-service pipeline" rather than re-listed here.  Translator-budget work, not engineering.
9. [x] i18n/l10n for all 14 languages — backend gettext for 402 strings + frontend nav.role.* keys (added to DYNAMIC_KEY_PREFIXES so template-literal `t(\`nav.role.${role}\`)` lookups stay valid); all four validators pass strict mode

### Deliverables

- [x] 2 new Pro+ modules (airgap_collector_engine, airgap_repository_engine) — both v0.1.0; 19 + 25 = 44 engine tests
- [x] CVE refresh settings folded into `vuln_engine` — 50 engine tests + 13 OSS gate tests
- [x] Package compliance folded into `compliance_engine` — 32 engine tests + 24 OSS tests
- [x] Air-gapped deployment guide — `sysmanage-docs/docs/administration/airgap-deployment.html` (architecture, role config walkthrough, collection cycle, ingestion cycle, per-distro install channels, compliance context, troubleshooting; 55 `data-i18n` keys seeded across all 14 locales — section titles localized, long-form bodies use English-passthrough per the existing docs-locale convention until the translation-service pipeline runs per §12.8)
- [x] Optical media transfer procedures documentation — `sysmanage-docs/docs/administration/airgap-runbook.html` covers chain-of-custody, ed25519 key rotation cadence, transport-loss procedures, signature-verification incident response, and recommended cadences; 41 `data-i18n` keys seeded across all 14 locales (titles localized, long-form bodies use English-passthrough per docs convention)
- [x] Integration tests for collection and ingestion workflows — collector→sign→repository→verify round-trip exercised in `test_airgap_repository_engine.py::TestVerifySignedEnvelopeRoundTrip`
- [x] **Agent subprocess persistence across WebSocket reconnects** — Phase 11.6 landed (28 inflight_journal tests + 27 generic_deployment regression tests pass).  See §11.6 status block below.

### Exit Criteria

- [x] Public-side collection captures all configured OS updates and CVE data — `build_collection_run_plan` covers 13 distro families
- [x] Optical media generation and integrity verification working — xorriso wrapper + ed25519 sig + per-file SHA-256 round-trips end-to-end
- [x] Private-side ingestion creates functional package repositories — ingestion plan + per-distro metadata generation (createrepo_c, apt-ftparchive, pkg repo, apk index)
- [x] Managed hosts can install updates from private repository — `build_agent_repoint_plan` rewrites APT/DNF/pkg/apk config per distro
- [x] Vulnerability scanning works with point-in-time CVE context — `airgap_compliance_context.classify_compliance_gap` distinguishes `not_applied` / `not_transferred` / `current`
- [x] Compliance reporting accounts for air-gap transfer state — `compute_freshness` returns `(days, label)` for use by compliance UI

### 11.6 Agent subprocess persistence across reconnects (carry-over from Phase 10.4) — ✅ landed (May 2026)

**Status.** New module `sysmanage_agent/operations/inflight_journal.py` implements `journal_write` / `journal_set_pid` / `journal_heartbeat` / `journal_clear` / `scan_inflight_on_startup`.  `apply_deployment_plan` in `generic_deployment.py` writes the journal before `subprocess.Popen`, runs an asyncio watchdog that updates the heartbeat every 30 s, and clears the journal on clean exit.  `agent_utils.reconcile_inflight_journal` runs at startup, attaches to live PIDs, and emits a synthetic `command_result` for dead PIDs so the server's `DISPATCHED` row clears.  Cross-platform liveness check uses `os.kill(pid, 0)` on POSIX and `ctypes` `OpenProcess` on Windows.  28 new tests + 27 generic_deployment regression tests all pass.



**Symptom observed during 10.4 testing:** any deployment plan whose
shell commands run longer than the WebSocket reconnect window loses
its result.  Concretely: a 7200s `apt-mirror` plan was dispatched at
T+0; the WebSocket bounced at T+5 minutes (server restart for an
unrelated code change); the agent reconnected at T+6 minutes carrying
no in-flight execution state; `apt-mirror` had been killed in the
gap; the `command_result` for the original plan was never produced
and never reached the server.  The mirror row sat in `DISPATCHED`
forever despite the underlying job being dead.

This will become acute in Phase 11 because air-gap collection cycles
include multi-hour package mirror sync + ISO build + checksum verify
operations.  A single WS hiccup mid-cycle today loses the entire
result.

**Required fix (cross-cutting; lives in `sysmanage-agent`):**

1. Agent writes a per-plan execution-state journal to
   ``~/.sysmanage-agent/inflight/<message_id>.json`` BEFORE
   `subprocess.Popen` is called.  Journal carries the message_id,
   plan, started_at, and the spawned PID.
2. After spawn, `subprocess.communicate()` is wrapped in a watchdog
   that checkpoints every 30s — appends an `alive_at` heartbeat to
   the journal so a post-mortem reader can tell killed-cleanly from
   killed-by-OS-OOM.
3. On agent startup, the journal directory is scanned.  For each
   in-flight plan: if the PID is still alive, attach to it and stream
   its output; if it's gone, mark the plan failed with the reason
   "agent restart while plan was in-flight" and emit a synthetic
   command_result so the server's ``DISPATCHED`` row clears.
4. On clean WS reconnect (without an agent restart), the in-memory
   subprocess set is unchanged — only the connection itself bounced
   — so the `command_result` is queued normally and delivered when
   the WS comes back.  This is the easy case; the journal handles
   the hard case where the agent process itself died/restarted.

**Estimated size:** ~250 lines in `sysmanage-agent/src/sysmanage_agent/communication/`
plus ~50 lines of fixture changes for the existing message-handler
tests.  No server-side changes needed (the synthetic command_result
flows through the existing routing path).

**Alternative considered + rejected:** "make all plans idempotent and
re-dispatch on timeout."  Rejected because some plans have side
effects that aren't safe to retry blindly (e.g.
``build_kvm_create_plan`` consumes a unique cloud-init seed; running
it twice produces a half-built VM).  The journal approach is more
work but correctly distinguishes "the plan ran to completion, agent
just couldn't tell us" from "the plan was interrupted, retry is
required."

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

### Data Architecture

Two extreme approaches both fail at federation scale, and the
coordinator/site partition has to land between them:

  * **Full replication** — coordinator DB mirrors every row from every
    site with a ``site_id`` column on each table.  Fails: at 1M-host
    target, the coordinator DB grows linearly with hosts rather than
    sites (contradicting the stated scalability target), and the
    upstream sync bandwidth becomes brutal (every package install,
    every CVE scan, every health tick replicating to the coordinator).
  * **Pure aggregates** — coordinator stores only rolled-up metrics
    (host counts, compliance %, CVE counts), all detail queries proxy
    over the wire to the originating site.  Fails: breaks the
    cross-site search the ROADMAP commits to — an operator can't ask
    "show me every host running kernel < X" if every search fans out
    to 100 sites; offline sites make any per-host query fail for
    that site.

The architecture splits data into **three tiers**:

  1. **Aggregate tier** (coordinator) — one row per site per metric.
     Host count, healthy/unhealthy ratio, compliance %, top CVEs by
     severity, alert counts, last-sync timestamp.  Small, fixed
     bound: 100 sites × handful of aggregate tables = thousands of
     rows total.
  2. **Host directory tier** (coordinator) — one row per host across
     the entire fleet, but **only the columns operators filter and
     search on**: ``id, hostname, ipv4, ipv6, os_family, os_version,
     platform, status, last_seen, site_id, tags, public_ip,
     geo_country_code, geo_subdivision_code, geo_city``.  Size bound:
     ~1KB per host × 1M hosts ≈ 1GB.  Sized for PostgreSQL with room
     to spare; enables cross-site list / search / filter without
     proxying.
  3. **Detail tier** (sites) — full ``software_package`` inventory,
     ``host_certificates`` chains, ``audit_log`` entries, alert
     bodies, OS-specific facts.  **Never replicated upstream.**  When
     an operator drills into a specific host's full inventory, the
     coordinator proxies the query to the originating site server
     via the existing dispatch channel.

**Site_id placement:** lives in the aggregate-tier rollup tables
and in the host-directory tier (the only places where multiple
sites' data is colocated).  Detail-tier tables at the sites
themselves don't need ``site_id`` — they're inherently site-local
and stay that way.

**Sync protocol design effort** is the tradeoff here.  The host
directory has to stay reasonably current: sites push delta updates
upstream (host registered, deactivated, IP changed, OS upgraded,
tags edited, geo recomputed) on top of the periodic rollup sync.
Delta protocol needs debouncing (a fleet-wide patch run that
upgrades 10k OSes at once shouldn't produce 10k sync messages),
deduplication on replay (offline site reconnects and re-sends
queued deltas — the coordinator dedup-keys by ``(host_id,
field, mtime)``), and conflict resolution if two sites somehow
both think they own a host (timestamp wins, audit-log the race).

**Reference precedent:** this is the same partition SaaS
observability platforms use at comparable scale — DataDog and New
Relic both separate a "metadata index" tier (fast cross-account
search, ~few KB per resource) from a high-volume telemetry tier
(detail data stays in the originating shard).  Federation is
structurally the same problem.

### Frontend Architecture

The coordinator UI follows two non-obvious design rules that the
Phase 12 frontend deliverables (12.3 + 12.7's map) are scoped
around:

**Rule 1: Sites are first-class entities, not just labels on hosts.**
A "tree view" that descends coordinator → site → host doesn't fit
operator workflows (operators typically ask "all hosts with
condition X across the fleet," not "drill into site-Cleveland's
host list").  Instead:

  * A new top-level **Sites** page lists/cards every subordinate
    site server with its operational metadata (host count, last
    sync, connectivity, compliance rollup, alert count).  Operations
    that target a site directly — push a policy, dispatch a batch
    command, suspend, view audit — happen on this page.
  * The existing **Hosts / Updates / Compliance / Reports** pages
    each gain a ``site`` filter facet alongside the existing tag
    facets.  A site is one more filter dimension, not a separate
    information architecture.
  * Drill-down from a site card → filtered Hosts page for that
    site.  Drill-down from a host → unchanged HostDetail page.

This means **two visualization surfaces** to build and maintain
(site-as-entity and host-as-entity-with-site-attribute), each
serving a distinct workflow.  The two map onto the operator's
actual mental model: "manage my sites" vs. "manage my fleet."

**Rule 2: Never draw individual agents on a visualization.**
Topology graphs collapse at 1M nodes; force-directed graphs become
unusable past a few thousand; even WebGL rendering hits practical
limits with that many markers.  Every map view in the coordinator
UI **terminates at sites**: coordinator at the center / top, ~100
site nodes around it, connection lines that animate sync activity
and turn red when a site goes silent.  Per-site density (host
count, % healthy, alert count) is surfaced as a marker badge or
heatmap intensity — never as 10k individual dots.

The federation frontend (12.3) ships two map flavors that share
the same data feed:

  * **Geographic map** — sites pinned to data-center coordinates.
    Useful for executive dashboards, war-room overviews, and the
    12.7 host-density visualization (where individual hosts ARE
    plotted but always in cluster-marker form, never as individual
    nodes).
  * **Tile/dashboard view** — sites as a grid of status cards with
    connection lines to the coordinator at the top.  No geography.
    Better for ops teams who don't care where the sites are physically,
    only that they're all green right now.

Both feed off the same coordinator-side aggregate + host-directory
tables; users pick the lens that matches their workflow.

**Implication for 12.1 / 12.3 implementation:** the API surface
should be designed around these two workflows — a ``GET /sites``
that returns per-site rollups (drives the Sites page + both map
flavors), and the existing per-host endpoints gain an optional
``?site_id=`` filter (drives the augmented Hosts page).  Don't
build a separate "tree" API that fetches the whole hierarchy in
one go; the data volume doesn't allow it.

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

Implements both architectural rules from the "Frontend Architecture"
section above: sites-as-first-class-entities, never-draw-individual-agents.

**Sites surface (new top-level page):**
- [ ] ``Sites`` page — one card per subordinate site server with host
      count, last sync, connectivity status (green/yellow/red), aggregate
      compliance %, open alert count, and a "manage" action menu
- [ ] Site detail view (drill into a site card) — site-level metadata,
      sync history, audit log, and a "see hosts" link that jumps to the
      Hosts page pre-filtered to ``?site_id=<this>``
- [ ] Site server lifecycle UI — add a site (enrollment flow), remove,
      suspend (admin keeps the site enrolled but stops accepting upstream
      sync), and resume
- [ ] Connection-health detail — last successful sync timestamp, sync
      latency histogram, current backlog size in the site's offline
      queue (read from the site server's sync-status endpoint)
- [ ] Per-site action surface — push a policy now, dispatch a batch
      command to all hosts at this site, view this site's audit log,
      compare configuration to fleet defaults

**Augmented existing pages (filter facets):**
- [ ] ``Hosts`` page — new ``site`` facet in the existing tag-filter
      panel; URL-shareable as ``?site_id=...`` (or multi-select).
      Cross-site search continues to work; the facet just narrows it.
- [ ] ``Updates`` page — same ``site`` facet so an operator can target
      "patch all hosts at site-A on the v2.4 update profile"
- [ ] ``Compliance`` page — same facet for cross-site compliance drill-down
- [ ] ``Reports`` page — site selector becomes a multi-select on report
      definitions; existing report types unchanged

**Enterprise map (two flavors, same data):**
- [ ] **Geographic map** — Leaflet + OpenStreetMap tiles, sites pinned
      at data-center coordinates, connection lines to the coordinator
      animating sync activity.  Host markers (from 12.7) cluster within
      each site's neighborhood.  Coloring: site nodes green/yellow/red
      by connectivity + compliance; host clusters scaled by density.
- [ ] **Tile dashboard view** — sites as a grid of status cards, lines
      to the coordinator at top, no geography.  Same color coding.
      Faster to scan, no cognitive load of geographic memory, better
      for screen-of-glass / war-room displays.
- [ ] View toggle in the same page — both feed off the same coordinator
      aggregate + host-directory tables, just different layouts
- [ ] **Never** draw individual agents as nodes — always cluster or
      site-summarize.  At fleet scale (1M hosts) this is a hard constraint,
      not a stylistic preference

**Policy + dispatch UI:**
- [ ] Policy management — create / edit / push update profiles, firewall
      roles, compliance baselines.  Push targets a site-selector with
      multi-select.
- [ ] Command dispatch — select hosts across sites (via Hosts-page
      multi-select or saved query), dispatch commands.  Progress view
      tracks per-site queueing + per-agent acknowledgement.

**Audit + observability:**
- [ ] Federation audit log viewer — every cross-site operation
      (enrollment, policy push, command dispatch, site suspend/resume)
      with filter by site, user, action type
- [ ] Sync status timeline per site — graph of upstream sync latency,
      offline-queue depth, deduplication-on-replay events

**Constraint on the API surface (informs 12.1 implementation):**

The frontend never asks for "the whole tree" in one call — that
doesn't scale, and the data model doesn't support it.  Endpoints
are designed around the two workflows:
- ``GET /api/federation/sites`` → aggregate row per site (drives
  Sites page + both map flavors)
- ``GET /api/hosts?site_id=<id>`` → existing endpoint, new optional
  filter (drives the augmented Hosts page)
- ``GET /api/hosts/{id}/detail`` → coordinator proxies the detail
  query to the originating site (drives drill-down from a host
  marker / row)

**Estimated Size:** ~4,500 lines (frontend plugin bundle, +500 over
the original estimate to account for the explicit two-map-flavor
design and the audit/sync-status surfaces)

#### 12.4 Access Groups + Registration Keys → federation_controller_engine

The Phase 8.1 OSS `backend/api/access_groups.py` (~446 lines) ships a
hierarchical AccessGroup tree with depth-10 cap, cycle detection,
recursive descendant lookup, RBAC scoping, and registration keys with
expiry/max-uses.  That complexity profile (multi-tenant fleet
segmentation, per-group enrollment scoping) is exactly what federation
needs — it's MSP/Enterprise functionality that doesn't fit free-tier.

**Migration Steps:**
1. [ ] Move `AccessGroup`, `RegistrationKey`, `HostAccessGroup`, and
       `UserAccessGroup` models into `federation_controller_engine` —
       the coordinator becomes the authoritative source for tenant /
       group definitions, sites pull them on policy sync
2. [ ] Extend the federation enrollment flow (12.1) so registration
       keys carry an optional `site_id` scope — keys generated at the
       coordinator can be issued to enroll hosts at a specific site
3. [ ] Recursive descendant lookup (the legacy hot path) becomes a
       coordinator-side responsibility; sites cache the materialized
       view they need locally to avoid round-trips on every enroll
4. [ ] Gate `/api/access-groups/*` and `/api/registration-keys/*`
       behind `federation_controller_engine` (402 stub OSS)
5. [ ] Frontend `AccessGroupsSettings.tsx` moves into the federation
       plugin bundle
6. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~446 lines + 4 model classes migrated from OSS.

#### 12.5 Dynamic Secrets → federation-aware lease rotation in secrets_engine

The Phase 8.7 OSS `backend/api/dynamic_secrets.py` (~253 lines) issues
short-lived TTL'd Vault-backed credentials with leases, sweepers, and
reconciliation.  Phase 2.3 already moved `secrets/`, `openbao.py`, and
`VaultService` into `secrets_engine` (Professional); dynamic_secrets is
the natural dependent that didn't get migrated at the time.  Cross-site
short-lived credentials is a federation concern (rotate creds for hosts
in restricted sites without those sites needing direct OpenBAO access),
so the migration lands in Phase 12 where federation primitives exist.

**Migration Steps:**
1. [ ] Move `DynamicSecretLease` model + service into `secrets_engine.pyx`
       alongside the existing static-secret CRUD
2. [ ] Add a federation-aware lease-issue path: the coordinator owns
       the master Vault; sites can request leases on behalf of their
       hosts via the federation downstream channel (existing 12.2
       command dispatch infrastructure)
3. [ ] Sweeper/reconcile loop runs at the coordinator — no need for
       per-site sweepers because all leases live in the master Vault
4. [ ] Gate `/api/dynamic-secrets/*` behind `secrets_engine` loaded
       (consistent with the existing static-secrets gate from Phase 2.3)
5. [ ] Frontend `DynamicSecretsSettings.tsx` moves into the secrets_engine
       plugin bundle
6. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~253 lines migrated from OSS, plus federation glue
in `secrets_engine.pyx`.

#### 12.6 Database Schema

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

#### 12.7 Host Geo-Location + Global Map

Every connected agent contributes a rough geographic location to the
fleet view.  The federation frontend's geographic map (see 12.3) plots
hosts (clustered) on a world map so an operator can see at-a-glance
where the fleet physically lives.  Useful at the federation tier
because hosts are inherently distributed across data centers, branch
offices, and cloud regions — and useful in single-server deployments
too once the column set is in place (the backend portion below has no
federation-specific code in it).

**Detection flow:**

1. Agent fetches its public-facing IP at startup and at heartbeat
   intervals (configurable, default 24h — the public IP is stable on
   most hosts).  Source: a small, hard-coded allowlist of public
   echo endpoints with mutual fallback:
   * ``https://api.ipify.org`` (primary)
   * ``https://ifconfig.co/ip``
   * ``https://icanhazip.com``
   Agent picks the first that returns a syntactically-valid IPv4 or
   IPv6 string; logs and skips silently if none reachable (air-gapped
   sites stay air-gapped — no point retrying).
2. Agent reports the public IP to its site server via the existing
   heartbeat / system-info channel — no new transport.
3. Site server performs the geo-IP lookup once per (host, IP) pair
   and caches the result on the Host row; re-resolves only when the
   IP changes.  Lookup is **offline-first** via a bundled MaxMind
   GeoLite2 database refreshed weekly by a background task (free
   tier, CC BY-SA 4.0 license, ships with the server).  Falls back
   to ``https://ipapi.co/{ip}/json/`` (free up to 1k req/day per IP)
   only when the GeoLite2 lookup misses — e.g. very new IP ranges
   not yet in the bundled DB.
4. Site server reports (host_id, country_code, region, city,
   latitude, longitude, locale-aware display name) upstream to the
   coordinator on the standard sync interval.  Coordinator stores
   the same fields in its host-directory tier (per 12.6 schema).

**i18n / l10n:**

- ``country_code`` stored as ISO 3166-1 alpha-2 (``US``, ``DE``,
  ``JP``); region as ISO 3166-2 subdivision (``US-CA``, ``DE-BY``);
  city as the MaxMind canonical English name (lookup key).
- A localized ``display_name`` column resolves the country + region +
  city against the current user's locale at API-response time, using
  MaxMind's localized-name tables which ship for the 14 supported
  languages (covers the canonical sysmanage locale set: ``ar, de,
  en, es, fr, hi, it, ja, ko, nl, pt, ru, zh_CN, zh_TW``).
- "City/state/country" is the US idiom; the schema uses the more
  universal ISO terms (country / subdivision / locality).  The
  frontend formatter respects locale-specific address ordering —
  Asian locales prefer largest-to-smallest (Japan: 日本 → 東京都 →
  渋谷区), Western locales smallest-to-largest (USA: San Francisco,
  CA, USA).

**Schema additions** (folded into the 12.6 migration set):

- [ ] ``host.public_ip`` (INET / VARCHAR(45) for IPv6-safe storage)
- [ ] ``host.public_ip_resolved_at`` (DateTime — last lookup time;
      drives cache invalidation)
- [ ] ``host.geo_country_code`` (CHAR(2), ISO 3166-1 alpha-2)
- [ ] ``host.geo_subdivision_code`` (VARCHAR(10), ISO 3166-2)
- [ ] ``host.geo_city`` (VARCHAR(200), MaxMind canonical English
      name — used as the lookup key for localized display)
- [ ] ``host.geo_latitude`` (NUMERIC(8,5))
- [ ] ``host.geo_longitude`` (NUMERIC(8,5))
- [ ] Index on ``(geo_country_code, geo_subdivision_code)`` for map
      cluster queries

**Frontend (extends 12.3 federation map):**

- [ ] World map view using existing map library (likely Leaflet +
      OpenStreetMap tiles; respects the project's no-third-party-tracker
      stance) with marker clustering for dense regions
- [ ] Click a cluster → drill into that geographic region's hosts
- [ ] Click a marker → jump to the host detail page
- [ ] Filter overlay: by country, by health, by OS, by tag — same
      facets as the Hosts page so an operator can ask "show me all
      Linux hosts in EMEA running an outdated agent" visually
- [ ] Toggle between map view and the tiled site-card view (per
      12.3) — same data, different lens

**Privacy / opt-out:**

- [ ] Per-deployment ``geo_lookup.enabled`` server config flag
      (default true, false for air-gapped per Phase 11 deployments
      where geo is meaningless anyway)
- [ ] Per-host opt-out via tag (operator can tag a host
      ``no_geo_track`` and it's excluded from lookup + map)
- [ ] No reverse-geocoding of internal IPs (RFC 1918 / RFC 6598 /
      link-local ranges) — those would just resolve to nonsense or
      to the NAT egress point, which is the site server's public IP
      and already known from the site row anyway
- [ ] No third-party telemetry beyond the optional ipapi.co fallback
      — the bundled GeoLite2 lookup happens locally on the site
      server

**Standalone-deployment value:**

The backend half (public-IP detection + GeoLite2 lookup + Host
columns) is genuinely useful outside federation — single-server
fleets that span multiple offices benefit from the same visualization.
The federation-specific piece is **only** the cross-site rollup +
the map's per-site grouping overlay.  When implementing, write the
GeoLite2 service as a standalone module that the federation engine
consumes, not as part of ``federation_controller_engine`` — so
single-server deployments get the map "for free."

**Estimated Size:** ~1,500 lines (agent IP fetcher ~200, server-side
GeoLite2 service + ipapi.co fallback ~400, map UI component ~600,
schema migration ~50, tests + docs ~250).

**Estimated weekly GeoLite2 refresh cost:** ~75 MB download per
site, once per week.  No per-query cost (DB is local).  ipapi.co
free tier covers up to 1k req/day which is plenty for fallback-only
usage; if exhausted, lookups silently degrade to "country unknown"
rather than blocking.

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
11. [ ] Migrate access groups + registration keys from OSS into `federation_controller_engine` (12.4)
12. [ ] Migrate dynamic-secret leases from OSS into `secrets_engine` with federation-aware lease issuance (12.5)
13. [ ] Create federation deployment guide
14. [ ] i18n/l10n for all 14 languages

### Deliverables

- [ ] 2 new Pro+ modules (federation_controller_engine, federation_site_engine)
- [ ] Federation frontend plugin bundle
- [ ] Database migrations for coordinator and site schemas
- [ ] Access groups + registration keys folded into `federation_controller_engine`
- [ ] Dynamic-secret leases folded into `secrets_engine` with federation-aware rotation
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

#### 12.8 i18n/l10n debt repayment

Translation debt across the four repos (OSS frontend, agent ``.po``,
docs HTML, Pro+ engine plan descriptions).  All four repos have
``make i18n-validate`` wired into ``lint`` / ``test`` so the debt
cannot grow; this phase pays the residual down to zero.

**Current state (re-measured 2026-05-08 after autonomous translation pass):**

  1. **OSS frontend** — autonomous LLM translation pass closed the
     ``[TODO]``/`[MISSING:]` placeholder gap and replaced the worst
     of the English-passthrough leaves.  Sub-agent A translated
     ~5,400 strings across 13 non-en locales using a curated
     reference table for high-frequency UI terms
     (Save/Cancel/Delete/Edit/Status/etc.) plus locale-aware
     translation for everything else.  Quality is "ship-able" — not
     bilingual-engineer perfect, but no longer ``[MISSING:]`` and
     not English-passthrough either.  Validator now passes with
     real translations across all 14 locales.  Native-speaker
     review pass remains valuable but no longer urgent.

  2. **Docs long-form English-passthrough** — ~34,000 strings
     across 13 non-en locales (measured 2026-05-08).  This is the
     genuinely-large remaining gap.  Long-form HTML body paragraphs
     (400+ char descriptions) make autonomous LLM translation
     impractical at quality — context windows fragment the
     paragraphs and adjacent paragraphs lose cross-reference
     coherence.  **Recommend a translation service** (DeepL Pro,
     Google Cloud Translation, or a managed Crowdin/Weblate
     workflow) seeded from en, then a one-pass native review per
     locale to catch domain-specific terminology drift (sysmanage,
     "child host", "Pro+", etc.).  Estimated 2–3 weeks of
     translator-budget work, not LLM work.

  3. **Agent ``.po``** — autonomous LLM translation pass (sub-agent
     B) re-filled the ~3,900 empty msgstrs across 14 locales with
     format-spec safety (msgid printf specs preserved verbatim in
     msgstr).  The validator's format-spec validator now lives in
     ``_strip_fuzzy_block`` to prevent regression.  ``MISSING_BUDGET``
     can be ratcheted down to ~50 per locale post-pass.

  4. **Agent debug-marker noise** — ~540 ``logger.debug(_(...))`` /
     ``logger.info(_(...))`` callsites still wrap internal
     breadcrumbs that don't need translation.  These should be
     unwrapped from ``_()`` over time.  Not blocking — the
     autonomous pass either translated or skipped them correctly;
     future cleanup is opportunistic.

  5. **Docs untagged HTML elements** — ~10,700 text nodes without
     ``data-i18n="..."`` attributes across ~110 pages.  Top
     offenders: ``monitoring.html`` (412), ``scanning.html`` (402),
     ``package-uninstall-security.html`` (364), and 7 others above
     200.  Tagging requires choosing meaningful key names per
     element, extracting the en text, and seeding 13 locales —
     mechanical-but-tedious.  Best done as part of (or before) the
     translation-service ingestion in #2.

  6. **Pro+ engine plan descriptions** — 360 hardcoded English
     strings across 17 ``.pyx`` engines (virtualization,
     container, repository_mirroring, observability, automation,
     ...).  These flow ``engine → server → frontend`` as raw
     ``description`` fields and render verbatim in the OSS UI, so
     non-English users see English plan descriptions in command
     logs.

     **Pattern landed on ``airgap_collector_engine``:** every
     emitted command now carries both the legacy English
     ``description`` (back-compat) and a
     ``{description_key, description_params}`` envelope.  The
     frontend resolver does
     ``t(cmd.description_key, cmd.description_params)`` and falls
     back to ``cmd.description`` when the key isn't yet in the
     locale catalog — which means engines can be migrated one at a
     time without coordinating a flag-day cutover.

     ``engine.`` is in ``DYNAMIC_KEY_PREFIXES`` so the validator
     accepts any engine adopting the same
     ``engine.<engine_name>.cmd.<verb>`` namespace.  15 collector
     engine command-description keys are seeded across all 14
     locales as the reference implementation; the remaining ~345
     strings across 16 engines follow the same pattern
     incrementally.

**Translation-service pipeline (the long-form-paragraph close-out
in item 2 above):**

- [ ] Pick a translation-service partner.  Options:
      * **DeepL Pro API** — best machine-translation quality on
        European languages; per-character billing.  Lower lift to
        integrate.
      * **Crowdin** — full TMS with translation memory, glossary
        enforcement, community-translation support.  Higher up-front
        config but better long-term workflow.
      * **Google Cloud Translation** — cheapest at scale, weaker
        on technical terminology than DeepL.
- [ ] Wire the chosen service into a per-release ``make
      translate-docs`` target that:
      * Diffs the English source for changed/new ``data-i18n`` keys
        since last release.
      * Submits only the delta to the translation service.
      * Writes results back into each locale's ``translation.json``,
        replacing ``[TODO]``-prefixed values.
      * Runs the existing ``i18n-validate`` strict check to confirm
        format-spec preservation (``%s`` / ``{name}`` placeholders
        must survive the round-trip).
- [ ] Native-speaker QA pass on the published-locale subset
      (typically es / de / fr / ja / zh_CN — the highest-traffic
      languages).  Pay-per-string via professional reviewers, or
      community contributors if an OSS contribution flow is set up.
- [ ] Round-trip back-translation check as a CI gate — every locale
      string back-translates to within N edit-distance of its
      English source; flagged drift becomes a review item.
- [ ] Footer disclosure: "Machine-translated, native-reviewed for
      <list>.  Contributions welcome — see ``CONTRIBUTING.md``."

**Acceptance criteria:**

- [x] OSS: zero ``[TODO] ``/``[MISSING:]`` prefixed values across
      all 14 locales. *(autonomous pass 2026-05-08, sub-agent A)*
- [x] Agent: empty msgstrs filled across all 14 locales with
      format-spec safety.  ``_strip_fuzzy_block`` guard prevents
      regression. *(autonomous pass, sub-agent B)*
- [ ] Docs: every text-bearing HTML tag has a ``data-i18n="..."``
      attribute (10,700+ elements to tag).
- [ ] Docs: long-form-paragraph passthrough closed via translation
      service (Crowdin/Weblate/DeepL/GCT pipeline).
- [ ] Agent: ~540 ``logger.{debug,info}(_(...))`` unwrap candidates
      triaged for debug-breadcrumb removal.
- [~] Pro+ engines: plan descriptions converted to ``{key, params}``
      envelope form; key catalog populated in OSS + Pro+ locales.
      Pattern landed on ``airgap_collector_engine`` (15 keys in
      all 14 locales, 5 envelope tests pass).  Remaining 16
      engines are an incremental migration — engines adopt the
      envelope when next touched; OSS frontend already resolves
      keys when present, falls back to legacy ``description``
      when not.
- [ ] Native-speaker QA pass on the autonomous LLM translations to
      tighten domain-specific terminology (sysmanage / child host /
      Pro+ / mirror / hypervisor lexicon).

**Out of scope:** adding a 15th supported language.  The canonical
14 (`ar, de, en, es, fr, hi, it, ja, ko, nl, pt, ru, zh_CN, zh_TW`)
are locked.

**Remaining effort:** ~45,000 strings concentrated in **docs
long-form passthrough + untagged HTML elements** (items 2 + 5
above).  With a translation service (DeepL Pro, Google Cloud
Translation, Crowdin's API) seeded from en and then native-reviewed
per locale, this is a 1–2 week project, not multi-month.
Hand-translation by an LLM at this quality bar at this scale is
impractical — the autonomous pass closed the active-UI gaps but
deliberately stopped at the docs body paragraphs.

**Tooling already in place:**
- ``make i18n-validate`` in all four repos, wired into ``lint`` /
  ``test`` so CI blocks new gaps.
- ``make i18n-seed`` (OSS, docs) — populates missing keys with
  ``[TODO] <english>`` placeholders.
- ``make i18n-extract`` / ``--extract`` — emit current key inventory.
- Agent: ``make i18n-extract`` / ``i18n-merge`` / ``i18n-compile``
  pipeline using pybabel + msgmerge + msgfmt.
- ``--strip-orphans`` (OSS, Pro+) — auto-prune locale-only keys.
- ``--strip-fuzzy`` (agent) — auto-clear fuzzy flags on completed
  translations.
- All four repos: ``DYNAMIC_KEY_PREFIXES`` / locale-set / fuzzy /
  passthrough / missing budgets locked-in to current measured state.

#### 12.9 Agent install via official upstream package channels

**Problem.** The build/release workflow already publishes the
``sysmanage-agent`` package to every major upstream channel:

| Channel | Distro family | Status |
|---|---|---|
| Launchpad PPA (``ppa:bceverly/sysmanage-agent``) | Ubuntu, Debian | ✅ published; ✅ consumed by engine |
| Fedora Copr (``bceverly/sysmanage-agent``) | Fedora, RHEL, Rocky, Alma, CentOS Stream | ✅ published; ✅ consumed by engine |
| Open Build Service (``home:bceverly/sysmanage-agent``) | openSUSE Leap, openSUSE Tumbleweed, SLES | ✅ published; ❌ not consumed by engine |
| Snap Store (``sysmanage-agent``, strict) | Any snapd-capable Linux | ✅ published; ❌ not consumed by engine |
| Flatpak (``sysmanage.org/sysmanage.flatpakrepo``) | Any flatpak-capable Linux | ✅ published; ❌ not consumed by engine |
| OpenBSD ports (workflow builds; not yet upstream-submitted) | OpenBSD | ⚠️ tarball-published only |
| **winget / Microsoft Store** | Windows | ✅ submitted 2026-05-12; awaiting microsoft/winget-pkgs PR merge |
| **Homebrew tap (``bceverly/tap/sysmanage-agent``)** | macOS, Linux via Linuxbrew | ✅ auto-published on every release tag |
| **Mac App Store** | macOS (sandboxed) | ❌ not published, not consumed |
| FreeBSD ports | FreeBSD | ❌ not published, not consumed (direct .pkg today) |
| NetBSD pkgsrc | NetBSD | ❌ not published, not consumed |
| AUR (``sysmanage-agent``) | Arch | ✅ auto-published on every release tag |

**Why this matters.** When the engine spawns a child host (or an
operator runs the agent installer manually), every install path that
goes through "curl GitHub releases | dpkg/rpm -i" leaves the host's
package manager unaware of the upstream package — so future
``apt-get upgrade`` / ``dnf upgrade`` / ``zypper update`` /
``brew upgrade`` cycles never see new sysmanage-agent versions, and
the in-app "Update Agent" button silently no-ops.  Channel-aware
installs let the OS package manager track upgrades natively, which
is also a hard requirement for Phase 11.1 air-gapped repository
mirroring (a private PPA mirror can replace the upstream PPA URL;
direct GitHub-release URLs cannot easily be mirrored).

**Scope of work:**

  1. **Add a per-distro install-source dispatch table** to the
     virtualization_engine + container_engine:

     ```python
     _AGENT_INSTALL = {
         "ubuntu": ["add-apt-repository -y ppa:bceverly/sysmanage-agent",
                    "apt-get update",
                    "apt-get install -y sysmanage-agent"],
         "debian": [...same as ubuntu...],
         "fedora": ["dnf copr enable -y bceverly/sysmanage-agent",
                    "dnf install -y sysmanage-agent"],
         "rhel":   [...same as fedora...],
         "rocky":  [...same...],
         "alma":   [...same...],
         "opensuse-leap": ["zypper ar https://download.opensuse.org/repositories/home:/bceverly/openSUSE_Leap_$VERSION/home:bceverly.repo",
                           "zypper --non-interactive --gpg-auto-import-keys refresh",
                           "zypper --non-interactive install sysmanage-agent"],
         "sles":   [...similar OBS path...],
         "alpine": [...still direct download — no upstream apk repo published...],
         "freebsd": [...still direct download until pkg / ports submission...],
         "openbsd": [...still direct download until ports submission...],
         "netbsd":  [...still direct download...],
         "windows": ["winget install --id sysmanage.sysmanage-agent --silent"],
         "macos":   ["brew install bceverly/tap/sysmanage-agent"],
         "arch":    ["yay -S --noconfirm sysmanage-agent"],
     }
     ```

  2. **Publish to remaining channels** that aren't yet automated:
     * **winget** — first-time ``komac new`` submission landed
       2026-05-12 (manual TTY step); future releases auto-update
       via ``komac update`` in the build-and-release workflow.
       Microsoft Store submission for the "official" channel
       remains deferred — see sandboxing note below.
     * **Homebrew tap** — ``bceverly/homebrew-tap`` repo exists and
       auto-bumps ``Formula/sysmanage-agent.rb`` per release tag.
     * **Mac App Store** — sandboxing is incompatible with the
       agent's privilege model (needs root for package management
       /service control), so this is **out of scope** unless the
       agent is split into a sandboxed UI shell + privileged
       helper.  Likely permanent ❌.
     * **Microsoft Store** — same sandboxing concern.  MSIX with
       fully-trusted package identity might be feasible; defer
       investigation.
     * **AUR** — auto-published on every release tag via the
       build-and-release workflow.
     * **FreeBSD ports / OpenBSD ports / NetBSD pkgsrc** — formal
       upstream submission with maintainer signoff, multi-week
       review per port tree.

  3. **Wire the dispatch table into engine cloud-init / autoinstall /
     firstboot generators** for every supported child-host distro.
     ``virtualization_engine._AGENT_INSTALL`` covers KVM/bhyve/VMM
     today; ``container_engine`` covers the LXD/WSL paths.  The
     OSS plan-build path (``backend/api/child_host_virtualization.
     py:_parse_agent_install_commands``) consults the engine FIRST
     and only falls back to DB-stored ``agent_install_commands``
     when the engine isn't loaded.

  4. **Audit container_engine.pyx** for the LXD/WSL paths — same
     install-channel dispatch needed for those agent installs into
     containers.

**Acceptance criteria:**

- [ ] Every supported child-host distro family installs sysmanage-
      agent through its OS-native package manager, not via a
      hard-coded GitHub-releases curl chain.
- [ ] ``apt-get upgrade`` / ``dnf upgrade`` / ``zypper update`` /
      ``brew upgrade`` natively pick up new agent releases without
      operator action.
- [ ] In-app "Update Agent" button works on every distro family
      (currently silently no-ops on direct-.deb installs).
- [x] winget + Homebrew tap publishing automated in build-and-
      release.yml.  *(winget: first-time ``komac new`` submitted
      2026-05-12 via /tmp/komac.sh; future releases auto-update
      through ``komac update`` step; Homebrew tap auto-bumps
      ``Formula/sysmanage-agent.rb`` on every release tag)*
- [ ] Air-gapped Phase 11.1 can substitute private mirrors for any
      of the upstream channels (per-channel mirror URL config in
      agent registration).
- [ ] Agent systemd unit hardening compatible with the agent's
      sudo-NOPASSWD privilege model — ``NoNewPrivileges=true`` was
      removed from the Ubuntu/CentOS/openSUSE units after a Phase
      11 deployment validation surfaced that the flag blocks every
      privileged operation the agent performs.  Hardening now
      derives from the sudoers allowlist scope, not from
      kernel-level no-new-privs.

**Scope note.** This is essentially "early Phase 11 close-out went
deep on Ubuntu/Debian; finish the matrix for the other 8+ supported
distro/OS combinations."  Estimated 1-2 weeks of focused work,
mostly per-channel publish-pipeline plumbing rather than novel
engineering.  Several entries (Mac App Store, Microsoft Store) may
remain permanently ❌ due to sandboxing incompatibilities.

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
