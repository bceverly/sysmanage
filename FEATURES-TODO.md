================================================================================
SYSMANAGE FEATURE ROADMAP
================================================================================

IMPLEMENTATION PHASES
================================================================================

Phase 1 - Licensing (IMPLEMENT FIRST):
  #1  Commercial Licensing System

Phase 2 - Foundation:
  #2  Access Groups and Registration Keys
  #3  Scheduled Update Profiles
  #4  Package Compliance Profiles
  #5  Activity Audit Log
  #6  Broadcast Messaging

Phase 3 - Security (Professional+):
  #7  CVE/USN Vulnerability Tracking
  #8  Security Compliance Reporting
  #9  Alerting System
  #10 Multi-Factor Authentication

Phase 4 - Enterprise (Professional+):
  #11 Repository Mirroring
  #12 External Identity Providers
  #13 Reboot Scheduling
  #14 Script Library
  #15 Host Lifecycle Management

Phase 5 - Monitoring (Professional+):
  #16 Custom Metrics and Graphs
  #17 Process Management
  #18 Livepatch Integration
  #19 AI Health Analysis

Phase 6 - Platform:
  #20 Additional Hypervisors
  #21 Infrastructure Deployment
  #22 Firewall Recommendations
  #23 Child Host Profiles
  #24 Enhanced Snap Management

Phase 7 - Polish:
  #25 API Completeness
  #26 Multi-Tenancy (Enterprise)
  #27 GPG Key Management
  #28 Administrator Invitations
  #29 Platform-Native Logging

================================================================================
PHASE 1 - LICENSING (IMPLEMENT FIRST)
================================================================================

1.  Commercial Licensing System
    Implement license key generation, validation, and feature gating to
    separate Community Edition (free) from Professional/Enterprise (paid).

    SEE: LICENSING-ARCHITECTURE.md for complete implementation details.

    Summary:
    - License keys are cryptographically signed JWT-like tokens (ECDSA P-521)
    - Contains: tier, parent host limit, child host limit, enabled features, expiry
    - Cannot be forged without our private signing key
    - Public key embedded in sysmanage server validates signatures
    - Optional phone-home validation for enterprise features

    Tiers:
    - Community: Free, unlimited hosts, Phase 2 features only
    - Professional: Paid per-host, Phases 3-6 features
    - Enterprise: Custom pricing, all features + multi-tenancy

    Features to Implement:
    - License key validation (signature verification, expiry check)
    - License storage in database
    - License management UI in Settings
    - Feature gating decorators for API endpoints
    - Frontend feature checks (hide/show UI elements)
    - Host count enforcement (parent vs child limits)
    - Grace period handling for expired licenses
    - License info API endpoint

    Implementation Hints:
    - Create License model in backend/persistence/models/
    - Create backend/licensing/ module with validator.py, feature_gate.py
    - Embed public key in backend/licensing/public_key.py
    - Add @requires_feature("feature_code") decorator for paid endpoints
    - Add /api/license endpoint returning license info for frontend
    - Frontend: Create LicenseContext, useFeature() hook
    - Frontend: Add License page in Settings.tsx
    - Modify agent registration to enforce host limits
    - Add SecurityRoles: MANAGE_LICENSE

    Code Separation Strategy (Recommended):
    - Single repository with feature flags (simplest)
    - All code in open source repo, but paid features require valid license
    - License signature verification is the protection mechanism
    - Consider Cython compilation for high-value algorithms later

    License Generation (Separate Infrastructure):
    - Private license server at license.sysmanage.io (not in this repo)
    - Customer portal for purchase and license management
    - Phone-home validation endpoint
    - Private signing key in HSM

================================================================================
PHASE 2 - FOUNDATION (Community Edition)
================================================================================

2.  Access Groups and Registration Keys
    Add hierarchical access groups for RBAC scoping and registration keys for
    auto-approval. (Host tagging is already fully implemented.)

    Features to Add:
    - Hierarchical access groups with parent/child relationships
    - Registration keys for auto-approval tied to access groups
    - RBAC permissions scoped by access group
    - Key expiration and usage limits

    Implementation Hints:
    - Tag system complete: backend/persistence/models/operations.py (Tag, HostTag)
    - Tag API complete: backend/api/tag.py with full CRUD and host association
    - Add AccessGroup model with parent_id self-reference for hierarchy
    - Add RegistrationKey model with access_group_id FK, expiration, usage_count
    - Modify host approval in backend/api/host_approval.py to check registration keys
    - Extend SecurityRole checking in backend/security/roles.py to scope by access group
    - Frontend: Add access group management to Settings.tsx
    - Add SecurityRoles: MANAGE_ACCESS_GROUPS, CREATE_REGISTRATION_KEYS

