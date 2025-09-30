"""
Models package for SysManage persistence layer.

This package splits the models into logical groups for better maintainability.
All models are re-exported here for backward compatibility.
"""

# Re-export all models for backward compatibility
from .core import *
from .hardware import *
from .operations import *
from .secret import *
from .host_certificate import *
from .host_role import *
from .grafana_integration import *
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
]
