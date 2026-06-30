"""
Models package for SysManage persistence layer.

This package splits the models into logical groups for better maintainability.
All models are re-exported here for backward compatibility.
"""

# Re-export all models for backward compatibility
from .access_groups import *
from .api_key import *
from .airgap import *
from .airgap_bundle import *
from .child_host import *
from .core import *
from .dynamic_secrets import *
from .external_idp import *
from .federation import *
from .mfa import *
from .package_compliance import *
from .report_branding import *
from .repository_mirroring import *
from .upgrade_profiles import *
from .grafana_integration import *
from .graylog_attachment import *
from .graylog_integration import *
from .hardware import *
from .host_certificate import *
from .host_role import *
from .operations import *
from .processes import *
from .proplus import *
from .secret import *
from .server_configuration import *
from .software import *
from .tenancy import *

__all__ = [
    # Core models
    "BearerToken",
    "Host",
    "User",
    "generate_secure_host_token",
    # API keys (Phase 13.2)
    "ApiKey",
    # Server-wide configuration singleton
    "ServerConfiguration",
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
    # Process management models (Phase 13.3)
    "HostProcess",
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
    "UserInvitation",
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
    # Multi-factor authentication (Phase 10.3)
    "UserMfaEnrollment",
    "MfaSettings",
    "MfaEmailChallenge",
    "SINGLETON_MFA_SETTINGS_ID",
    # Repository mirroring (Phase 10.4)
    "MirrorRepository",
    "MirrorSnapshot",
    "MirrorSettings",
    "MirrorSetupStatus",
    "MirrorPlatformConfig",
    "MirrorKnownVersion",
    "HostDefaultMirror",
    "SINGLETON_MIRROR_SETTINGS_ID",
    # External Identity Providers (Phase 10.5)
    "ExternalIdpProvider",
    "IdpRoleMapping",
    "ExternalIdpSettings",
    "SINGLETON_IDP_SETTINGS_ID",
    # Multi-site federation (Phase 12.6)
    "FederationSite",
    "FederationHostDirectory",
    "FederationHostRollup",
    "FederationComplianceRollup",
    "FederationVulnerabilityRollup",
    "FederationPolicy",
    "FederationPolicyAssignment",
    "FederationDispatchedCommand",
    "FederationAuditLog",
    "FederationAlert",
    "FederationAlertConfig",
    "FederationSiteSyncEvent",
    "FederationSecretLease",
    "FederationReceivedSecretLease",
    "FederationCoordinator",
    "SINGLETON_FEDERATION_ALERT_CONFIG_ID",
    "FederationSyncQueue",
    "FederationReceivedPolicy",
    "FederationReceivedCommand",
    "SINGLETON_FEDERATION_COORDINATOR_ID",
    # Air-gap install bundles (multi-OS ISO builder)
    "AirGapBundle",
    "BUNDLE_PRODUCT_SERVER",
    "BUNDLE_PRODUCT_AGENT",
    "BUNDLE_PRODUCTS",
    "BUNDLE_STATUS_QUEUED",
    "BUNDLE_STATUS_BUILDING",
    "BUNDLE_STATUS_READY",
    "BUNDLE_STATUS_FAILED",
    "BUNDLE_STATUSES",
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
    # Multi-tenancy control-plane / registry (Phase 13.1.A)
    "RegistryTenant",
    "RegistryUser",
    "RegistryUserTenantGrant",
    "RegistryTenantPlacement",
    "RegistryTenantEmailDomain",
    "RegistryTenantDbVersion",
    "RegistryEnrollmentToken",
    "RegistryHostTenant",
    "TENANT_TIER_SILO",
    "TENANT_TIER_POOL",
    "TENANT_TIERS",
    "TENANT_STATUS_ACTIVE",
    "TENANT_STATUS_SUSPENDED",
    "TENANT_STATUS_PROVISIONING",
    "TENANT_STATUSES",
]

# Alias for Cython modules that reference ChildHost instead of HostChild
ChildHost = HostChild