--------------------------------------------------------------------------------

3.  Scheduled Update Profiles
    Define when and how updates are applied to groups of hosts.

    Features:
    - Upgrade profiles with scheduling (hourly, daily, weekly, specific times)
    - Security-only update option
    - Associate profiles with tags
    - Staggered rollout windows
    - Automation tab in UI showing host auto-update status
    - Inline editing of auto-update settings

    Implementation Hints:
    - Create UpgradeProfile model: name, schedule_cron, security_only, access_group_id
    - Create UpgradeProfileTag junction table
    - Add scheduled task using APScheduler (already used for other scheduled tasks)
    - Server sends UPDATE_REQUEST to agents matching profile tags at scheduled time
    - Agent handler exists: check update_operations.py, update_manager.py
    - Frontend: Add Automation tab between Updates and Scripts in Navbar.tsx
    - Create AutomationPage.tsx with DataGrid showing hosts + auto-update status pills
    - Use inline editing pattern from other grids (pencil icon → checkboxes → save)
    - Add SecurityRoles: MANAGE_UPGRADE_PROFILES, APPLY_UPGRADE_PROFILE

--------------------------------------------------------------------------------

4.  Package Compliance Profiles
    Ensure specific packages are always/never installed on tagged hosts.

    Features:
    - Define required packages ("always install")
    - Define blocked packages ("never install")
    - Version constraints (>=, <=, ==)
    - Associate with host tags
    - Periodic compliance checks with drift detection

    Implementation Hints:
    - Create PackageProfile model: name, access_group_id
    - Create PackageProfileConstraint: profile_id, package_name, constraint_type
      (REQUIRED/BLOCKED), version_constraint
    - Create PackageProfileTag junction table
    - Agent-side: Add compliance check in data_collector.py periodic loop
    - Compare installed packages against profile constraints
    - Send compliance_status message type with violations list
    - Server: Store compliance state in new HostComplianceStatus table
    - Frontend: Add Compliance tab to HostDetail.tsx showing violations
    - Add SecurityRoles: MANAGE_PACKAGE_PROFILES, VIEW_COMPLIANCE

--------------------------------------------------------------------------------

5.  Activity Audit Log
    Comprehensive logging of all administrative actions.

    Features:
    - Log who did what, when, to which hosts
    - Track success/failure with details
    - Script output and exit codes
    - Filterable activity history page
    - Export to CSV/PDF

    Implementation Hints:
    - AuditLog model already exists: backend/persistence/models/core.py
    - AuditService exists: backend/services/audit_service.py
    - Currently logs CREATE/UPDATE/DELETE actions
    - Add EXECUTE action type for script executions, reboots, etc.
    - Store script output in details JSON field (truncate if > 64KB)
    - Frontend: AuditLogViewer.tsx exists - enhance with better filtering
    - Add date range picker, entity type filter, user filter, result filter
    - Add export buttons using existing PDF report infrastructure
    - Ensure all API endpoints call AuditService (audit existing endpoints)

--------------------------------------------------------------------------------

6.  Broadcast Messaging
    Send commands to all agents simultaneously without linear scaling.

    Features:
    - Broadcast channel for mass operations
    - Efficient ping/refresh all hosts
    - Broadcast software inventory requests
    - Subscribe/unsubscribe pattern

    Implementation Hints:
    - Current queue system: backend/websocket/queue_operations.py
    - enqueue_message() already supports host_id=None for broadcast
    - Modify outbound_processor.py to handle broadcast differently
    - Option 1: WebSocket pub/sub - agents subscribe to broadcast topic
    - Option 2: Database flag - agents poll for broadcast messages
    - Agent: Add broadcast message handler in message_handler.py
    - Check for broadcast messages in message_receiver() loop
    - Add BROADCAST message type to backend/websocket/messages.py
    - Frontend: Add "Broadcast Refresh" button to Hosts.tsx toolbar
    - Add SecurityRoles: SEND_BROADCAST

