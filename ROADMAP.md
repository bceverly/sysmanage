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
16. [Phase 2: Foundation Features](#phase-2-foundation-features)
17. [Phase 3: Stabilization](#phase-3-stabilization)
18. [Phase 4: Pro+ Professional Tier](#phase-4-pro-professional-tier)
19. [Phase 5: Stabilization](#phase-5-stabilization)
20. [Phase 6: Stabilization RC1](#phase-6-stabilization-rc1)
21. [Phase 7: Pro+ Enterprise Tier - Part 1](#phase-7-pro-enterprise-tier---part-1)
22. [Phase 8: Pro+ Enterprise Tier - Part 2](#phase-8-pro-enterprise-tier---part-2)
23. [Phase 9: Stabilization RC2](#phase-9-stabilization-rc2)
24. [Phase 10: Pro+ Enterprise Tier - Part 3](#phase-10-pro-enterprise-tier---part-3)
25. [Phase 11: Enterprise GA (v3.0.0.0)](#phase-11-enterprise-ga-v3000)
26. [Release Schedule Summary](#release-schedule-summary)
27. [Module Migration Plan](#module-migration-plan)

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
│  Phase 2: Foundation Features (Open Source)                         v1.3.0.0   │
│     └── Access Groups, Scheduled Updates, Package Compliance, Audit, Broadcast │
│                                                                                 │
│  Phase 3: Stabilization                                             v1.4.0.0   │
│     └── Test coverage push, full i18n audit, performance baseline              │
│                                                                                 │
│  Phase 4: Pro+ Professional Tier                                    v2.0.0.0   │
│     └── reporting, audit, secrets + container_engine (LXD, WSL)                │
│                                                                                 │
│  Phase 5: Stabilization                                             v2.1.0.0   │
│     └── Pro+ integration testing, license gating verification                  │
│                                                                                 │
│  Phase 6: Stabilization                                             v2.2.0.0   │
│     └── Integration testing, load testing, security penetration test           │
│                                                                                 │
│  Phase 7: Pro+ Enterprise Tier - Part 1                             v2.3.0.0   │
│     └── av_management_engine, firewall_orchestration_engine (security first)   │
│                                                                                 │
│  Phase 8: Pro+ Enterprise Tier - Part 2                             v2.4.0.0   │
│     └── automation_engine, fleet_engine                                        │
│                                                                                 │
│  Phase 9: Stabilization                                             v2.5.0.0   │
│     └── Final polish, documentation completion, i18n verification              │
│                                                                                 │
│  Phase 10: Pro+ Enterprise Tier - Part 3                            v2.6.0.0   │
│     └── virtualization_engine, observability_engine, MFA (largest/most complex)│
│                                                                                 │
│  Phase 11: Major Enterprise GA                                      v3.0.0.0   │
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

**Target Release:** v1.4.0.0
**Focus:** Test coverage push, i18n audit, performance baseline

### Goals

1. **Test Coverage Push** (+5% from Phase 1)
   - [ ] Backend coverage: Target 70%
   - [ ] Agent coverage: Target 70%
   - [ ] Pro+ coverage: Target 75%
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

- Backend test coverage: ≥70%
- Agent test coverage: ≥70%
- Pro+ test coverage: ≥75%
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

#### 4.4 container_engine (Professional)

**Source Files:**
- `sysmanage_agent/operations/child_host_lxd.py`
- `sysmanage_agent/operations/child_host_lxd_container_creator.py`
- `sysmanage_agent/operations/child_host_wsl.py`
- `sysmanage_agent/operations/child_host_wsl_setup.py`
- `sysmanage_agent/operations/child_host_wsl_control.py`
- `sysmanage_agent/operations/child_host_listing_wsl.py`

**Features:**
- [ ] LXD container creation and lifecycle (Ubuntu)
- [ ] LXD container networking
- [ ] WSL instance creation and lifecycle (Windows)
- [ ] WSL distribution management
- [ ] Container/instance status monitoring

**Keep in Open Source:**
- Read-only container/instance listing

**Migration Steps:**
1. [ ] Create `module-source/container_engine/` structure
2. [ ] Create `container_engine.pyx` Cython module
3. [ ] Migrate LXD and WSL management code
4. [ ] Create frontend plugin bundle
5. [ ] Update open source to read-only listing
6. [ ] Update documentation
7. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~2,000 lines

### Deliverables

- [ ] 4 new Pro+ modules (reporting, audit, secrets, container)
- [ ] Open source code updated with license checks
- [ ] Documentation for Professional tier features
- [ ] Migration guide for existing users

---

## Phase 5: Stabilization

**Target Release:** v2.1.0.0
**Focus:** Pro+ integration testing and license gating verification

### Goals

1. **Pro+ Module Testing**
   - [ ] Verify all Professional tier modules work correctly
   - [ ] License gating verification for each module
   - [ ] Plugin loading and registration testing
   - [ ] Cross-module integration tests

2. **Container Engine Testing**
   - [ ] LXD container lifecycle testing on Ubuntu
   - [ ] WSL instance lifecycle testing on Windows
   - [ ] Verify read-only mode for unlicensed users

3. **Documentation**
   - [ ] Professional tier feature documentation
   - [ ] Upgrade guide from open source to Professional

### Exit Criteria

- All Professional tier modules functional
- License gating working correctly
- No critical bugs in Pro+ modules

---

## Phase 6: Stabilization RC1

**Target Release:** v2.2.0.0
**Focus:** Integration testing, load testing, security penetration test

### Goals

1. **Test Coverage Push** (+5% from Phase 3)
   - [ ] Backend coverage: Target 75%
   - [ ] Agent coverage: Target 75%
   - [ ] Pro+ coverage: Target 80%

2. **Integration Testing**
   - [ ] End-to-end tests for container_engine (LXD, WSL)
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

## Phase 7: Pro+ Enterprise Tier - Part 1

**Target Release:** v2.3.0.0
**Focus:** Security engines for Enterprise tier (AV and firewall management)

### Modules to Migrate

#### 7.1 av_management_engine (Enterprise)

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

**Migration Steps:**
1. [ ] Create `module-source/av_management_engine/` structure
2. [ ] Create `av_management_engine.pyx` Cython module
3. [ ] Migrate AV management code
4. [ ] Create frontend plugin bundle
5. [ ] Update open source to read-only status
6. [ ] Update documentation
7. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~3,000 lines

#### 7.2 firewall_orchestration_engine (Enterprise)

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

**Migration Steps:**
1. [ ] Create `module-source/firewall_orchestration_engine/` structure
2. [ ] Create `firewall_orchestration_engine.pyx` Cython module
3. [ ] Migrate firewall management code
4. [ ] Create frontend plugin bundle
5. [ ] Update open source to read-only status
6. [ ] Update documentation
7. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~4,000 lines

### Deliverables

- [ ] 2 new Pro+ modules (AV management, firewall orchestration)
- [ ] Open source code updated with stubs/license checks
- [ ] Documentation for Enterprise tier features

---

## Phase 8: Pro+ Enterprise Tier - Part 2

**Target Release:** v2.4.0.0
**Focus:** Automation and fleet management for Enterprise tier

### Modules to Migrate

#### 8.1 automation_engine (Enterprise)

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
- [ ] Multi-shell support (bash, zsh, PowerShell, cmd, ksh)
- [ ] Scheduled script execution
- [ ] Approval workflows for privileged scripts
- [ ] Script parameterization

**Estimated Size:** ~2,000 lines

#### 8.2 fleet_engine (Enterprise)

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

## Phase 9: Stabilization RC2

**Target Release:** v2.5.0.0
**Focus:** Final polish, documentation completion, i18n verification

### Goals

1. **Test Coverage Push** (+5% from Phase 6)
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

## Phase 10: Enterprise Features

**Target Release:** v2.6.0.0
**Focus:** Final Pro+ Enterprise-tier modules (largest/most complex)

### Modules to Migrate

#### 10.1 virtualization_engine (Enterprise)

**Source Files:**
- KVM/QEMU: `sysmanage_agent/operations/child_host_kvm*.py` (8 files, ~4,500 lines)
- bhyve: `sysmanage_agent/operations/child_host_bhyve*.py` (10 files, ~4,600 lines)
- VMM/vmd: `sysmanage_agent/operations/child_host_vmm*.py` (17 files)
- Guest provisioning: `sysmanage_agent/operations/child_host_ubuntu*.py`, `child_host_debian*.py`, `child_host_alpine*.py`
- Backend: `backend/api/child_host_virtualization*.py`, `backend/api/handlers/child_host/*.py`

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

**Keep in Open Source:**
- Read-only VM/container listing and status

**Migration Steps:**
1. [ ] Create `module-source/virtualization_engine/` structure
2. [ ] Create `virtualization_engine.pyx` Cython module
3. [ ] Migrate all hypervisor management code
4. [ ] Create frontend plugin bundle
5. [ ] Update open source to read-only listing
6. [ ] Update documentation
7. [ ] i18n/l10n for all 14 languages

**Estimated Size:** ~13,000 lines

#### 10.2 observability_engine (Enterprise)

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

- [ ] virtualization_engine module
- [ ] observability_engine module
- [ ] MFA implementation
- [ ] Repository mirroring
- [ ] External IdP support

---

## Phase 11: Enterprise GA (v3.0.0.0)

**Target Release:** v3.0.0.0
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
| 0 | v1.1.0.0 | Current | Core platform + virtualization code (moving to Pro+) |
| 1 | v1.2.0.0 | Stabilization | Test coverage, SonarQube cleanup |
| 2 | v1.3.0.0 | Foundation | Access groups, update profiles, compliance |
| 3 | v1.4.0.0 | Stabilization | Performance baseline, i18n audit |
| 4 | **v2.0.0.0** | Pro+ Professional | reporting, audit, secrets, container (LXD/WSL) |
| 5 | v2.1.0.0 | Stabilization | Pro+ integration testing, license verification |
| 6 | v2.2.0.0 | Stabilization | Integration tests, load tests, security |
| 7 | v2.3.0.0 | Pro+ Enterprise 1 | AV management, firewall orchestration (security) |
| 8 | v2.4.0.0 | Pro+ Enterprise 2 | automation, fleet engines |
| 9 | v2.5.0.0 | Stabilization | Final polish, docs complete |
| 10 | v2.6.0.0 | Pro+ Enterprise 3 | virtualization, observability, MFA (largest) |
| 11 | **v3.0.0.0** | Enterprise GA | Multi-tenancy, API complete, full feature set |

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
| container_engine (LXD, WSL) | Professional | 4 | ~2,000 | High |
| av_management_engine | Enterprise | 7 | ~3,000 | High |
| firewall_orchestration_engine | Enterprise | 7 | ~4,000 | High |
| automation_engine | Enterprise | 8 | ~2,000 | Medium |
| fleet_engine | Enterprise | 8 | ~1,500 | Medium |
| virtualization_engine (KVM, bhyve, VMM) | Enterprise | 10 | ~13,000 | Medium |
| observability_engine | Enterprise | 10 | ~4,000 | Medium |

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

- **Professional Tier:** ~8,000 lines (Phase 4: reporting + audit + secrets + container)
- **Enterprise Tier - Part 1:** ~7,000 lines (Phase 7: AV + firewall)
- **Enterprise Tier - Part 2:** ~3,500 lines (Phase 8: automation + fleet)
- **Enterprise Tier - Part 3:** ~17,000 lines (Phase 10: virtualization + observability)

**Grand Total:** ~35,500 lines to migrate for Pro+

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
