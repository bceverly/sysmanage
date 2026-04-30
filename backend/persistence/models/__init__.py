"""
Models package for SysManage persistence layer.

This package splits the models into logical groups for better maintainability.
All models are re-exported here for backward compatibility.
"""

# Re-export all models for backward compatibility
from .access_groups import *
from .child_host import *
from .core import *
from .dynamic_secrets import *
from .package_compliance import *
from .report_branding import *
from .upgrade_profiles import *
from .grafana_integration import *
from .graylog_attachment import *
from .graylog_integration import *
from .hardware import *
from .host_certificate import *
from .host_role import *
from .operations import *
from .proplus import *
from .secret import *
from .software import *

__all__ = [
    # Core models
    "BearerToken",
    "Host",
    "User",
    "generate_secure_host_token",
    # Hardware models
    "StorageDevice",
    "NetworkInterface",
    # Software models
    "SoftwarePackage",
    "PackageUpdate",
    "AvailablePackage",
    "SoftwareInstallationLog",
    "InstallationRequest",
    "InstallationPackage",
    "ThirdPartyRepository",
    "AntivirusDefault",
    "AntivirusStatus",
    "CommercialAntivirusStatus",
    "FirewallStatus",
    # User management models
    "UserAccount",
    "UserGroup",
    "UserGroupMembership",
    # Operations models
    "UpdateExecutionLog",
    "MessageQueue",
    "QueueMetrics",
    "SavedScript",
    "ScriptExecutionLog",
    "DiagnosticReport",
    # Organization models
    "Tag",
    "HostTag",
    "PasswordResetToken",
    "UbuntuProInfo",
    "UbuntuProService",
    "UbuntuProSettings",
    # Secret models
    "Secret",
    # Certificate models
    "HostCertificate",
    # Role models
    "HostRole",
    # Grafana integration models
    "GrafanaIntegrationSettings",
    # Graylog integration models
    "GraylogIntegrationSettings",
    "GraylogAttachment",
    # Security role models
    "SecurityRoleGroup",
    "SecurityRole",
    "UserSecurityRole",
    # User preference models
    "UserDataGridColumnPreference",
    "UserDashboardCardPreference",
    # Audit models
    "AuditLog",
    # Default repository models
    "DefaultRepository",
    # Firewall role models
    "FirewallRole",
    "FirewallRoleOpenPort",
    "HostFirewallRole",
    # Enabled package manager models
    "EnabledPackageManager",
    # Child host models
    "HostChild",
    "ChildHost",
    "ChildHostDistribution",
    "RebootOrchestration",
    # Pro+ models
    "ProPlusLicense",
    "ProPlusLicenseValidationLog",
    "ProPlusModuleCache",
    "ProPlusPluginCache",
    "HostHealthAnalysis",
    # Vulnerability tracking models
    "Vulnerability",
    "PackageVulnerability",
    "HostVulnerabilityScan",
    "HostVulnerabilityFinding",
    "VulnerabilityIngestionLog",
    "CveRefreshSettings",
    # Compliance models
    "ComplianceProfile",
    "HostComplianceScan",
    # Alerting models
    "NotificationChannel",
    "AlertRule",
    "AlertRuleNotificationChannel",
    "Alert",
    # Scheduled report models
    "ScheduledReport",
    "ScheduledReportChannel",
    # Audit retention models
    "AuditRetentionPolicy",
    "AuditLogArchive",
    # Secret versioning and rotation models
    "SecretVersion",
    "RotationSchedule",
    # Access group / registration key models (Phase 8.1)
    "AccessGroup",
    "RegistrationKey",
    "HostAccessGroup",
    "UserAccessGroup",
    "generate_registration_key",
    # Upgrade-profile model (Phase 8.2)
    "UpgradeProfile",
    # Package-compliance models (Phase 8.3)
    "PackageProfile",
    "PackageProfileConstraint",
    "HostPackageComplianceStatus",
    # Report templates + branding (Phase 8.7)
    "ReportBranding",
    "ReportTemplate",
    "SINGLETON_BRANDING_ID",
    # Dynamic secret leases (Phase 8.7)
    "DynamicSecretLease",
    "LEASE_ACTIVE",
    "LEASE_REVOKED",
    "LEASE_EXPIRED",
    "LEASE_FAILED",
    "LEASE_STATUSES",
    "LEASE_KINDS",
    "LEASE_KIND_DATABASE",
    "LEASE_KIND_SSH",
    "LEASE_KIND_TOKEN",
]

# Alias for Cython modules that reference ChildHost instead of HostChild
ChildHost = HostChild
