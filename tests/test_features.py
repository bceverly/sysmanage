"""
Tests for backend/licensing/features.py module.
Tests feature codes, module codes, license tiers, and tier mappings.
"""

import pytest


class TestFeatureCode:
    """Tests for FeatureCode enum."""

    def test_health_analysis_value(self):
        """Test HEALTH_ANALYSIS has correct value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.HEALTH_ANALYSIS.value == "health"

    def test_health_history_value(self):
        """Test HEALTH_HISTORY has correct value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.HEALTH_HISTORY.value == "health_history"

    def test_health_alerts_value(self):
        """Test HEALTH_ALERTS has correct value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.HEALTH_ALERTS.value == "alerts"

    def test_health_reports_value(self):
        """Test HEALTH_REPORTS has correct value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.HEALTH_REPORTS.value == "reports"

    def test_vulnerability_scanning_value(self):
        """Test VULNERABILITY_SCANNING has correct value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.VULNERABILITY_SCANNING.value == "vuln"

    def test_compliance_reports_value(self):
        """Test COMPLIANCE_REPORTS has correct value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.COMPLIANCE_REPORTS.value == "compliance"

    def test_api_extended_value(self):
        """Test API_EXTENDED has correct value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.API_EXTENDED.value == "api"

    def test_from_string_valid(self):
        """Test from_string with valid value."""
        from backend.licensing.features import FeatureCode

        result = FeatureCode.from_string("health")
        assert result == FeatureCode.HEALTH_ANALYSIS

    def test_from_string_vuln(self):
        """Test from_string with vuln value."""
        from backend.licensing.features import FeatureCode

        result = FeatureCode.from_string("vuln")
        assert result == FeatureCode.VULNERABILITY_SCANNING

    def test_from_string_invalid(self):
        """Test from_string raises error for invalid value."""
        from backend.licensing.features import FeatureCode

        with pytest.raises(ValueError) as exc_info:
            FeatureCode.from_string("invalid_feature")

        assert "Unknown feature code: invalid_feature" in str(exc_info.value)

    def test_from_string_empty(self):
        """Test from_string raises error for empty string."""
        from backend.licensing.features import FeatureCode

        with pytest.raises(ValueError) as exc_info:
            FeatureCode.from_string("")

        assert "Unknown feature code:" in str(exc_info.value)

    def test_feature_code_is_str_enum(self):
        """Test FeatureCode is a string enum."""
        from backend.licensing.features import FeatureCode

        assert isinstance(FeatureCode.HEALTH_ANALYSIS, str)
        assert FeatureCode.HEALTH_ANALYSIS == "health"

    def test_all_feature_codes_exist(self):
        """Test all expected feature codes exist."""
        from backend.licensing.features import FeatureCode

        expected_features = [
            "HEALTH_ANALYSIS",
            "HEALTH_HISTORY",
            "HEALTH_ALERTS",
            "HEALTH_REPORTS",
            "ADVANCED_MONITORING",
            "PERFORMANCE_ANALYTICS",
            "PREDICTIVE_MAINTENANCE",
            "VULNERABILITY_SCANNING",
            "COMPLIANCE_REPORTS",
            "SECURITY_HARDENING",
            "AUTO_REMEDIATION",
            "WORKFLOW_AUTOMATION",
            "SCHEDULED_TASKS",
            "SIEM_INTEGRATION",
            "API_EXTENDED",
            "WEBHOOK_ADVANCED",
            "CUSTOM_REPORTS",
            "EXECUTIVE_DASHBOARD",
            "EXPORT_PDF",
        ]

        for feature_name in expected_features:
            assert hasattr(FeatureCode, feature_name)


class TestModuleCode:
    """Tests for ModuleCode enum."""

    def test_health_engine_value(self):
        """Test HEALTH_ENGINE has correct value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.HEALTH_ENGINE.value == "health_engine"

    def test_security_scanner_value(self):
        """Test SECURITY_SCANNER has correct value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.SECURITY_SCANNER.value == "security_scanner"

    def test_vuln_engine_value(self):
        """Test VULN_ENGINE has correct value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.VULN_ENGINE.value == "vuln_engine"

    def test_compliance_engine_value(self):
        """Test COMPLIANCE_ENGINE has correct value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.COMPLIANCE_ENGINE.value == "compliance_engine"

    def test_alerting_engine_value(self):
        """Test ALERTING_ENGINE has correct value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.ALERTING_ENGINE.value == "alerting_engine"

    def test_proplus_core_value(self):
        """Test PROPLUS_CORE has correct value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.PROPLUS_CORE.value == "proplus_core"

    def test_from_string_valid(self):
        """Test from_string with valid value."""
        from backend.licensing.features import ModuleCode

        result = ModuleCode.from_string("health_engine")
        assert result == ModuleCode.HEALTH_ENGINE

    def test_from_string_vuln_engine(self):
        """Test from_string with vuln_engine value."""
        from backend.licensing.features import ModuleCode

        result = ModuleCode.from_string("vuln_engine")
        assert result == ModuleCode.VULN_ENGINE

    def test_from_string_invalid(self):
        """Test from_string raises error for invalid value."""
        from backend.licensing.features import ModuleCode

        with pytest.raises(ValueError) as exc_info:
            ModuleCode.from_string("invalid_module")

        assert "Unknown module code: invalid_module" in str(exc_info.value)

    def test_from_string_empty(self):
        """Test from_string raises error for empty string."""
        from backend.licensing.features import ModuleCode

        with pytest.raises(ValueError) as exc_info:
            ModuleCode.from_string("")

        assert "Unknown module code:" in str(exc_info.value)

    def test_module_code_is_str_enum(self):
        """Test ModuleCode is a string enum."""
        from backend.licensing.features import ModuleCode

        assert isinstance(ModuleCode.HEALTH_ENGINE, str)
        assert ModuleCode.HEALTH_ENGINE == "health_engine"

    def test_all_module_codes_exist(self):
        """Test all expected module codes exist."""
        from backend.licensing.features import ModuleCode

        expected_modules = [
            "HEALTH_ENGINE",
            "SECURITY_SCANNER",
            "VULN_ENGINE",
            "COMPLIANCE_ENGINE",
            "PERFORMANCE_ANALYZER",
            "ANOMALY_DETECTOR",
            "PREDICTION_ENGINE",
            "PROPLUS_CORE",
            "ALERTING_ENGINE",
            "REPORTING_ENGINE",
            "AUDIT_ENGINE",
            "SECRETS_ENGINE",
            "CONTAINER_ENGINE",
            "LOG_ANALYZER",
            "METRICS_AGGREGATOR",
        ]

        for module_name in expected_modules:
            assert hasattr(ModuleCode, module_name)


class TestLicenseTier:
    """Tests for LicenseTier enum."""

    def test_community_value(self):
        """Test COMMUNITY has correct value."""
        from backend.licensing.features import LicenseTier

        assert LicenseTier.COMMUNITY.value == "community"

    def test_professional_value(self):
        """Test PROFESSIONAL has correct value."""
        from backend.licensing.features import LicenseTier

        assert LicenseTier.PROFESSIONAL.value == "professional"

    def test_enterprise_value(self):
        """Test ENTERPRISE has correct value."""
        from backend.licensing.features import LicenseTier

        assert LicenseTier.ENTERPRISE.value == "enterprise"

    def test_license_tier_is_str_enum(self):
        """Test LicenseTier is a string enum."""
        from backend.licensing.features import LicenseTier

        assert isinstance(LicenseTier.COMMUNITY, str)
        assert LicenseTier.COMMUNITY == "community"


class TestTierFeatures:
    """Tests for TIER_FEATURES mapping."""

    def test_community_has_no_features(self):
        """Test community tier has no features."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier

        assert TIER_FEATURES[LicenseTier.COMMUNITY] == set()
        assert len(TIER_FEATURES[LicenseTier.COMMUNITY]) == 0

    def test_professional_has_features(self):
        """Test professional tier has features."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier, FeatureCode

        pro_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        assert len(pro_features) > 0
        assert FeatureCode.HEALTH_ANALYSIS in pro_features
        assert FeatureCode.VULNERABILITY_SCANNING in pro_features

    def test_professional_features_specific(self):
        """Test professional tier has specific features."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier, FeatureCode

        pro_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        expected = {
            FeatureCode.HEALTH_ANALYSIS,
            FeatureCode.HEALTH_HISTORY,
            FeatureCode.VULNERABILITY_SCANNING,
            FeatureCode.ADVANCED_MONITORING,
            FeatureCode.CUSTOM_REPORTS,
        }
        assert pro_features == expected

    def test_enterprise_has_more_features(self):
        """Test enterprise tier has more features than professional."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier

        pro_count = len(TIER_FEATURES[LicenseTier.PROFESSIONAL])
        ent_count = len(TIER_FEATURES[LicenseTier.ENTERPRISE])
        assert ent_count > pro_count

    def test_enterprise_includes_professional_features(self):
        """Test enterprise tier includes all professional features."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier

        pro_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        ent_features = TIER_FEATURES[LicenseTier.ENTERPRISE]

        for feature in pro_features:
            assert feature in ent_features

    def test_enterprise_has_exclusive_features(self):
        """Test enterprise has features not in professional."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier, FeatureCode

        ent_features = TIER_FEATURES[LicenseTier.ENTERPRISE]
        assert FeatureCode.COMPLIANCE_REPORTS in ent_features
        assert FeatureCode.EXECUTIVE_DASHBOARD in ent_features
        assert FeatureCode.SIEM_INTEGRATION in ent_features


class TestTierModules:
    """Tests for TIER_MODULES mapping."""

    def test_community_has_no_modules(self):
        """Test community tier has no modules."""
        from backend.licensing.features import TIER_MODULES, LicenseTier

        assert TIER_MODULES[LicenseTier.COMMUNITY] == set()
        assert len(TIER_MODULES[LicenseTier.COMMUNITY]) == 0

    def test_professional_has_modules(self):
        """Test professional tier has modules."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        pro_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        assert len(pro_modules) > 0
        assert ModuleCode.HEALTH_ENGINE in pro_modules
        assert ModuleCode.VULN_ENGINE in pro_modules

    def test_professional_modules_specific(self):
        """Test professional tier has specific modules."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        pro_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        expected = {
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
        }
        assert pro_modules == expected

    def test_enterprise_has_more_modules(self):
        """Test enterprise tier has more modules than professional."""
        from backend.licensing.features import TIER_MODULES, LicenseTier

        pro_count = len(TIER_MODULES[LicenseTier.PROFESSIONAL])
        ent_count = len(TIER_MODULES[LicenseTier.ENTERPRISE])
        assert ent_count > pro_count

    def test_enterprise_includes_professional_modules(self):
        """Test enterprise tier includes all professional modules."""
        from backend.licensing.features import TIER_MODULES, LicenseTier

        pro_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]

        for module in pro_modules:
            assert module in ent_modules

    def test_enterprise_has_exclusive_modules(self):
        """Test enterprise has modules not in professional."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]
        assert ModuleCode.PERFORMANCE_ANALYZER in ent_modules
        assert ModuleCode.ANOMALY_DETECTOR in ent_modules
        assert ModuleCode.PREDICTION_ENGINE in ent_modules
        assert ModuleCode.LOG_ANALYZER in ent_modules
        assert ModuleCode.METRICS_AGGREGATOR in ent_modules

    def test_all_tiers_in_mapping(self):
        """Test all license tiers are in TIER_MODULES."""
        from backend.licensing.features import TIER_MODULES, LicenseTier

        for tier in LicenseTier:
            assert tier in TIER_MODULES
