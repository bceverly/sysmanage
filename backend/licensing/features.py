"""
Feature and module code definitions for Pro+ licensing.

FeatureCode: Individual features that can be enabled by a license
ModuleCode: Cython modules that can be downloaded and loaded dynamically
"""

from enum import Enum


class FeatureCode(str, Enum):
    """
    Feature codes that can be enabled by a Pro+ license.
    Each feature represents a specific capability in the system.
    """

    # Health Analysis Features
    HEALTH_ANALYSIS = "health"  # Matches license server feature code
    HEALTH_HISTORY = "health_history"
    HEALTH_ALERTS = "health_alerts"
    HEALTH_REPORTS = "health_reports"

    # Advanced Monitoring Features
    ADVANCED_MONITORING = "advanced_monitoring"
    PERFORMANCE_ANALYTICS = "performance_analytics"
    PREDICTIVE_MAINTENANCE = "predictive_maintenance"

    # Security Features
    VULNERABILITY_SCANNING = "vulnerability_scanning"
    COMPLIANCE_REPORTS = "compliance_reports"
    SECURITY_HARDENING = "security_hardening"

    # Automation Features
    AUTO_REMEDIATION = "auto_remediation"
    WORKFLOW_AUTOMATION = "workflow_automation"
    SCHEDULED_TASKS = "scheduled_tasks"

    # Integration Features
    SIEM_INTEGRATION = "siem_integration"
    API_EXTENDED = "api_extended"
    WEBHOOK_ADVANCED = "webhook_advanced"

    # Reporting Features
    CUSTOM_REPORTS = "custom_reports"
    EXECUTIVE_DASHBOARD = "executive_dashboard"
    EXPORT_PDF = "export_pdf"

    @classmethod
    def from_string(cls, value: str) -> "FeatureCode":
        """Convert string to FeatureCode enum."""
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"Unknown feature code: {value}") from exc


class ModuleCode(str, Enum):
    """
    Module codes for Pro+ Cython modules.
    Each module is a compiled Cython extension that provides specific functionality.
    """

    # Core Analysis Modules
    HEALTH_ENGINE = "health_engine"
    SECURITY_SCANNER = "security_scanner"
    PERFORMANCE_ANALYZER = "performance_analyzer"

    # AI/ML Modules
    ANOMALY_DETECTOR = "anomaly_detector"
    PREDICTION_ENGINE = "prediction_engine"

    # Data Processing Modules
    LOG_ANALYZER = "log_analyzer"
    METRICS_AGGREGATOR = "metrics_aggregator"

    @classmethod
    def from_string(cls, value: str) -> "ModuleCode":
        """Convert string to ModuleCode enum."""
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"Unknown module code: {value}") from exc


class LicenseTier(str, Enum):
    """
    License tier levels.
    """

    COMMUNITY = "community"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


# Mapping of tiers to their included features
TIER_FEATURES = {
    LicenseTier.COMMUNITY: set(),
    LicenseTier.PROFESSIONAL: {
        FeatureCode.HEALTH_ANALYSIS,
        FeatureCode.HEALTH_HISTORY,
        FeatureCode.ADVANCED_MONITORING,
        FeatureCode.CUSTOM_REPORTS,
    },
    LicenseTier.ENTERPRISE: {
        # All professional features
        FeatureCode.HEALTH_ANALYSIS,
        FeatureCode.HEALTH_HISTORY,
        FeatureCode.HEALTH_ALERTS,
        FeatureCode.HEALTH_REPORTS,
        FeatureCode.ADVANCED_MONITORING,
        FeatureCode.PERFORMANCE_ANALYTICS,
        FeatureCode.PREDICTIVE_MAINTENANCE,
        FeatureCode.VULNERABILITY_SCANNING,
        FeatureCode.COMPLIANCE_REPORTS,
        FeatureCode.SECURITY_HARDENING,
        FeatureCode.AUTO_REMEDIATION,
        FeatureCode.WORKFLOW_AUTOMATION,
        FeatureCode.SCHEDULED_TASKS,
        FeatureCode.SIEM_INTEGRATION,
        FeatureCode.API_EXTENDED,
        FeatureCode.WEBHOOK_ADVANCED,
        FeatureCode.CUSTOM_REPORTS,
        FeatureCode.EXECUTIVE_DASHBOARD,
        FeatureCode.EXPORT_PDF,
    },
}

# Mapping of tiers to their included modules
TIER_MODULES = {
    LicenseTier.COMMUNITY: set(),
    LicenseTier.PROFESSIONAL: {
        ModuleCode.HEALTH_ENGINE,
    },
    LicenseTier.ENTERPRISE: {
        ModuleCode.HEALTH_ENGINE,
        ModuleCode.SECURITY_SCANNER,
        ModuleCode.PERFORMANCE_ANALYZER,
        ModuleCode.ANOMALY_DETECTOR,
        ModuleCode.PREDICTION_ENGINE,
        ModuleCode.LOG_ANALYZER,
        ModuleCode.METRICS_AGGREGATOR,
    },
}