================================================================================
PHASE 3 - SECURITY (Professional+)
================================================================================

7.  CVE/USN Vulnerability Tracking
    Track security vulnerabilities affecting managed hosts enterprise-wide.

    Features:
    - Enterprise-wide vulnerability dashboard showing all CVEs across all hosts
    - Per-host vulnerability view in host details page
    - Map CVEs to USNs (Ubuntu Security Notices) and other advisories
    - Link packages to vulnerabilities across all supported package managers
    - CVSS score-based prioritization
    - Regular ingestion of CVE databases with package version mappings
    - Security compliance reports

    Implementation Hints:
    - Create Vulnerability model: cve_id, description, cvss_score, published_date,
      severity, affected_systems (JSON for OS/distro specifics)
    - Create PackageVulnerability: package_name, package_manager (apt/dnf/brew/etc),
      vulnerable_versions, fixed_version, vulnerability_id
    - Store in database, match against host software inventory by package manager
    - Create HostVulnerability view joining hosts → packages → vulnerabilities
    - Agent: No changes needed - uses existing software inventory
    - Server: Add vulnerability matching in software_package_handlers.py
    - Frontend: Add Vulnerabilities page showing enterprise-wide CVE list
    - Frontend: Add Security tab to HostDetail.tsx with per-host CVE list
    - Add vulnerability count badge to host list
    - Add SecurityRoles: VIEW_VULNERABILITIES, EXPORT_VULNERABILITY_REPORT

    Vulnerability Data Sources:

    GENERAL (All Platforms):
    - NVD (NIST National Vulnerability Database) API 2.0
      URL: https://services.nvd.nist.gov/rest/json/cves/2.0
      Docs: https://nvd.nist.gov/developers/vulnerabilities
      Notes: Primary CVE source, includes CVSS scores. Rate limited, request API key.

    LINUX - Ubuntu/Debian (apt):
    - Ubuntu Security API (CVEs and USNs)
      CVEs: https://ubuntu.com/security/cves.json
      USNs: https://ubuntu.com/security/notices.json
      Docs: https://github.com/canonical/ubuntu-com-security-api
      Notes: Maps CVEs to Ubuntu packages and versions, includes fix status.
    - Debian Security Tracker
      URL: https://security-tracker.debian.org/tracker/data/json
      Notes: JSON export of all Debian CVEs with package mappings.

    LINUX - RHEL/Fedora/CentOS (dnf/yum):
    - Red Hat Security Data API
      Base: https://access.redhat.com/hydra/rest/securitydata
      CVEs: https://access.redhat.com/hydra/rest/securitydata/cve.json
      OVAL: https://access.redhat.com/hydra/rest/securitydata/oval.json
      Docs: https://docs.redhat.com/en/documentation/red_hat_security_data_api/1.0
      Notes: No API key required. Filter by severity, date, package.
    - Fedora Bodhi Updates API
      URL: https://bodhi.fedoraproject.org/updates/?type=security
      Notes: REST API for Fedora security updates with CVE references.

    LINUX - SUSE/openSUSE (zypper):
    - SUSE OVAL Data
      URL: https://www.suse.com/support/security/oval/
      CVE DB: https://www.suse.com/security/cve/index.html
      Notes: OVAL XML files for CVE-to-RPM mapping. Also provides CSAF data.

    WINDOWS (chocolatey/winget):
    - Microsoft Security Response Center (MSRC) API
      URL: https://api.msrc.microsoft.com/sug/v2.0/en-us/vulnerability
      Docs: https://github.com/microsoft/MSRC-Microsoft-Security-Updates-API
      Notes: No API key required. PowerShell module: MsrcSecurityUpdates.
      Filter by CVE, product, date. Returns KB articles and affected versions.
    - Chocolatey has no dedicated CVE API; use NVD filtered by product name.

    macOS (brew):
    - Apple Security Updates (no official API)
      URL: https://support.apple.com/en-us/HT201222 (HTML scraping required)
      Notes: No machine-readable API. Consider using NVD filtered for Apple.
    - Homebrew has no CVE database; formulae don't track CVEs directly.
      Use NVD filtered by package names from brew list output.

    BSD - FreeBSD (pkg):
    - FreeBSD VuXML
      URL: https://vuxml.freebsd.org/freebsd/
      Raw XML: https://cgit.freebsd.org/ports/plain/security/vuxml/vuln.xml
      CVE Index: https://www.vuxml.org/freebsd/index-cve.html
      Notes: XML format mapping CVEs to pkg package names and versions.
      Agent can run: pkg audit -F (fetches vuln.xml and audits installed pkgs)

    BSD - OpenBSD:
    - OpenBSD Errata
      URL: https://www.openbsd.org/errata.html
      Notes: HTML format, per-version errata pages. No API.
      Patches signed with signify(1). Use syspatch(8) for binary updates.
      Consider scraping errata pages or using CVEDetails for OpenBSD CVEs.

    BSD - NetBSD (pkgsrc):
    - NetBSD pkg-vulnerabilities
      URL: https://cdn.netbsd.org/pub/pkgsrc/distfiles/vulnerabilities
      Alt: https://ftp.netbsd.org/pub/pkgsrc/distfiles/vulnerabilities
      Notes: Plain text format mapping CVEs to pkgsrc package versions.
      Agent can run: pkg_admin fetch-pkg-vulnerabilities && pkg_admin audit

    Ingestion Strategy:
    - Run scheduled tasks daily (or more frequently for critical sources)
    - NVD: Fetch incrementally using lastModStartDate/lastModEndDate params
    - Ubuntu/Red Hat: Full refresh weekly, delta checks daily
    - BSD VuXML/pkg-vulnerabilities: Fetch and parse XML/text files
    - Store normalized data in PackageVulnerability table
    - Match against host software inventory on each host data refresh

