"""
Tests for backend/persistence/models/proplus.py module.
Tests all Pro+ licensing and health analysis models.
"""

import uuid
from datetime import datetime, timezone

import pytest


class TestProPlusLicenseModel:
    """Tests for ProPlusLicense model."""

    def test_table_name(self):
        """Test ProPlusLicense table name."""
        from backend.persistence.models.proplus import ProPlusLicense

        assert ProPlusLicense.__tablename__ == "proplus_license"

    def test_columns_exist(self):
        """Test ProPlusLicense has expected columns."""
        from backend.persistence.models.proplus import ProPlusLicense

        assert hasattr(ProPlusLicense, "id")
        assert hasattr(ProPlusLicense, "license_key_hash")
        assert hasattr(ProPlusLicense, "license_id")
        assert hasattr(ProPlusLicense, "tier")
        assert hasattr(ProPlusLicense, "features")
        assert hasattr(ProPlusLicense, "modules")
        assert hasattr(ProPlusLicense, "expires_at")
        assert hasattr(ProPlusLicense, "offline_days")
        assert hasattr(ProPlusLicense, "last_phone_home_at")
        assert hasattr(ProPlusLicense, "is_active")
        assert hasattr(ProPlusLicense, "created_at")
        assert hasattr(ProPlusLicense, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import ProPlusLicense

        license_obj = ProPlusLicense()
        license_obj.id = uuid.uuid4()
        license_obj.license_id = "abc-123-def"
        license_obj.tier = "professional"
        license_obj.is_active = True

        repr_str = repr(license_obj)

        assert "ProPlusLicense" in repr_str
        assert "abc-123-def" in repr_str
        assert "professional" in repr_str
        assert "True" in repr_str


class TestProPlusLicenseValidationLogModel:
    """Tests for ProPlusLicenseValidationLog model."""

    def test_table_name(self):
        """Test ProPlusLicenseValidationLog table name."""
        from backend.persistence.models.proplus import ProPlusLicenseValidationLog

        assert (
            ProPlusLicenseValidationLog.__tablename__
            == "proplus_license_validation_log"
        )

    def test_columns_exist(self):
        """Test ProPlusLicenseValidationLog has expected columns."""
        from backend.persistence.models.proplus import ProPlusLicenseValidationLog

        assert hasattr(ProPlusLicenseValidationLog, "id")
        assert hasattr(ProPlusLicenseValidationLog, "license_id")
        assert hasattr(ProPlusLicenseValidationLog, "validation_type")
        assert hasattr(ProPlusLicenseValidationLog, "result")
        assert hasattr(ProPlusLicenseValidationLog, "error_message")
        assert hasattr(ProPlusLicenseValidationLog, "details")
        assert hasattr(ProPlusLicenseValidationLog, "validated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import ProPlusLicenseValidationLog

        log = ProPlusLicenseValidationLog()
        log.id = uuid.uuid4()
        log.license_id = "abc-123"
        log.result = "success"

        repr_str = repr(log)

        assert "ProPlusLicenseValidationLog" in repr_str
        assert "abc-123" in repr_str
        assert "success" in repr_str


class TestProPlusModuleCacheModel:
    """Tests for ProPlusModuleCache model."""

    def test_table_name(self):
        """Test ProPlusModuleCache table name."""
        from backend.persistence.models.proplus import ProPlusModuleCache

        assert ProPlusModuleCache.__tablename__ == "proplus_module_cache"

    def test_columns_exist(self):
        """Test ProPlusModuleCache has expected columns."""
        from backend.persistence.models.proplus import ProPlusModuleCache

        assert hasattr(ProPlusModuleCache, "id")
        assert hasattr(ProPlusModuleCache, "module_code")
        assert hasattr(ProPlusModuleCache, "version")
        assert hasattr(ProPlusModuleCache, "platform")
        assert hasattr(ProPlusModuleCache, "architecture")
        assert hasattr(ProPlusModuleCache, "python_version")
        assert hasattr(ProPlusModuleCache, "file_path")
        assert hasattr(ProPlusModuleCache, "file_hash")
        assert hasattr(ProPlusModuleCache, "downloaded_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import ProPlusModuleCache

        cache = ProPlusModuleCache()
        cache.module_code = "health_engine"
        cache.version = "1.0.0"
        cache.platform = "linux"

        repr_str = repr(cache)

        assert "ProPlusModuleCache" in repr_str
        assert "health_engine" in repr_str
        assert "1.0.0" in repr_str
        assert "linux" in repr_str


class TestHostHealthAnalysisModel:
    """Tests for HostHealthAnalysis model."""

    def test_table_name(self):
        """Test HostHealthAnalysis table name."""
        from backend.persistence.models.proplus import HostHealthAnalysis

        assert HostHealthAnalysis.__tablename__ == "host_health_analysis"

    def test_columns_exist(self):
        """Test HostHealthAnalysis has expected columns."""
        from backend.persistence.models.proplus import HostHealthAnalysis

        assert hasattr(HostHealthAnalysis, "id")
        assert hasattr(HostHealthAnalysis, "host_id")
        assert hasattr(HostHealthAnalysis, "analyzed_at")
        assert hasattr(HostHealthAnalysis, "score")
        assert hasattr(HostHealthAnalysis, "grade")
        assert hasattr(HostHealthAnalysis, "issues")
        assert hasattr(HostHealthAnalysis, "recommendations")
        assert hasattr(HostHealthAnalysis, "analysis_version")
        assert hasattr(HostHealthAnalysis, "raw_metrics")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import HostHealthAnalysis

        analysis = HostHealthAnalysis()
        analysis.host_id = uuid.uuid4()
        analysis.score = 85
        analysis.grade = "B"

        repr_str = repr(analysis)

        assert "HostHealthAnalysis" in repr_str
        assert "85" in repr_str
        assert "B" in repr_str


class TestVulnerabilityModel:
    """Tests for Vulnerability model."""

    def test_table_name(self):
        """Test Vulnerability table name."""
        from backend.persistence.models.proplus import Vulnerability

        assert Vulnerability.__tablename__ == "vulnerability"

    def test_columns_exist(self):
        """Test Vulnerability has expected columns."""
        from backend.persistence.models.proplus import Vulnerability

        assert hasattr(Vulnerability, "id")
        assert hasattr(Vulnerability, "cve_id")
        assert hasattr(Vulnerability, "description")
        assert hasattr(Vulnerability, "cvss_score")
        assert hasattr(Vulnerability, "cvss_version")
        assert hasattr(Vulnerability, "severity")
        assert hasattr(Vulnerability, "published_date")
        assert hasattr(Vulnerability, "modified_date")
        assert hasattr(Vulnerability, "references")
        assert hasattr(Vulnerability, "affected_systems")
        assert hasattr(Vulnerability, "created_at")
        assert hasattr(Vulnerability, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import Vulnerability

        vuln = Vulnerability()
        vuln.cve_id = "CVE-2024-1234"
        vuln.severity = "CRITICAL"
        vuln.cvss_score = "9.8"

        repr_str = repr(vuln)

        assert "Vulnerability" in repr_str
        assert "CVE-2024-1234" in repr_str
        assert "CRITICAL" in repr_str
        assert "9.8" in repr_str


class TestPackageVulnerabilityModel:
    """Tests for PackageVulnerability model."""

    def test_table_name(self):
        """Test PackageVulnerability table name."""
        from backend.persistence.models.proplus import PackageVulnerability

        assert PackageVulnerability.__tablename__ == "package_vulnerability"

    def test_columns_exist(self):
        """Test PackageVulnerability has expected columns."""
        from backend.persistence.models.proplus import PackageVulnerability

        assert hasattr(PackageVulnerability, "id")
        assert hasattr(PackageVulnerability, "vulnerability_id")
        assert hasattr(PackageVulnerability, "package_name")
        assert hasattr(PackageVulnerability, "package_manager")
        assert hasattr(PackageVulnerability, "vulnerable_versions")
        assert hasattr(PackageVulnerability, "fixed_version")
        assert hasattr(PackageVulnerability, "advisory_ids")
        assert hasattr(PackageVulnerability, "source")
        assert hasattr(PackageVulnerability, "created_at")
        assert hasattr(PackageVulnerability, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import PackageVulnerability

        pkg_vuln = PackageVulnerability()
        pkg_vuln.package_name = "openssl"
        pkg_vuln.package_manager = "apt"
        pkg_vuln.vulnerability_id = uuid.uuid4()

        repr_str = repr(pkg_vuln)

        assert "PackageVulnerability" in repr_str
        assert "openssl" in repr_str
        assert "apt" in repr_str


class TestHostVulnerabilityScanModel:
    """Tests for HostVulnerabilityScan model."""

    def test_table_name(self):
        """Test HostVulnerabilityScan table name."""
        from backend.persistence.models.proplus import HostVulnerabilityScan

        assert HostVulnerabilityScan.__tablename__ == "host_vulnerability_scan"

    def test_columns_exist(self):
        """Test HostVulnerabilityScan has expected columns."""
        from backend.persistence.models.proplus import HostVulnerabilityScan

        assert hasattr(HostVulnerabilityScan, "id")
        assert hasattr(HostVulnerabilityScan, "host_id")
        assert hasattr(HostVulnerabilityScan, "scanned_at")
        assert hasattr(HostVulnerabilityScan, "total_packages")
        assert hasattr(HostVulnerabilityScan, "vulnerable_packages")
        assert hasattr(HostVulnerabilityScan, "total_vulnerabilities")
        assert hasattr(HostVulnerabilityScan, "critical_count")
        assert hasattr(HostVulnerabilityScan, "high_count")
        assert hasattr(HostVulnerabilityScan, "medium_count")
        assert hasattr(HostVulnerabilityScan, "low_count")
        assert hasattr(HostVulnerabilityScan, "risk_score")
        assert hasattr(HostVulnerabilityScan, "risk_level")
        assert hasattr(HostVulnerabilityScan, "summary")
        assert hasattr(HostVulnerabilityScan, "recommendations")
        assert hasattr(HostVulnerabilityScan, "scanner_version")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import HostVulnerabilityScan

        scan = HostVulnerabilityScan()
        scan.host_id = uuid.uuid4()
        scan.total_vulnerabilities = 15
        scan.critical_count = 3

        repr_str = repr(scan)

        assert "HostVulnerabilityScan" in repr_str
        assert "15" in repr_str
        assert "3" in repr_str


class TestHostVulnerabilityFindingModel:
    """Tests for HostVulnerabilityFinding model."""

    def test_table_name(self):
        """Test HostVulnerabilityFinding table name."""
        from backend.persistence.models.proplus import HostVulnerabilityFinding

        assert HostVulnerabilityFinding.__tablename__ == "host_vulnerability_finding"

    def test_columns_exist(self):
        """Test HostVulnerabilityFinding has expected columns."""
        from backend.persistence.models.proplus import HostVulnerabilityFinding

        assert hasattr(HostVulnerabilityFinding, "id")
        assert hasattr(HostVulnerabilityFinding, "scan_id")
        assert hasattr(HostVulnerabilityFinding, "vulnerability_id")
        assert hasattr(HostVulnerabilityFinding, "package_name")
        assert hasattr(HostVulnerabilityFinding, "installed_version")
        assert hasattr(HostVulnerabilityFinding, "fixed_version")
        assert hasattr(HostVulnerabilityFinding, "severity")
        assert hasattr(HostVulnerabilityFinding, "cvss_score")
        assert hasattr(HostVulnerabilityFinding, "remediation")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import HostVulnerabilityFinding

        finding = HostVulnerabilityFinding()
        finding.package_name = "curl"
        finding.severity = "HIGH"

        repr_str = repr(finding)

        assert "HostVulnerabilityFinding" in repr_str
        assert "curl" in repr_str
        assert "HIGH" in repr_str


class TestVulnerabilityIngestionLogModel:
    """Tests for VulnerabilityIngestionLog model."""

    def test_table_name(self):
        """Test VulnerabilityIngestionLog table name."""
        from backend.persistence.models.proplus import VulnerabilityIngestionLog

        assert VulnerabilityIngestionLog.__tablename__ == "vulnerability_ingestion_log"

    def test_columns_exist(self):
        """Test VulnerabilityIngestionLog has expected columns."""
        from backend.persistence.models.proplus import VulnerabilityIngestionLog

        assert hasattr(VulnerabilityIngestionLog, "id")
        assert hasattr(VulnerabilityIngestionLog, "source")
        assert hasattr(VulnerabilityIngestionLog, "started_at")
        assert hasattr(VulnerabilityIngestionLog, "completed_at")
        assert hasattr(VulnerabilityIngestionLog, "status")
        assert hasattr(VulnerabilityIngestionLog, "vulnerabilities_processed")
        assert hasattr(VulnerabilityIngestionLog, "packages_processed")
        assert hasattr(VulnerabilityIngestionLog, "error_message")
        assert hasattr(VulnerabilityIngestionLog, "details")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import VulnerabilityIngestionLog

        log = VulnerabilityIngestionLog()
        log.source = "nvd"
        log.status = "success"

        repr_str = repr(log)

        assert "VulnerabilityIngestionLog" in repr_str
        assert "nvd" in repr_str
        assert "success" in repr_str


class TestCveRefreshSettingsModel:
    """Tests for CveRefreshSettings model."""

    def test_table_name(self):
        """Test CveRefreshSettings table name."""
        from backend.persistence.models.proplus import CveRefreshSettings

        assert CveRefreshSettings.__tablename__ == "cve_refresh_settings"

    def test_columns_exist(self):
        """Test CveRefreshSettings has expected columns."""
        from backend.persistence.models.proplus import CveRefreshSettings

        assert hasattr(CveRefreshSettings, "id")
        assert hasattr(CveRefreshSettings, "enabled")
        assert hasattr(CveRefreshSettings, "refresh_interval_hours")
        assert hasattr(CveRefreshSettings, "enabled_sources")
        assert hasattr(CveRefreshSettings, "last_refresh_at")
        assert hasattr(CveRefreshSettings, "next_refresh_at")
        assert hasattr(CveRefreshSettings, "nvd_api_key")
        assert hasattr(CveRefreshSettings, "created_at")
        assert hasattr(CveRefreshSettings, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import CveRefreshSettings

        settings = CveRefreshSettings()
        settings.enabled = True
        settings.refresh_interval_hours = 24

        repr_str = repr(settings)

        assert "CveRefreshSettings" in repr_str
        assert "True" in repr_str
        assert "24" in repr_str


class TestComplianceProfileModel:
    """Tests for ComplianceProfile model."""

    def test_table_name(self):
        """Test ComplianceProfile table name."""
        from backend.persistence.models.proplus import ComplianceProfile

        assert ComplianceProfile.__tablename__ == "compliance_profile"

    def test_columns_exist(self):
        """Test ComplianceProfile has expected columns."""
        from backend.persistence.models.proplus import ComplianceProfile

        assert hasattr(ComplianceProfile, "id")
        assert hasattr(ComplianceProfile, "name")
        assert hasattr(ComplianceProfile, "description")
        assert hasattr(ComplianceProfile, "benchmark_type")
        assert hasattr(ComplianceProfile, "enabled")
        assert hasattr(ComplianceProfile, "rules")
        assert hasattr(ComplianceProfile, "created_at")
        assert hasattr(ComplianceProfile, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import ComplianceProfile

        profile = ComplianceProfile()
        profile.name = "CIS Ubuntu 22.04"
        profile.benchmark_type = "CIS"

        repr_str = repr(profile)

        assert "ComplianceProfile" in repr_str
        assert "CIS Ubuntu 22.04" in repr_str
        assert "CIS" in repr_str


class TestProPlusPluginCacheModel:
    """Tests for ProPlusPluginCache model."""

    def test_table_name(self):
        """Test ProPlusPluginCache table name."""
        from backend.persistence.models.proplus import ProPlusPluginCache

        assert ProPlusPluginCache.__tablename__ == "proplus_plugin_cache"

    def test_columns_exist(self):
        """Test ProPlusPluginCache has expected columns."""
        from backend.persistence.models.proplus import ProPlusPluginCache

        assert hasattr(ProPlusPluginCache, "id")
        assert hasattr(ProPlusPluginCache, "module_code")
        assert hasattr(ProPlusPluginCache, "version")
        assert hasattr(ProPlusPluginCache, "file_path")
        assert hasattr(ProPlusPluginCache, "file_hash")
        assert hasattr(ProPlusPluginCache, "downloaded_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import ProPlusPluginCache

        cache = ProPlusPluginCache()
        cache.module_code = "vuln_engine"
        cache.version = "2.0.0"

        repr_str = repr(cache)

        assert "ProPlusPluginCache" in repr_str
        assert "vuln_engine" in repr_str
        assert "2.0.0" in repr_str


class TestNotificationChannelModel:
    """Tests for NotificationChannel model."""

    def test_table_name(self):
        """Test NotificationChannel table name."""
        from backend.persistence.models.proplus import NotificationChannel

        assert NotificationChannel.__tablename__ == "notification_channel"

    def test_columns_exist(self):
        """Test NotificationChannel has expected columns."""
        from backend.persistence.models.proplus import NotificationChannel

        assert hasattr(NotificationChannel, "id")
        assert hasattr(NotificationChannel, "name")
        assert hasattr(NotificationChannel, "channel_type")
        assert hasattr(NotificationChannel, "config")
        assert hasattr(NotificationChannel, "enabled")
        assert hasattr(NotificationChannel, "created_at")
        assert hasattr(NotificationChannel, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import NotificationChannel

        channel = NotificationChannel()
        channel.name = "Admin Email"
        channel.channel_type = "email"
        channel.enabled = True

        repr_str = repr(channel)

        assert "NotificationChannel" in repr_str
        assert "Admin Email" in repr_str
        assert "email" in repr_str
        assert "True" in repr_str


class TestAlertRuleModel:
    """Tests for AlertRule model."""

    def test_table_name(self):
        """Test AlertRule table name."""
        from backend.persistence.models.proplus import AlertRule

        assert AlertRule.__tablename__ == "alert_rule"

    def test_columns_exist(self):
        """Test AlertRule has expected columns."""
        from backend.persistence.models.proplus import AlertRule

        assert hasattr(AlertRule, "id")
        assert hasattr(AlertRule, "name")
        assert hasattr(AlertRule, "description")
        assert hasattr(AlertRule, "condition_type")
        assert hasattr(AlertRule, "condition_params")
        assert hasattr(AlertRule, "severity")
        assert hasattr(AlertRule, "enabled")
        assert hasattr(AlertRule, "cooldown_minutes")
        assert hasattr(AlertRule, "host_filter")
        assert hasattr(AlertRule, "created_at")
        assert hasattr(AlertRule, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import AlertRule

        rule = AlertRule()
        rule.name = "Critical CVE Alert"
        rule.condition_type = "cve_severity"
        rule.severity = "critical"

        repr_str = repr(rule)

        assert "AlertRule" in repr_str
        assert "Critical CVE Alert" in repr_str
        assert "cve_severity" in repr_str
        assert "critical" in repr_str


class TestAlertRuleNotificationChannelModel:
    """Tests for AlertRuleNotificationChannel model."""

    def test_table_name(self):
        """Test AlertRuleNotificationChannel table name."""
        from backend.persistence.models.proplus import AlertRuleNotificationChannel

        assert (
            AlertRuleNotificationChannel.__tablename__
            == "alert_rule_notification_channel"
        )

    def test_columns_exist(self):
        """Test AlertRuleNotificationChannel has expected columns."""
        from backend.persistence.models.proplus import AlertRuleNotificationChannel

        assert hasattr(AlertRuleNotificationChannel, "id")
        assert hasattr(AlertRuleNotificationChannel, "rule_id")
        assert hasattr(AlertRuleNotificationChannel, "channel_id")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import AlertRuleNotificationChannel

        link = AlertRuleNotificationChannel()
        link.rule_id = uuid.uuid4()
        link.channel_id = uuid.uuid4()

        repr_str = repr(link)

        assert "AlertRuleNotificationChannel" in repr_str
        assert str(link.rule_id) in repr_str
        assert str(link.channel_id) in repr_str


class TestAlertModel:
    """Tests for Alert model."""

    def test_table_name(self):
        """Test Alert table name."""
        from backend.persistence.models.proplus import Alert

        assert Alert.__tablename__ == "alert"

    def test_columns_exist(self):
        """Test Alert has expected columns."""
        from backend.persistence.models.proplus import Alert

        assert hasattr(Alert, "id")
        assert hasattr(Alert, "rule_id")
        assert hasattr(Alert, "host_id")
        assert hasattr(Alert, "severity")
        assert hasattr(Alert, "title")
        assert hasattr(Alert, "message")
        assert hasattr(Alert, "details")
        assert hasattr(Alert, "triggered_at")
        assert hasattr(Alert, "acknowledged_at")
        assert hasattr(Alert, "acknowledged_by")
        assert hasattr(Alert, "resolved_at")
        assert hasattr(Alert, "notification_sent")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import Alert

        alert = Alert()
        alert.title = "Host webserver-01 is down"
        alert.severity = "high"
        alert.host_id = uuid.uuid4()

        repr_str = repr(alert)

        assert "Alert" in repr_str
        assert "Host webserver-01 is down" in repr_str
        assert "high" in repr_str


class TestHostComplianceScanModel:
    """Tests for HostComplianceScan model."""

    def test_table_name(self):
        """Test HostComplianceScan table name."""
        from backend.persistence.models.proplus import HostComplianceScan

        assert HostComplianceScan.__tablename__ == "host_compliance_scan"

    def test_columns_exist(self):
        """Test HostComplianceScan has expected columns."""
        from backend.persistence.models.proplus import HostComplianceScan

        assert hasattr(HostComplianceScan, "id")
        assert hasattr(HostComplianceScan, "host_id")
        assert hasattr(HostComplianceScan, "profile_id")
        assert hasattr(HostComplianceScan, "scanned_at")
        assert hasattr(HostComplianceScan, "total_rules")
        assert hasattr(HostComplianceScan, "passed_rules")
        assert hasattr(HostComplianceScan, "failed_rules")
        assert hasattr(HostComplianceScan, "error_rules")
        assert hasattr(HostComplianceScan, "not_applicable_rules")
        assert hasattr(HostComplianceScan, "compliance_score")
        assert hasattr(HostComplianceScan, "compliance_grade")
        assert hasattr(HostComplianceScan, "critical_failures")
        assert hasattr(HostComplianceScan, "high_failures")
        assert hasattr(HostComplianceScan, "medium_failures")
        assert hasattr(HostComplianceScan, "low_failures")
        assert hasattr(HostComplianceScan, "summary")
        assert hasattr(HostComplianceScan, "results")
        assert hasattr(HostComplianceScan, "scanner_version")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.proplus import HostComplianceScan

        scan = HostComplianceScan()
        scan.host_id = uuid.uuid4()
        scan.compliance_score = 78
        scan.compliance_grade = "C"

        repr_str = repr(scan)

        assert "HostComplianceScan" in repr_str
        assert "78" in repr_str
        assert "C" in repr_str


class TestProPlusConstants:
    """Tests for module constants."""

    def test_constants_exist(self):
        """Test module-level constants exist."""
        from backend.persistence.models.proplus import (
            HOST_ID_FK,
            CASCADE_DELETE,
            CASCADE_ALL_DELETE_ORPHAN,
        )

        assert HOST_ID_FK == "host.id"
        assert CASCADE_DELETE == "CASCADE"
        assert CASCADE_ALL_DELETE_ORPHAN == "all, delete-orphan"
