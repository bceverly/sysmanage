"""
Tests for backend/licensing/features.py module.
Tests FeatureCode, ModuleCode, LicenseTier enums and tier mappings.
"""

import pytest


class TestFeatureCode:
    """Tests for FeatureCode enum."""

    def test_feature_code_values(self):
        """Test that all FeatureCode values are strings."""
        from backend.licensing.features import FeatureCode

        for feature in FeatureCode:
            assert isinstance(feature.value, str)
            assert len(feature.value) > 0

    def test_health_analysis_value(self):
        """Test HEALTH_ANALYSIS feature code value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.HEALTH_ANALYSIS.value == "health"

    def test_health_history_value(self):
        """Test HEALTH_HISTORY feature code value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.HEALTH_HISTORY.value == "health_history"

    def test_health_alerts_value(self):
        """Test HEALTH_ALERTS feature code value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.HEALTH_ALERTS.value == "alerts"

    def test_vulnerability_scanning_value(self):
        """Test VULNERABILITY_SCANNING feature code value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.VULNERABILITY_SCANNING.value == "vuln"

    def test_compliance_reports_value(self):
        """Test COMPLIANCE_REPORTS feature code value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.COMPLIANCE_REPORTS.value == "compliance"

    def test_api_extended_value(self):
        """Test API_EXTENDED feature code value."""
        from backend.licensing.features import FeatureCode

        assert FeatureCode.API_EXTENDED.value == "api"

    def test_from_string_valid(self):
        """Test from_string with valid feature code."""
        from backend.licensing.features import FeatureCode

        result = FeatureCode.from_string("health")
        assert result == FeatureCode.HEALTH_ANALYSIS

    def test_from_string_vuln(self):
        """Test from_string with vuln feature code."""
        from backend.licensing.features import FeatureCode

        result = FeatureCode.from_string("vuln")
        assert result == FeatureCode.VULNERABILITY_SCANNING

    def test_from_string_invalid(self):
        """Test from_string with invalid feature code raises ValueError."""
        from backend.licensing.features import FeatureCode

        with pytest.raises(ValueError) as exc_info:
            FeatureCode.from_string("invalid_feature")
        assert "Unknown feature code" in str(exc_info.value)

    def test_from_string_empty(self):
        """Test from_string with empty string raises ValueError."""
        from backend.licensing.features import FeatureCode

        with pytest.raises(ValueError):
            FeatureCode.from_string("")

    def test_feature_code_is_str_enum(self):
        """Test that FeatureCode is a string enum."""
        from backend.licensing.features import FeatureCode

        assert isinstance(FeatureCode.HEALTH_ANALYSIS, str)
        assert FeatureCode.HEALTH_ANALYSIS == "health"


class TestModuleCode:
    """Tests for ModuleCode enum."""

    def test_module_code_values(self):
        """Test that all ModuleCode values are strings."""
        from backend.licensing.features import ModuleCode

        for module in ModuleCode:
            assert isinstance(module.value, str)
            assert len(module.value) > 0

    def test_health_engine_value(self):
        """Test HEALTH_ENGINE module code value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.HEALTH_ENGINE.value == "health_engine"

    def test_vuln_engine_value(self):
        """Test VULN_ENGINE module code value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.VULN_ENGINE.value == "vuln_engine"

    def test_compliance_engine_value(self):
        """Test COMPLIANCE_ENGINE module code value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.COMPLIANCE_ENGINE.value == "compliance_engine"

    def test_alerting_engine_value(self):
        """Test ALERTING_ENGINE module code value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.ALERTING_ENGINE.value == "alerting_engine"

    def test_proplus_core_value(self):
        """Test PROPLUS_CORE module code value."""
        from backend.licensing.features import ModuleCode

        assert ModuleCode.PROPLUS_CORE.value == "proplus_core"

    def test_from_string_valid(self):
        """Test from_string with valid module code."""
        from backend.licensing.features import ModuleCode

        result = ModuleCode.from_string("health_engine")
        assert result == ModuleCode.HEALTH_ENGINE

    def test_from_string_vuln_engine(self):
        """Test from_string with vuln_engine module code."""
        from backend.licensing.features import ModuleCode

        result = ModuleCode.from_string("vuln_engine")
        assert result == ModuleCode.VULN_ENGINE

    def test_from_string_invalid(self):
        """Test from_string with invalid module code raises ValueError."""
        from backend.licensing.features import ModuleCode

        with pytest.raises(ValueError) as exc_info:
            ModuleCode.from_string("invalid_module")
        assert "Unknown module code" in str(exc_info.value)

    def test_from_string_empty(self):
        """Test from_string with empty string raises ValueError."""
        from backend.licensing.features import ModuleCode

        with pytest.raises(ValueError):
            ModuleCode.from_string("")

    def test_module_code_is_str_enum(self):
        """Test that ModuleCode is a string enum."""
        from backend.licensing.features import ModuleCode

        assert isinstance(ModuleCode.HEALTH_ENGINE, str)
        assert ModuleCode.HEALTH_ENGINE == "health_engine"


class TestLicenseTier:
    """Tests for LicenseTier enum."""

    def test_community_value(self):
        """Test COMMUNITY tier value."""
        from backend.licensing.features import LicenseTier

        assert LicenseTier.COMMUNITY.value == "community"

    def test_professional_value(self):
        """Test PROFESSIONAL tier value."""
        from backend.licensing.features import LicenseTier

        assert LicenseTier.PROFESSIONAL.value == "professional"

    def test_enterprise_value(self):
        """Test ENTERPRISE tier value."""
        from backend.licensing.features import LicenseTier

        assert LicenseTier.ENTERPRISE.value == "enterprise"

    def test_license_tier_is_str_enum(self):
        """Test that LicenseTier is a string enum."""
        from backend.licensing.features import LicenseTier

        assert isinstance(LicenseTier.COMMUNITY, str)
        assert LicenseTier.COMMUNITY == "community"


class TestTierFeatures:
    """Tests for TIER_FEATURES mapping."""

    def test_community_has_no_features(self):
        """Test that community tier has no features."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier

        assert TIER_FEATURES[LicenseTier.COMMUNITY] == set()

    def test_professional_has_features(self):
        """Test that professional tier has features."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier, FeatureCode

        prof_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        assert FeatureCode.HEALTH_ANALYSIS in prof_features
        assert FeatureCode.HEALTH_HISTORY in prof_features
        assert FeatureCode.VULNERABILITY_SCANNING in prof_features

    def test_enterprise_has_more_features(self):
        """Test that enterprise tier has more features than professional."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier

        prof_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        ent_features = TIER_FEATURES[LicenseTier.ENTERPRISE]
        assert len(ent_features) > len(prof_features)

    def test_enterprise_has_all_professional_features(self):
        """Test that enterprise tier includes professional features."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier, FeatureCode

        ent_features = TIER_FEATURES[LicenseTier.ENTERPRISE]
        assert FeatureCode.HEALTH_ANALYSIS in ent_features
        assert FeatureCode.HEALTH_HISTORY in ent_features
        assert FeatureCode.VULNERABILITY_SCANNING in ent_features

    def test_enterprise_has_exclusive_features(self):
        """Test that enterprise has features not in professional."""
        from backend.licensing.features import TIER_FEATURES, LicenseTier, FeatureCode

        prof_features = TIER_FEATURES[LicenseTier.PROFESSIONAL]
        ent_features = TIER_FEATURES[LicenseTier.ENTERPRISE]
        # Check for enterprise-only features
        assert FeatureCode.HEALTH_ALERTS in ent_features
        assert FeatureCode.HEALTH_ALERTS not in prof_features


class TestTierModules:
    """Tests for TIER_MODULES mapping."""

    def test_community_has_no_modules(self):
        """Test that community tier has no modules."""
        from backend.licensing.features import TIER_MODULES, LicenseTier

        assert TIER_MODULES[LicenseTier.COMMUNITY] == set()

    def test_professional_has_modules(self):
        """Test that professional tier has modules."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        prof_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        assert ModuleCode.HEALTH_ENGINE in prof_modules
        assert ModuleCode.VULN_ENGINE in prof_modules
        assert ModuleCode.COMPLIANCE_ENGINE in prof_modules
        assert ModuleCode.ALERTING_ENGINE in prof_modules

    def test_enterprise_has_more_modules(self):
        """Test that enterprise tier has more modules than professional."""
        from backend.licensing.features import TIER_MODULES, LicenseTier

        prof_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]
        assert len(ent_modules) > len(prof_modules)

    def test_enterprise_has_all_professional_modules(self):
        """Test that enterprise tier includes professional modules."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]
        assert ModuleCode.HEALTH_ENGINE in ent_modules
        assert ModuleCode.VULN_ENGINE in ent_modules
        assert ModuleCode.COMPLIANCE_ENGINE in ent_modules

    def test_enterprise_has_exclusive_modules(self):
        """Test that enterprise has modules not in professional."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        prof_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]
        # Check for enterprise-only modules
        assert ModuleCode.PERFORMANCE_ANALYZER in ent_modules
        assert ModuleCode.PERFORMANCE_ANALYZER not in prof_modules
        assert ModuleCode.ANOMALY_DETECTOR in ent_modules
        assert ModuleCode.ANOMALY_DETECTOR not in prof_modules

    def test_proplus_core_in_professional(self):
        """Test that PROPLUS_CORE is available in professional tier."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        prof_modules = TIER_MODULES[LicenseTier.PROFESSIONAL]
        assert ModuleCode.PROPLUS_CORE in prof_modules

    def test_proplus_core_in_enterprise(self):
        """Test that PROPLUS_CORE is available in enterprise tier."""
        from backend.licensing.features import TIER_MODULES, LicenseTier, ModuleCode

        ent_modules = TIER_MODULES[LicenseTier.ENTERPRISE]
        assert ModuleCode.PROPLUS_CORE in ent_modules