--------------------------------------------------------------------------------

8.  Security Compliance Reporting
    Audit hosts against security benchmarks.

    Features:
    - CIS benchmark auditing
    - DISA STIG compliance
    - Custom compliance rules
    - Exportable compliance reports
    - Security posture dashboard

    Implementation Hints:
    - Create ComplianceProfile model: name, benchmark_type (CIS/STIG/CUSTOM)
    - Create ComplianceRule: profile_id, rule_id, description, check_script
    - Create HostComplianceResult: host_id, rule_id, status, last_checked
    - Agent: Add compliance_check operation that runs USG or custom scripts
    - Parse USG output (Ubuntu Security Guide) for CIS/STIG
    - Send compliance_result message with rule-by-rule status
    - Frontend: Add Compliance page showing hosts × rules matrix
    - Use existing PDF report infrastructure for exports
    - Add SecurityRoles: MANAGE_COMPLIANCE_PROFILES, RUN_COMPLIANCE_SCAN

--------------------------------------------------------------------------------

9.  Alerting System
    Configurable alerts with multiple notification channels.

    Features:
    - Alert rules (security updates available, reboot required, disk low)
    - Custom alert conditions
    - Email notifications
    - Webhook notifications (Slack, Teams, generic)
    - Alert history and acknowledgment

    Implementation Hints:
    - Create AlertRule model: name, condition_type, condition_params (JSON),
      severity, enabled, notification_channels (JSON)
    - Create Alert model: rule_id, host_id, triggered_at, acknowledged_at, message
    - Create NotificationChannel model: type (email/webhook/slack), config (JSON)
    - Background task evaluates rules against host data periodically
    - Use existing email infrastructure or add with smtplib/sendgrid
    - Webhook: Simple POST request with alert payload
    - Frontend: Add Alerts page showing active alerts with ack button
    - Add Alert settings in Settings.tsx for rule configuration
    - Add SecurityRoles: MANAGE_ALERT_RULES, ACKNOWLEDGE_ALERTS

--------------------------------------------------------------------------------

10. Multi-Factor Authentication
    Add TOTP and email-based second factor authentication.

    Features:
    - TOTP authenticator app support
    - Email code verification fallback
    - Backup codes
    - Per-user MFA enforcement
    - Admin can require MFA for all users

    Implementation Hints:
    - Add to User model: mfa_enabled, mfa_secret (encrypted), mfa_backup_codes
    - Use pyotp library for TOTP generation/verification
    - Modify backend/api/auth.py login flow:
      1. Verify password → return mfa_required: true if enabled
      2. Second request with TOTP code → issue JWT
    - Add MFA setup endpoint: generate secret, return QR code URL
    - Email fallback: generate 6-digit code, store with expiry, send via email
    - Frontend: Add MFA setup in Profile.tsx with QR code display
    - Modify Login.tsx to handle two-step flow
    - Add SecurityRoles: REQUIRE_MFA_FOR_ALL (admin setting)

