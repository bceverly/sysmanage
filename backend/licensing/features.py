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
    HEALTH_ALERTS = "alerts"  # Matches license server feature code
    HEALTH_REPORTS = "reports"  # Matches license server feature code

    # Advanced Monitoring Features
    ADVANCED_MONITORING = "advanced_monitoring"
    PERFORMANCE_ANALYTICS = "performance_analytics"
    PREDICTIVE_MAINTENANCE = "predictive_maintenance"

    # Security Features
    VULNERABILITY_SCANNING = "vuln"  # Matches license server feature code
    COMPLIANCE_REPORTS = "compliance"  # Matches license server feature code
    SECURITY_HARDENING = "security_hardening"

    # Automation Features
    AUTO_REMEDIATION = "auto_remediation"
    WORKFLOW_AUTOMATION = "workflow_automation"
    SCHEDULED_TASKS = "scheduled_tasks"

    # Integration Features
    SIEM_INTEGRATION = "siem_integration"
    API_EXTENDED = "api"  # Matches license server feature code
    WEBHOOK_ADVANCED = "webhook_advanced"

    # Reporting Features
    CUSTOM_REPORTS = "custom_reports"
    EXECUTIVE_DASHBOARD = "executive_dashboard"
    EXPORT_PDF = "export_pdf"

    # AV Management Engine (Phase 3)
    AV_INSTALL = "av_install"
    AV_UNINSTALL = "av_uninstall"
    AV_STATUS = "av_status"
    AV_SCAN = "av_scan"
    COMMERCIAL_AV_DETECT = "commercial_av_detect"

    # Firewall Orchestration Engine (Phase 3)
    FIREWALL_ROLE_DEFINE = "firewall_role_define"
    FIREWALL_ROLE_ASSIGN = "firewall_role_assign"
    FIREWALL_DEPLOY = "firewall_deploy"
    FIREWALL_STATUS = "firewall_status"
    FIREWALL_COMPLIANCE_CHECK = "firewall_compliance_check"

    # Automation Engine (Phase 5)
    AUTOMATION_SCRIPT_LIBRARY = "automation_script_library"
    AUTOMATION_SCRIPT_EXEC = "automation_script_exec"
    AUTOMATION_SCRIPT_SCHEDULE = "automation_script_schedule"
    AUTOMATION_SCRIPT_APPROVAL = "automation_script_approval"

    # Fleet Engine (Phase 5)
    FLEET_GROUPS = "fleet_groups"
    FLEET_BULK_OPERATIONS = "fleet_bulk_operations"
    FLEET_ROLLING_DEPLOYMENTS = "fleet_rolling_deployments"
    FLEET_SCHEDULED_OPERATIONS = "fleet_scheduled_operations"
    FLEET_CONFIG_DEPLOYMENT = "fleet_config_deployment"

    # Virtualization Engine (Phase 10.1)
    VIRTUALIZATION_KVM_LIFECYCLE = "virtualization_kvm_lifecycle"
    VIRTUALIZATION_KVM_CREATE = "virtualization_kvm_create"
    VIRTUALIZATION_KVM_DELETE = "virtualization_kvm_delete"
    VIRTUALIZATION_KVM_STORAGE = "virtualization_kvm_storage"
    VIRTUALIZATION_KVM_NETWORKING = "virtualization_kvm_networking"
    VIRTUALIZATION_BHYVE_LIFECYCLE = "virtualization_bhyve_lifecycle"
    VIRTUALIZATION_BHYVE_CREATE = "virtualization_bhyve_create"
    VIRTUALIZATION_BHYVE_STORAGE = "virtualization_bhyve_storage"
    VIRTUALIZATION_VMM_LIFECYCLE = "virtualization_vmm_lifecycle"
    VIRTUALIZATION_VMM_CREATE = "virtualization_vmm_create"
    VIRTUALIZATION_GUEST_PROVISIONING = "virtualization_guest_provisioning"
    VIRTUALIZATION_SAFE_REBOOT = "virtualization_safe_reboot"

    # Observability Engine (Phase 10.2)
    OBSERVABILITY_OTEL_DEPLOY = "observability_otel_deploy"
    OBSERVABILITY_OTEL_REMOVE = "observability_otel_remove"
    OBSERVABILITY_GRAYLOG_DEPLOY = "observability_graylog_deploy"
    OBSERVABILITY_GRAFANA_PROVISION = "observability_grafana_provision"
    OBSERVABILITY_TELEMETRY_ROUTING = "observability_telemetry_routing"

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
    SECURITY_SCANNER = "security_scanner"  # Legacy alias
    VULN_ENGINE = "vuln_engine"  # Renamed from security_scanner
    COMPLIANCE_ENGINE = "compliance_engine"
    PERFORMANCE_ANALYZER = "performance_analyzer"

    # AI/ML Modules
    ANOMALY_DETECTOR = "anomaly_detector"
    PREDICTION_ENGINE = "prediction_engine"

    # Plugin-only Modules (no Cython)
    PROPLUS_CORE = "proplus_core"

    # Alerting Modules
    ALERTING_ENGINE = "alerting_engine"

    # Reporting Modules
    REPORTING_ENGINE = "reporting_engine"

    # Audit Modules
    AUDIT_ENGINE = "audit_engine"

    # Secrets Modules
    SECRETS_ENGINE = "secrets_engine"

    # Container Modules
    CONTAINER_ENGINE = "container_engine"

    # Phase 3 Enterprise modules
    AV_MANAGEMENT_ENGINE = "av_management_engine"
    FIREWALL_ORCHESTRATION_ENGINE = "firewall_orchestration_engine"

    # Phase 5 Enterprise modules
    AUTOMATION_ENGINE = "automation_engine"
    FLEET_ENGINE = "fleet_engine"

    # Phase 10 Enterprise modules
    VIRTUALIZATION_ENGINE = "virtualization_engine"
    OBSERVABILITY_ENGINE = "observability_engine"
    REPOSITORY_MIRRORING_ENGINE = "repository_mirroring_engine"
    EXTERNAL_IDP_ENGINE = "external_idp_engine"

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
        FeatureCode.VULNERABILITY_SCANNING,
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
        # Phase 3
        FeatureCode.AV_INSTALL,
        FeatureCode.AV_UNINSTALL,
        FeatureCode.AV_STATUS,
        FeatureCode.AV_SCAN,
        FeatureCode.COMMERCIAL_AV_DETECT,
        FeatureCode.FIREWALL_ROLE_DEFINE,
        FeatureCode.FIREWALL_ROLE_ASSIGN,
        FeatureCode.FIREWALL_DEPLOY,
        FeatureCode.FIREWALL_STATUS,
        FeatureCode.FIREWALL_COMPLIANCE_CHECK,
        # Phase 5
        FeatureCode.AUTOMATION_SCRIPT_LIBRARY,
        FeatureCode.AUTOMATION_SCRIPT_EXEC,
        FeatureCode.AUTOMATION_SCRIPT_SCHEDULE,
        FeatureCode.AUTOMATION_SCRIPT_APPROVAL,
        FeatureCode.FLEET_GROUPS,
        FeatureCode.FLEET_BULK_OPERATIONS,
        FeatureCode.FLEET_ROLLING_DEPLOYMENTS,
        FeatureCode.FLEET_SCHEDULED_OPERATIONS,
        FeatureCode.FLEET_CONFIG_DEPLOYMENT,
        # Phase 10.1 — virtualization
        FeatureCode.VIRTUALIZATION_KVM_LIFECYCLE,
        FeatureCode.VIRTUALIZATION_KVM_CREATE,
        FeatureCode.VIRTUALIZATION_KVM_DELETE,
        FeatureCode.VIRTUALIZATION_KVM_STORAGE,
        FeatureCode.VIRTUALIZATION_KVM_NETWORKING,
        FeatureCode.VIRTUALIZATION_BHYVE_LIFECYCLE,
        FeatureCode.VIRTUALIZATION_BHYVE_CREATE,
        FeatureCode.VIRTUALIZATION_BHYVE_STORAGE,
        FeatureCode.VIRTUALIZATION_VMM_LIFECYCLE,
        FeatureCode.VIRTUALIZATION_VMM_CREATE,
        FeatureCode.VIRTUALIZATION_GUEST_PROVISIONING,
        FeatureCode.VIRTUALIZATION_SAFE_REBOOT,
        # Phase 10.2 — observability
        FeatureCode.OBSERVABILITY_OTEL_DEPLOY,
        FeatureCode.OBSERVABILITY_OTEL_REMOVE,
        FeatureCode.OBSERVABILITY_GRAYLOG_DEPLOY,
        FeatureCode.OBSERVABILITY_GRAFANA_PROVISION,
        FeatureCode.OBSERVABILITY_TELEMETRY_ROUTING,
    },
}

