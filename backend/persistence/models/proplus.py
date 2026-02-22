"""
Pro+ licensing and health analysis models for SysManage.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Constants
HOST_ID_FK = "host.id"
CASCADE_DELETE = "CASCADE"
CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
SET_NULL = "SET NULL"


class ProPlusLicense(Base):
    """
    Pro+ license storage model.
    Stores validated license information and phone-home status.
    """

    __tablename__ = "proplus_license"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    license_key_hash = Column(String(128), nullable=False)
    license_id = Column(String(36), nullable=False, unique=True)
    tier = Column(String(20), nullable=False)  # e.g., "professional", "enterprise"
    features = Column(JSON, nullable=False)  # List of enabled feature codes
    modules = Column(JSON, nullable=False)  # List of available module codes
    expires_at = Column(DateTime, nullable=False)
    offline_days = Column(Integer, nullable=False, default=30)
    last_phone_home_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<ProPlusLicense(id={self.id}, license_id='{self.license_id}', tier='{self.tier}', is_active={self.is_active})>"


class ProPlusLicenseValidationLog(Base):
    """
    Log of license validation attempts for audit purposes.
    """

    __tablename__ = "proplus_license_validation_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    license_id = Column(String(36), nullable=True, index=True)
    validation_type = Column(
        String(50), nullable=False
    )  # "local", "phone_home", "revocation_check"
    result = Column(String(20), nullable=False)  # "success", "failure", "error"
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    validated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )

    def __repr__(self):
        return f"<ProPlusLicenseValidationLog(id={self.id}, license_id='{self.license_id}', result='{self.result}')>"


class ProPlusModuleCache(Base):
    """
    Cache of downloaded Pro+ Cython modules.
    Tracks downloaded modules with their versions and file hashes.
    """

    __tablename__ = "proplus_module_cache"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    module_code = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    platform = Column(String(50), nullable=False)  # e.g., "linux", "windows", "darwin"
    architecture = Column(String(20), nullable=False)  # e.g., "x86_64", "aarch64"
    python_version = Column(String(10), nullable=False)  # e.g., "3.11", "3.12"
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(128), nullable=False)  # SHA-512 hash
    downloaded_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Unique constraint on module_code + version + platform + architecture + python_version
    __table_args__ = (
        {
            "sqlite_autoincrement": True,
        },
    )

    def __repr__(self):
        return f"<ProPlusModuleCache(module_code='{self.module_code}', version='{self.version}', platform='{self.platform}')>"


class HostHealthAnalysis(Base):
    """
    AI-powered health analysis results for hosts.
    Stores health scores, grades, issues, and recommendations.
    """

    __tablename__ = "host_health_analysis"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    analyzed_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    score = Column(Integer, nullable=False)  # 0-100 health score
    grade = Column(String(2), nullable=False)  # A+, A, B, C, D, F
    issues = Column(JSON, nullable=True)  # List of identified issues
    recommendations = Column(JSON, nullable=True)  # List of recommendations
    analysis_version = Column(
        String(20), nullable=True
    )  # Version of health_engine used
    raw_metrics = Column(JSON, nullable=True)  # Raw metrics used for analysis

    # Relationship to host
    host = relationship("Host", backref="health_analyses")

    def __repr__(self):
        return f"<HostHealthAnalysis(host_id={self.host_id}, score={self.score}, grade='{self.grade}')>"


class Vulnerability(Base):
    """
    Central vulnerability database storing CVE data.
    Ingested from NVD, Ubuntu Security API, Red Hat, Debian, FreeBSD VuXML, etc.
    """

    __tablename__ = "vulnerability"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    cve_id = Column(String(20), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    cvss_score = Column(String(10), nullable=True)  # Store as string to handle "N/A"
    cvss_version = Column(String(10), nullable=True)  # "2.0", "3.0", "3.1"
    severity = Column(String(20), nullable=True)  # CRITICAL, HIGH, MEDIUM, LOW, NONE
    published_date = Column(DateTime, nullable=True)
    modified_date = Column(DateTime, nullable=True)
    references = Column(JSON, nullable=True)  # List of reference URLs
    affected_systems = Column(JSON, nullable=True)  # OS/distro specifics
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationship to package vulnerabilities
    package_vulnerabilities = relationship(
        "PackageVulnerability",
        back_populates="vulnerability",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )

    def __repr__(self):
        return f"<Vulnerability(cve_id='{self.cve_id}', severity='{self.severity}', cvss={self.cvss_score})>"


class PackageVulnerability(Base):
    """
    Maps vulnerabilities to specific packages and package managers.
    Allows matching host software inventory against known vulnerabilities.
    """

    __tablename__ = "package_vulnerability"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    vulnerability_id = Column(
        GUID(),
        ForeignKey("vulnerability.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    package_name = Column(String(255), nullable=False, index=True)
    package_manager = Column(
        String(50), nullable=False, index=True
    )  # apt, dnf, brew, pkg, etc.
    vulnerable_versions = Column(
        String(500), nullable=True
    )  # Version constraint (e.g., "< 2.0.0")
    fixed_version = Column(
        String(100), nullable=True
    )  # Version where vulnerability is fixed
    advisory_ids = Column(JSON, nullable=True)  # Related advisories (USN, RHSA, etc.)
    source = Column(
        String(100), nullable=True
    )  # Data source (nvd, ubuntu, redhat, etc.)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationship to vulnerability
    vulnerability = relationship(
        "Vulnerability", back_populates="package_vulnerabilities"
    )

    def __repr__(self):
        return f"<PackageVulnerability(package='{self.package_name}', manager='{self.package_manager}', vuln_id={self.vulnerability_id})>"


class HostVulnerabilityScan(Base):
    """
    Stores vulnerability scan results for hosts.
    Generated by running the security_scanner module against host software inventory.
    """

    __tablename__ = "host_vulnerability_scan"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    scanned_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    total_packages = Column(Integer, nullable=False, default=0)
    vulnerable_packages = Column(Integer, nullable=False, default=0)
    total_vulnerabilities = Column(Integer, nullable=False, default=0)
    critical_count = Column(Integer, nullable=False, default=0)
    high_count = Column(Integer, nullable=False, default=0)
    medium_count = Column(Integer, nullable=False, default=0)
    low_count = Column(Integer, nullable=False, default=0)
    risk_score = Column(Integer, nullable=False, default=0)  # 0-100
    risk_level = Column(String(20), nullable=True)  # CRITICAL, HIGH, MEDIUM, LOW, NONE
    summary = Column(Text, nullable=True)
    recommendations = Column(JSON, nullable=True)  # List of recommendations
    scanner_version = Column(
        String(20), nullable=True
    )  # Version of security_scanner used

    # Relationship to host
    host = relationship("Host", backref="vulnerability_scans")

    # Relationship to individual findings
    findings = relationship(
        "HostVulnerabilityFinding",
        back_populates="scan",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )

    def __repr__(self):
        return f"<HostVulnerabilityScan(host_id={self.host_id}, total={self.total_vulnerabilities}, critical={self.critical_count})>"


class HostVulnerabilityFinding(Base):
    """
    Individual vulnerability findings from a host scan.
    Links specific CVEs to hosts with package details.
    """

    __tablename__ = "host_vulnerability_finding"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    scan_id = Column(
        GUID(),
        ForeignKey("host_vulnerability_scan.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    vulnerability_id = Column(
        GUID(),
        ForeignKey("vulnerability.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    package_name = Column(String(255), nullable=False)
    installed_version = Column(String(100), nullable=False)
    fixed_version = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=False)
    cvss_score = Column(String(10), nullable=True)
    remediation = Column(Text, nullable=True)

    # Relationships
    scan = relationship("HostVulnerabilityScan", back_populates="findings")
    vulnerability = relationship("Vulnerability")

    def __repr__(self):
        return f"<HostVulnerabilityFinding(package='{self.package_name}', severity='{self.severity}')>"


class VulnerabilityIngestionLog(Base):
    """
    Log of vulnerability data ingestion runs.
    Tracks when data was fetched from each source.
    """

    __tablename__ = "vulnerability_ingestion_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    source = Column(
        String(100), nullable=False, index=True
    )  # nvd, ubuntu, redhat, debian, etc.
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)  # running, success, failed
    vulnerabilities_processed = Column(Integer, nullable=True)
    packages_processed = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<VulnerabilityIngestionLog(source='{self.source}', status='{self.status}')>"


class CveRefreshSettings(Base):
    """
    Settings for CVE database refresh scheduling and configuration.
    Stores refresh frequency, enabled sources, and last refresh timestamp.
    """

    __tablename__ = "cve_refresh_settings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    refresh_interval_hours = Column(
        Integer, nullable=False, default=24
    )  # Default: daily
    enabled_sources = Column(
        JSON, nullable=False, default=lambda: ["nvd", "ubuntu", "debian", "redhat"]
    )  # List of enabled CVE sources
    last_refresh_at = Column(DateTime, nullable=True)
    next_refresh_at = Column(DateTime, nullable=True)
    nvd_api_key = Column(
        String(255), nullable=True
    )  # Optional NVD API key for higher rate limits
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<CveRefreshSettings(enabled={self.enabled}, interval_hours={self.refresh_interval_hours})>"


class ComplianceProfile(Base):
    """
    Compliance profile defining a set of rules to check.
    Can be based on CIS, STIG, or custom rules.
    """

    __tablename__ = "compliance_profile"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    benchmark_type = Column(
        String(50), nullable=False, default="CUSTOM"
    )  # CIS, STIG, CUSTOM
    enabled = Column(Boolean, nullable=False, default=True)
    rules = Column(JSON, nullable=True)  # List of custom rule definitions
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<ComplianceProfile(name='{self.name}', benchmark_type='{self.benchmark_type}')>"


class ProPlusPluginCache(Base):
    """
    Cache of downloaded Pro+ JavaScript plugin bundles.
    Tracks downloaded plugin bundles with their versions and file hashes.
    """

    __tablename__ = "proplus_plugin_cache"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    module_code = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(128), nullable=False)  # SHA-512 hash
    downloaded_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<ProPlusPluginCache(module_code='{self.module_code}', version='{self.version}')>"


class NotificationChannel(Base):
    """
    Notification channel configuration for the alerting engine.
    Stores connection details for email, webhook, Slack, and Teams channels.
    """

    __tablename__ = "notification_channel"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    channel_type = Column(
        String(50), nullable=False
    )  # "email", "webhook", "slack", "teams"
    config = Column(JSON, nullable=False)  # Channel-specific configuration
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<NotificationChannel(name='{self.name}', type='{self.channel_type}', enabled={self.enabled})>"


class AlertRule(Base):
    """
    Alert rule definition for the alerting engine.
    Defines conditions that trigger alerts and their severity.
    """

    __tablename__ = "alert_rule"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    condition_type = Column(
        String(50), nullable=False
    )  # "host_down", "reboot_required", "updates_available", "disk_usage", "cve_severity", "custom_metric"
    condition_params = Column(JSON, nullable=False)  # Condition-specific parameters
    severity = Column(
        String(20), nullable=False
    )  # "critical", "high", "medium", "low", "info"
    enabled = Column(Boolean, nullable=False, default=True)
    cooldown_minutes = Column(
        Integer, nullable=False, default=60
    )  # Min time between re-alerts for same host+rule
    host_filter = Column(
        JSON, nullable=True
    )  # Optional tag-based filter e.g. {"tags": ["production"]}
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationship to notification channels via junction table
    notification_channels = relationship(
        "AlertRuleNotificationChannel",
        back_populates="rule",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )

    def __repr__(self):
        return f"<AlertRule(name='{self.name}', condition='{self.condition_type}', severity='{self.severity}')>"


class AlertRuleNotificationChannel(Base):
    """
    Junction table linking alert rules to notification channels (M:N).
    """

    __tablename__ = "alert_rule_notification_channel"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    rule_id = Column(
        GUID(),
        ForeignKey("alert_rule.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    channel_id = Column(
        GUID(),
        ForeignKey("notification_channel.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )

    # Relationships
    rule = relationship("AlertRule", back_populates="notification_channels")
    channel = relationship("NotificationChannel")

    def __repr__(self):
        return f"<AlertRuleNotificationChannel(rule_id={self.rule_id}, channel_id={self.channel_id})>"


class Alert(Base):
    """
    Fired alert instance from the alerting engine.
    Records when a condition was triggered for a specific host.
    """

    __tablename__ = "alert"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    rule_id = Column(
        GUID(),
        ForeignKey("alert_rule.id", ondelete=SET_NULL),
        nullable=True,
        index=True,
    )
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    severity = Column(String(20), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)  # Condition-specific data snapshot
    triggered_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(255), nullable=True)  # Username
    resolved_at = Column(DateTime, nullable=True)
    notification_sent = Column(Boolean, nullable=False, default=False)

    # Relationships
    rule = relationship("AlertRule")
    host = relationship("Host", backref="alerts")

    def __repr__(self):
        return f"<Alert(title='{self.title}', severity='{self.severity}', host_id={self.host_id})>"


class ScheduledReport(Base):
    """
    Scheduled report configuration.
    Defines a report to be generated on a recurring schedule
    and delivered via notification channels.
    """

    __tablename__ = "scheduled_report"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False)  # matches ReportTypeEnum values
    schedule_type = Column(String(20), nullable=False)  # "daily", "weekly", "monthly"
    schedule_config = Column(
        JSON, nullable=False
    )  # e.g. {"day_of_week": "monday", "hour": 8}
    output_format = Column(String(10), nullable=False, default="pdf")  # "pdf" or "html"
    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=False)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Relationship to notification channels via junction table
    channels = relationship(
        "ScheduledReportChannel",
        back_populates="scheduled_report",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )

    def __repr__(self):
        return f"<ScheduledReport(name='{self.name}', type='{self.report_type}', schedule='{self.schedule_type}')>"


class ScheduledReportChannel(Base):
    """
    Junction table linking scheduled reports to notification channels (M:N).
    """

    __tablename__ = "scheduled_report_channel"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    scheduled_report_id = Column(
        GUID(),
        ForeignKey("scheduled_report.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    channel_id = Column(
        GUID(),
        ForeignKey("notification_channel.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )

    # Relationships
    scheduled_report = relationship("ScheduledReport", back_populates="channels")
    channel = relationship("NotificationChannel")

    def __repr__(self):
        return f"<ScheduledReportChannel(report_id={self.scheduled_report_id}, channel_id={self.channel_id})>"


class AuditRetentionPolicy(Base):
    """
    Audit log retention policy.
    Defines rules for automatic deletion or archival of old audit entries.
    """

    __tablename__ = "audit_retention_policy"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    retention_days = Column(Integer, nullable=False)  # 1-3650
    action = Column(String(20), nullable=False)  # "delete" or "archive"
    entity_types = Column(JSON, nullable=True)  # filter by entity type
    action_types = Column(JSON, nullable=True)  # filter by action type
    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    entries_processed = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<AuditRetentionPolicy(name='{self.name}', days={self.retention_days}, action='{self.action}')>"


class AuditLogArchive(Base):
    """
    Archived audit log entries.
    Stores audit entries that have been moved from the main audit_log table
    by a retention policy with action='archive'.
    """

    __tablename__ = "audit_log_archive"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, nullable=False, index=True)
    user_id = Column(GUID(), nullable=True, index=True)
    username = Column(String(255), nullable=True)
    action_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(255), nullable=True)
    entity_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    result = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    category = Column(String(50), nullable=True, index=True)
    entry_type = Column(String(50), nullable=True, index=True)
    archived_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    archived_by_policy_id = Column(
        GUID(),
        ForeignKey("audit_retention_policy.id", ondelete=SET_NULL),
        nullable=True,
    )

    # Relationship to retention policy
    archived_by_policy = relationship("AuditRetentionPolicy")

    def __repr__(self):
        return f"<AuditLogArchive(id={self.id}, user='{self.username}', action='{self.action_type}')>"


class SecretVersion(Base):
    """
    Secret version history.
    Tracks each version of a secret with a content fingerprint (no actual content stored).
    """

    __tablename__ = "secret_version"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    secret_id = Column(
        GUID(),
        ForeignKey("secrets.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    version_number = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=True)  # SHA-256 fingerprint
    created_at = Column(
        DateTime,
        nullable=True,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created_by = Column(String(255), nullable=True)
    change_description = Column(String(500), nullable=True)

    __table_args__ = ({"sqlite_autoincrement": True},)

    def __repr__(self):
        return f"<SecretVersion(secret_id={self.secret_id}, version={self.version_number})>"


class RotationSchedule(Base):
    """
    Credential rotation schedule.
    Defines automatic rotation policies for secrets.
    """

    __tablename__ = "rotation_schedule"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    secret_id = Column(
        GUID(),
        ForeignKey("secrets.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    frequency = Column(
        String(20), nullable=False
    )  # daily, weekly, monthly, quarterly, yearly
    notify_days_before = Column(Integer, nullable=False, default=7)
    auto_rotate = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    next_rotation = Column(DateTime, nullable=True)
    last_rotation = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    def __repr__(self):
        return f"<RotationSchedule(secret_id={self.secret_id}, frequency='{self.frequency}')>"


class HostComplianceScan(Base):
    """
    Stores compliance scan results for hosts.
    Generated by running the compliance_engine module against host diagnostics.
    """

    __tablename__ = "host_compliance_scan"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    profile_id = Column(
        GUID(),
        ForeignKey("compliance_profile.id", ondelete=SET_NULL),
        nullable=True,
        index=True,
    )
    scanned_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    total_rules = Column(Integer, nullable=False, default=0)
    passed_rules = Column(Integer, nullable=False, default=0)
    failed_rules = Column(Integer, nullable=False, default=0)
    error_rules = Column(Integer, nullable=False, default=0)
    not_applicable_rules = Column(Integer, nullable=False, default=0)
    compliance_score = Column(Integer, nullable=False, default=0)  # 0-100
    compliance_grade = Column(
        String(2), nullable=False, default="F"
    )  # A+, A, B, C, D, F
    critical_failures = Column(Integer, nullable=False, default=0)
    high_failures = Column(Integer, nullable=False, default=0)
    medium_failures = Column(Integer, nullable=False, default=0)
    low_failures = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=True)
    results = Column(JSON, nullable=True)  # List of rule check results
    scanner_version = Column(
        String(20), nullable=True
    )  # Version of compliance_engine used

    # Relationships
    host = relationship("Host", backref="compliance_scans")
    profile = relationship("ComplianceProfile")

    def __repr__(self):
        return f"<HostComplianceScan(host_id={self.host_id}, score={self.compliance_score}, grade='{self.compliance_grade}')>"