================================================================================
PHASE 4 - ENTERPRISE (Professional+)
================================================================================

11. Repository Mirroring
    Mirror package repositories for bandwidth savings and air-gapped deployments.

    Features:
    - Mirror APT, DNF repositories locally
    - Tiered mirrors for multi-region deployments
    - Repository snapshots for consistent updates
    - Custom repository creation
    - Air-gapped deployment support

    Implementation Hints:
    - Create RepositoryMirror model: name, upstream_url, local_path, sync_schedule
    - Create MirrorSyncLog: mirror_id, started_at, completed_at, status, bytes_synced
    - Use apt-mirror or debmirror for APT repos (shell out)
    - Use reposync for DNF repos
    - Run as separate service or scheduled task on designated host
    - Agent: Add repository source configuration to point to local mirror
    - Modify linux_repository_operations.py to support mirror URLs
    - Frontend: Add Repository Mirrors page in Settings
    - Add SecurityRoles: MANAGE_REPOSITORY_MIRRORS

--------------------------------------------------------------------------------

12. External Identity Providers
    Integrate with LDAP, Active Directory, and OIDC providers.

    Features:
    - LDAP/Active Directory authentication
    - OIDC provider support (Okta, Azure AD, Keycloak)
    - Map external groups to sysmanage roles
    - Optional local account fallback

    Implementation Hints:
    - Create IdentityProvider model: name, type (LDAP/OIDC), config (JSON), enabled
    - Create ExternalGroupMapping: provider_id, external_group, security_role_group_id
    - Use python-ldap for LDAP/AD integration
    - Use authlib for OIDC integration
    - Modify backend/api/auth.py to check external providers first
    - On successful external auth, create/update local User record
    - Apply role mappings based on external group membership
    - Frontend: Add Identity Providers section in Settings.tsx
    - Add SecurityRoles: MANAGE_IDENTITY_PROVIDERS

--------------------------------------------------------------------------------

13. Reboot Scheduling
    Schedule and coordinate host reboots.

    Features:
    - Track pending reboot status with reasons
    - Schedule reboots via profiles
    - Maintenance windows
    - Coordinate reboots across clusters (avoid simultaneous)

    Implementation Hints:
    - Host model already has: reboot_required, reboot_required_reason
    - Create RebootProfile: name, schedule_cron, maintenance_window_start/end
    - Create RebootProfileTag junction table
    - Create ScheduledReboot: host_id, profile_id, scheduled_time, status
    - Server: Background task checks schedules, sends REBOOT command
    - Add stagger logic: if multiple hosts in same profile, spread over window
    - Agent: system_control.py already has reboot functionality
    - Frontend: Add Reboot Scheduling section to Automation tab
    - Show pending reboots with reasons in Hosts.tsx status column
    - Add SecurityRoles: MANAGE_REBOOT_PROFILES, SCHEDULE_REBOOT

--------------------------------------------------------------------------------

14. Script Library
    Save and manage reusable scripts.

    Features:
    - Script library with titles and descriptions
    - Script versioning
    - Script attachments (config files, etc.)
    - Associate scripts with access groups
    - Script templates with variables

    Implementation Hints:
    - SavedScript model exists: backend/persistence/models/operations.py
    - Already has: name, description, script_content, interpreter, created_by
    - Add: version, access_group_id, is_template, variables (JSON)
    - Create ScriptAttachment model: script_id, filename, content (BLOB), size
    - Limit attachments: 5 files, 1MB total per script
    - Add version history: ScriptVersion with script_id, version, content, created_at
    - Frontend: Scripts.tsx exists - enhance with version history, attachments
    - Add template variable substitution ({{hostname}}, {{date}}, etc.)
    - Add SecurityRoles: MANAGE_SCRIPT_LIBRARY (already have ADD_SCRIPT, etc.)

--------------------------------------------------------------------------------

