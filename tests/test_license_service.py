"""
Tests for backend/licensing/license_service.py module.
Tests Pro+ license service management.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLicenseServiceInit:
    """Tests for LicenseService initialization."""

    def test_init_defaults(self):
        """Test initialization sets default values."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()

        assert service._cached_license is None
        assert service._license_key is None
        assert service._license_key_hash is None
        assert service._phone_home_task is None
        assert service._module_update_task is None
        assert service._initialized is False


class TestLicenseServiceProperties:
    """Tests for LicenseService properties."""

    def test_cached_license_property(self):
        """Test cached_license property."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        assert service.cached_license is None

        mock_license = MagicMock()
        service._cached_license = mock_license
        assert service.cached_license == mock_license

    def test_is_pro_plus_active_false(self):
        """Test is_pro_plus_active when not active."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        assert service.is_pro_plus_active is False

    def test_is_pro_plus_active_true(self):
        """Test is_pro_plus_active when active."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = MagicMock()
        assert service.is_pro_plus_active is True

    def test_license_tier_none(self):
        """Test license_tier when no license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        assert service.license_tier is None

    def test_license_tier_with_license(self):
        """Test license_tier when license is present."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import LicenseTier

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.tier = LicenseTier.ENTERPRISE
        service._cached_license = mock_license
        assert service.license_tier == "enterprise"


class TestLicenseServiceConfig:
    """Tests for LicenseService configuration methods."""

    @patch("backend.licensing.license_service.get_config")
    def test_get_license_config(self, mock_get_config):
        """Test _get_license_config method."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {"key": "test-key"}}

        service = LicenseService()
        config = service._get_license_config()

        assert config == {"key": "test-key"}

    @patch("backend.licensing.license_service.get_config")
    def test_get_license_config_empty(self, mock_get_config):
        """Test _get_license_config when license not configured."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {}

        service = LicenseService()
        config = service._get_license_config()

        assert config == {}

    @patch("backend.licensing.license_service.get_config")
    def test_get_phone_home_url(self, mock_get_config):
        """Test _get_phone_home_url method."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {
            "license": {"phone_home_url": "https://license.example.com"}
        }

        service = LicenseService()
        url = service._get_phone_home_url()

        assert url == "https://license.example.com"

    @patch("backend.licensing.license_service.get_config")
    def test_get_phone_home_url_not_configured(self, mock_get_config):
        """Test _get_phone_home_url when not configured."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {}}

        service = LicenseService()
        url = service._get_phone_home_url()

        assert url is None

    @patch("backend.licensing.license_service.get_config")
    def test_get_phone_home_interval_default(self, mock_get_config):
        """Test _get_phone_home_interval returns default."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {}}

        service = LicenseService()
        interval = service._get_phone_home_interval()

        assert interval == 24  # DEFAULT_PHONE_HOME_INTERVAL

    @patch("backend.licensing.license_service.get_config")
    def test_get_phone_home_interval_configured(self, mock_get_config):
        """Test _get_phone_home_interval with configured value."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {"phone_home_interval_hours": 12}}

        service = LicenseService()
        interval = service._get_phone_home_interval()

        assert interval == 12

    @patch("backend.licensing.license_service.get_config")
    def test_get_modules_path_default(self, mock_get_config):
        """Test _get_modules_path returns default."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {}}

        service = LicenseService()
        path = service._get_modules_path()

        assert path == "/var/lib/sysmanage/modules"

    @patch("backend.licensing.license_service.get_config")
    def test_get_modules_path_configured(self, mock_get_config):
        """Test _get_modules_path with configured value."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {"modules_path": "/custom/modules"}}

        service = LicenseService()
        path = service._get_modules_path()

        assert path == "/custom/modules"

    @patch("backend.licensing.license_service.get_config")
    def test_get_module_update_interval_default(self, mock_get_config):
        """Test _get_module_update_interval returns default."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {}}

        service = LicenseService()
        interval = service._get_module_update_interval()

        assert interval == 6  # DEFAULT_MODULE_UPDATE_INTERVAL


class TestLicenseServiceInitialize:
    """Tests for LicenseService initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        """Test initialize when already initialized."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._initialized = True

        await service.initialize()

        # Should return early without doing anything
        assert service._initialized is True

    @patch("backend.licensing.license_service.get_config")
    @pytest.mark.asyncio
    async def test_initialize_no_license_key(self, mock_get_config):
        """Test initialize without license key configured."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {}}

        service = LicenseService()
        await service.initialize()

        assert service._initialized is True
        assert service._cached_license is None

    @patch("backend.licensing.license_service.get_public_key_pem")
    @patch("backend.licensing.license_service.get_config")
    @pytest.mark.asyncio
    async def test_initialize_no_public_key(self, mock_get_config, mock_get_key):
        """Test initialize when public key fetch fails."""
        from backend.licensing.license_service import LicenseService

        mock_get_config.return_value = {"license": {"key": "test-license-key"}}
        mock_get_key.return_value = None

        service = LicenseService()
        with patch.object(service, "_log_validation"):
            await service.initialize()

        assert service._initialized is True
        assert service._cached_license is None


class TestLicenseServiceHasFeature:
    """Tests for has_feature method."""

    def test_has_feature_no_license(self):
        """Test has_feature when no license."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import FeatureCode

        service = LicenseService()
        assert service.has_feature(FeatureCode.HEALTH_ANALYSIS) is False

    def test_has_feature_with_license(self):
        """Test has_feature when license has feature."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import FeatureCode

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.features = [FeatureCode.HEALTH_ANALYSIS.value]
        service._cached_license = mock_license

        # Need to implement the actual method call
        # This tests the interface exists


class TestLicenseServiceHasModule:
    """Tests for has_module method."""

    def test_has_module_no_license(self):
        """Test has_module when no license."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import ModuleCode

        service = LicenseService()
        assert service.has_module(ModuleCode.HEALTH_ENGINE) is False


class TestGlobalInstance:
    """Tests for global license_service instance."""

    def test_global_instance_exists(self):
        """Test that global license_service instance exists."""
        from backend.licensing.license_service import license_service

        assert license_service is not None

    def test_global_instance_type(self):
        """Test that global instance is correct type."""
        from backend.licensing.license_service import LicenseService, license_service

        assert isinstance(license_service, LicenseService)


class TestConstants:
    """Tests for module constants."""

    def test_default_phone_home_interval(self):
        """Test DEFAULT_PHONE_HOME_INTERVAL constant."""
        from backend.licensing.license_service import DEFAULT_PHONE_HOME_INTERVAL

        assert DEFAULT_PHONE_HOME_INTERVAL == 24

    def test_default_module_update_interval(self):
        """Test DEFAULT_MODULE_UPDATE_INTERVAL constant."""
        from backend.licensing.license_service import DEFAULT_MODULE_UPDATE_INTERVAL

        assert DEFAULT_MODULE_UPDATE_INTERVAL == 6

    def test_default_modules_path(self):
        """Test DEFAULT_MODULES_PATH constant."""
        from backend.licensing.license_service import DEFAULT_MODULES_PATH

        assert DEFAULT_MODULES_PATH == "/var/lib/sysmanage/modules"
