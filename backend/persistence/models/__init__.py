"""
Models package for SysManage persistence layer.

This package splits the models into logical groups for better maintainability.
All models are re-exported here for backward compatibility.
"""

# Re-export all models for backward compatibility
from .child_host import *
from .core import *
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
    "ChildHostDistribution",
    # Pro+ models
    "ProPlusLicense",
    "ProPlusLicenseValidationLog",
    "ProPlusModuleCache",
    "HostHealthAnalysis",
]