15. Host Lifecycle Management
    Automatically manage stale hosts and license seats.

    Features:
    - Removal profiles (auto-remove after X days inactive)
    - License seat tracking
    - Host archival vs. deletion
    - License usage alerts

    Implementation Hints:
    - Create RemovalProfile: name, days_inactive, action (ARCHIVE/DELETE), enabled
    - Create RemovalProfileAccessGroup junction table
    - Add to Host model: archived_at, archive_reason
    - Create License model: total_seats, used_seats (computed), alert_threshold
    - Background task: Check hosts against removal profiles daily
    - If last_access > days_inactive, archive or delete based on profile
    - Archived hosts excluded from license count but data preserved
    - Frontend: Add Host Lifecycle section in Settings.tsx
    - Show license usage meter in dashboard
    - Add SecurityRoles: MANAGE_REMOVAL_PROFILES, MANAGE_LICENSES

================================================================================
PHASE 5 - MONITORING (Professional+)
================================================================================

16. Custom Metrics and Graphs
    Collect custom metrics and display time-series graphs.

    Features:
    - Define custom metric scripts (output numeric value)
    - Scheduled metric collection (every 5 minutes)
    - Time-series storage
    - Dashboard graphs
    - Sensor data (temperature, fan speed)

    Implementation Hints:
    - Create CustomMetric model: name, script, interval_seconds, unit, host_tags
    - Create MetricDataPoint: metric_id, host_id, timestamp, value
    - Use TimescaleDB extension or simple time-bucketed table
    - Agent: Add custom_metric_collector.py in collection/
    - Run configured scripts, parse numeric output, send metric_data message
    - Add sensor collection using lm-sensors (Linux), powermetrics (macOS)
    - Server: Store data points, implement retention policy (30 days default)
    - Frontend: Add Metrics page with line charts (use recharts or chart.js)
    - Add metric widgets to dashboard
    - Add SecurityRoles: MANAGE_CUSTOM_METRICS, VIEW_METRICS

--------------------------------------------------------------------------------

17. Process Management
    Monitor and manage running processes on hosts.

    Features:
    - View running processes with resource usage
    - Kill processes remotely
    - Process alerts (high CPU, memory)
    - Process history

    Implementation Hints:
    - Create ProcessSnapshot model: host_id, collected_at, processes (JSON)
    - Agent: Add process_collector.py using psutil.process_iter()
    - Collect: pid, name, username, cpu_percent, memory_percent, cmdline
    - Send process_snapshot message periodically (configurable interval)
    - Add kill_process operation using psutil or os.kill()
    - Server: Store latest snapshot per host, optionally keep history
    - Frontend: Add Processes tab to HostDetail.tsx with DataGrid
    - Add Kill button with confirmation dialog
    - Add SecurityRoles: VIEW_PROCESSES, KILL_PROCESS

--------------------------------------------------------------------------------

18. Livepatch Integration
    Track Ubuntu Livepatch status for kernel patching without reboot.

    Features:
    - Track Livepatch status per Ubuntu host
    - View applied live patches
    - Livepatch enablement from UI

    Implementation Hints:
    - Add to Host model: livepatch_enabled, livepatch_status, livepatch_last_check
    - Agent: Add livepatch_collector.py for Ubuntu hosts only
    - Run: canonical-livepatch status --format json
    - Parse running kernel, patch level, last check time
    - Send livepatch_status message type
    - Add livepatch enable/disable operations using canonical-livepatch
    - Server: Store status, add to host response
    - Frontend: Add Livepatch section to HostDetail.tsx (Ubuntu hosts only)
    - Show patch status, enable/disable toggle
    - Add SecurityRoles: MANAGE_LIVEPATCH

--------------------------------------------------------------------------------

19. AI Health Analysis
    Use AI to analyze diagnostics and recommend improvements.

    Features:
    - Analyze diagnostic reports with AI
    - Best practices recommendations
    - Auto-fix capability for common issues
    - Natural language health summaries

    Implementation Hints:
    - DiagnosticReport model exists: backend/persistence/models/operations.py
    - Diagnostic collection exists in agent
    - Add AI analysis endpoint: POST /api/hosts/{id}/analyze-health
    - Send diagnostic data to AI service (OpenAI API or local LLM)
    - Prompt: "Analyze this system diagnostic and provide recommendations..."
    - Store analysis in DiagnosticReport.ai_analysis field
    - Create HealthRecommendation model: host_id, category, recommendation, fixable
    - For fixable issues, generate fix command and offer "Apply Fix" button
    - Frontend: Add AI Analysis section to Diagnostics tab in HostDetail.tsx
    - Add SecurityRoles: RUN_AI_ANALYSIS, APPLY_AI_FIX