# Mapping of tiers to their included modules
TIER_MODULES = {
    LicenseTier.COMMUNITY: set(),
    LicenseTier.PROFESSIONAL: {
        ModuleCode.HEALTH_ENGINE,
        ModuleCode.SECURITY_SCANNER,
        ModuleCode.VULN_ENGINE,
        ModuleCode.COMPLIANCE_ENGINE,
        ModuleCode.ALERTING_ENGINE,
        ModuleCode.REPORTING_ENGINE,
        ModuleCode.AUDIT_ENGINE,
        ModuleCode.SECRETS_ENGINE,
        ModuleCode.CONTAINER_ENGINE,
        ModuleCode.PROPLUS_CORE,
    },
    LicenseTier.ENTERPRISE: {
        ModuleCode.HEALTH_ENGINE,
        ModuleCode.SECURITY_SCANNER,
        ModuleCode.VULN_ENGINE,
        ModuleCode.COMPLIANCE_ENGINE,
        ModuleCode.ALERTING_ENGINE,
        ModuleCode.REPORTING_ENGINE,
        ModuleCode.AUDIT_ENGINE,
        ModuleCode.SECRETS_ENGINE,
        ModuleCode.CONTAINER_ENGINE,
        ModuleCode.PROPLUS_CORE,
        ModuleCode.PERFORMANCE_ANALYZER,
        ModuleCode.ANOMALY_DETECTOR,
        ModuleCode.PREDICTION_ENGINE,
        ModuleCode.LOG_ANALYZER,
        ModuleCode.METRICS_AGGREGATOR,
        # Phase 3
        ModuleCode.AV_MANAGEMENT_ENGINE,
        ModuleCode.FIREWALL_ORCHESTRATION_ENGINE,
        # Phase 5
        ModuleCode.AUTOMATION_ENGINE,
        ModuleCode.FLEET_ENGINE,
        # Phase 10
        ModuleCode.VIRTUALIZATION_ENGINE,
        ModuleCode.OBSERVABILITY_ENGINE,
        ModuleCode.REPOSITORY_MIRRORING_ENGINE,
        ModuleCode.EXTERNAL_IDP_ENGINE,
    },
}