================================================================================
PHASE 6 - PLATFORM
================================================================================

20. Additional Hypervisors
    Support more virtualization platforms for child host management.

    Features:
    - KVM/QEMU on Linux
    - bhyve on FreeBSD
    - VirtualBox (cross-platform)
    - Automatic VM registration as managed hosts

    Implementation Hints:
    - Child host framework exists: backend/persistence/models/child_host.py
    - Agent operations exist: child_host_wsl.py, child_host_lxd.py, child_host_vmm.py
    - Create child_host_kvm.py using virsh/libvirt commands
    - Create child_host_bhyve.py using bhyve/bhyvectl commands
    - Create child_host_vbox.py using VBoxManage commands
    - Follow existing pattern: list, create, start, stop, delete operations
    - Add virtualization type detection in virtualization_collector.py
    - Server: ChildHostDistribution model already supports different child_types
    - Add distributions for each hypervisor in Settings
    - Frontend: HostDetail.tsx child hosts tab already handles multiple types
    - Add SecurityRoles per hypervisor if needed

--------------------------------------------------------------------------------

21. Infrastructure Deployment
    Deploy common infrastructure servers to managed hosts.

    Features:
    - Graylog server deployment
    - Grafana server deployment
    - Database server deployment (PostgreSQL, MySQL)
    - Deployment templates

    Implementation Hints:
    - Create DeploymentTemplate model: name, type, script_content, variables
    - Create Deployment model: template_id, host_id, status, deployed_at, config
    - Pre-create templates for common deployments
    - Graylog: Docker compose or package install script
    - Grafana: Docker compose or package install script
    - Databases: Package install + initial config script
    - Use existing script execution infrastructure
    - Agent: No changes needed - uses existing execute_script operation
    - Frontend: Add Deployments page with template selector
    - Show deployment status and logs
    - Add SecurityRoles: MANAGE_DEPLOYMENT_TEMPLATES, DEPLOY_INFRASTRUCTURE

--------------------------------------------------------------------------------

22. Firewall Recommendations
    Recommend firewall rules based on detected server roles.

    Features:
    - Detect server roles (web, database, mail, etc.)
    - Generate appropriate firewall rules
    - Preview and apply recommendations
    - Role-based rule templates

    Implementation Hints:
    - HostRole model exists: backend/persistence/models/host_role.py
    - Role detection exists in agent: role_detection.py
    - Create FirewallRuleTemplate model: role, port, protocol, description
    - Pre-populate templates: web (80,443), ssh (22), postgres (5432), etc.
    - Create endpoint: GET /api/hosts/{id}/firewall-recommendations
    - Match detected roles to templates, return recommended rules
    - Apply uses existing firewall operations in agent
    - Frontend: Add Firewall Recommendations section to HostDetail.tsx
    - Show recommended rules with "Apply" button
    - Add SecurityRoles: VIEW_FIREWALL_RECOMMENDATIONS, APPLY_FIREWALL_RULES

--------------------------------------------------------------------------------

23. Child Host Profiles
    Standardize child host deployments with profiles.

    Features:
    - Define default distributions per virtualization type
    - Standard configurations (CPU, memory, disk)
    - Post-install scripts
    - Profile assignment to parent hosts

    Implementation Hints:
    - Create ChildHostProfile model: name, child_type, distribution_id,
      cpu_cores, memory_mb, disk_gb, post_install_script
    - Create ChildHostProfileTag junction for profile assignment
    - Modify child host creation to use profile defaults
    - Agent: Pass profile config in create_child_host command
    - Run post_install_script after VM creation via SSH or guest agent
    - Frontend: Add Child Host Profiles section in Settings.tsx
    - Modify create child host dialog to show profile selector
    - Add SecurityRoles: MANAGE_CHILD_HOST_PROFILES

--------------------------------------------------------------------------------

24. Enhanced Snap Management
    Full snap package management capabilities.

    Features:
    - Install/remove snaps from UI
    - Update snaps
    - Pause/resume snap auto-updates
    - View snap details (version, channel, confinement)

    Implementation Hints:
    - Snap collection exists in agent: software_inventory_linux.py
    - Add snap-specific operations to package_operations.py
    - Commands: snap install/remove/refresh/hold/unhold
    - Add snap_operation message type
    - Server: Add snap endpoints to software package API
    - Store snap-specific fields: channel, confinement, revision
    - Frontend: Enhance Software tab in HostDetail.tsx
    - Add Snaps sub-tab with snap-specific actions
    - Add SecurityRoles: MANAGE_SNAPS

================================================================================
PHASE 7 - POLISH
================================================================================

25. API Completeness
    Comprehensive REST API covering all features with documentation.

    Features:
    - API endpoints for all features
    - OpenAPI/Swagger documentation
    - API versioning
    - Rate limiting
    - API keys for automation

    Implementation Hints:
    - FastAPI already generates OpenAPI docs at /docs
    - Audit all features for missing API endpoints
    - Add API versioning: /api/v1/, /api/v2/
    - Create ApiKey model: user_id, key_hash, name, permissions, expires_at
    - Add rate limiting middleware using slowapi or similar
    - Document all endpoints with proper descriptions and examples
    - Frontend: Add API Keys section in user Profile.tsx
    - Add SecurityRoles: MANAGE_API_KEYS

--------------------------------------------------------------------------------

26. Multi-Tenancy (Enterprise)
    Support multiple isolated accounts/organizations.

    Features:
    - Separate accounts for different organizations
    - Account switching for administrators
    - Complete data isolation between accounts
    - Per-account settings and limits

    Implementation Hints:
    - Create Account model: name, settings (JSON), created_at
    - Add account_id FK to: Host, User, all profile tables, etc.
    - Modify all queries to filter by current account
    - Create AccountUser junction for users with access to multiple accounts
    - Add account context to JWT claims
    - Middleware: Extract account from JWT, add to request state
    - Frontend: Add account switcher to Navbar if user has multiple accounts
    - Add Account Management page for super-admins
    - Add SecurityRoles: MANAGE_ACCOUNTS, SWITCH_ACCOUNTS

--------------------------------------------------------------------------------

27. GPG Key Management
    Manage GPG keys for package signing verification.

    Features:
    - Store GPG keys centrally
    - Distribute keys to hosts
    - Key rotation support
    - Verify package signatures

    Implementation Hints:
    - Create GpgKey model: name, key_id, public_key, fingerprint, expires_at
    - Create HostGpgKey junction for key deployment tracking
    - Agent: Add gpg_key operations to import keys
    - Use gpg --import for Linux, similar for other platforms
    - Verify packages: dpkg-sig --verify, rpm -K
    - Frontend: Add GPG Keys section in Settings.tsx
    - Show key list with deploy button per host
    - Add SecurityRoles: MANAGE_GPG_KEYS, DEPLOY_GPG_KEY

--------------------------------------------------------------------------------

28. Administrator Invitations
    Invite new administrators with pre-configured roles.

    Features:
    - Generate invitation links
    - Pre-configure roles for invitees
    - Track pending invitations
    - Expiring invitations

    Implementation Hints:
    - Create Invitation model: email, token, roles (JSON), created_by,
      expires_at, accepted_at
    - Generate secure random token for invitation link
    - Send email with invitation link (use existing email infrastructure)
    - Invitation acceptance endpoint creates user with pre-assigned roles
    - Frontend: Add Invitations section in Settings.tsx or Users page
    - Show pending invitations with resend/revoke options
    - Add SecurityRoles: SEND_INVITATIONS, MANAGE_INVITATIONS

--------------------------------------------------------------------------------

29. Platform-Native Logging
    Log to OS-appropriate locations with fallback.

    Features:
    - Use system log locations (/var/log, Windows Event Log)
    - Fallback to local directory if no access
    - Structured logging format
    - Log rotation

    Implementation Hints:
    - Server: Modify backend logging configuration
    - Check for /var/log/sysmanage directory, create if possible
    - Fallback to ./logs/ if permission denied
    - Use Python logging with RotatingFileHandler
    - Agent: Already has logging config in config file
    - Modify agent logging setup in main.py
    - Add Windows Event Log support using pywin32
    - Add syslog support for Linux/BSD using SysLogHandler
    - No new UI needed - configuration via config files
    - Document logging configuration in deployment guide
