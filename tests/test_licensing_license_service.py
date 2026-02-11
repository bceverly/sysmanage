"""
Tests for backend/licensing/license_service.py module.
Tests Pro+ license service functionality.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock


class TestLicenseServiceProperties:
    """Tests for LicenseService properties."""

    def test_cached_license_initially_none(self):
        """Test that cached_license is None initially."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        assert service.cached_license is None

    def test_is_pro_plus_active_false_initially(self):
        """Test that is_pro_plus_active is False initially."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        assert service.is_pro_plus_active is False

    def test_is_pro_plus_active_true_with_license(self):
        """Test that is_pro_plus_active is True with cached license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = MagicMock()
        assert service.is_pro_plus_active is True

    def test_license_tier_none_without_license(self):
        """Test that license_tier is None without license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        assert service.license_tier is None

    def test_license_tier_returns_value_with_license(self):
        """Test that license_tier returns tier value with license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.tier.value = "professional"
        service._cached_license = mock_license
        assert service.license_tier == "professional"


class TestLicenseServiceConfig:
    """Tests for LicenseService configuration methods."""

    def test_get_license_config(self):
        """Test _get_license_config returns license section."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {"key": "test-key"}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_license_config()

        assert result == {"key": "test-key"}

    def test_get_license_config_empty(self):
        """Test _get_license_config returns empty dict when no license section."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_license_config()

        assert result == {}

    def test_get_phone_home_url(self):
        """Test _get_phone_home_url returns configured URL."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {"phone_home_url": "https://license.example.com"}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_phone_home_url()

        assert result == "https://license.example.com"

    def test_get_phone_home_interval_default(self):
        """Test _get_phone_home_interval returns default."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_phone_home_interval()

        assert result == 24

    def test_get_phone_home_interval_configured(self):
        """Test _get_phone_home_interval returns configured value."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {"phone_home_interval_hours": 12}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_phone_home_interval()

        assert result == 12

    def test_get_modules_path_default(self):
        """Test _get_modules_path returns default."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_modules_path()

        assert result == "/var/lib/sysmanage/modules"

    def test_get_modules_path_configured(self):
        """Test _get_modules_path returns configured value."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {"modules_path": "/custom/path"}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_modules_path()

        assert result == "/custom/path"

    def test_get_module_update_interval_default(self):
        """Test _get_module_update_interval returns default."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = service._get_module_update_interval()

        assert result == 6


class TestLicenseServiceInitialize:
    """Tests for LicenseService.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        """Test initialize returns early if already initialized."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._initialized = True

        await service.initialize()

        # Should return without doing anything

    @pytest.mark.asyncio
    async def test_initialize_no_license_key(self):
        """Test initialize with no license key configured."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            await service.initialize()

        assert service._initialized is True
        assert service._cached_license is None

    @pytest.mark.asyncio
    async def test_initialize_no_public_key(self):
        """Test initialize when public key fetch fails."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_config = {"license": {"key": "test-license-key"}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            with patch(
                "backend.licensing.license_service.get_public_key_pem",
                new=AsyncMock(return_value=None),
            ):
                with patch.object(service, "_log_validation"):
                    await service.initialize()

        assert service._initialized is True
        assert service._cached_license is None


class TestLicenseServiceShutdown:
    """Tests for LicenseService.shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_no_tasks(self):
        """Test shutdown with no background tasks."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        await service.shutdown()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_shutdown_cancels_tasks(self):
        """Test shutdown cancels background tasks."""
        from backend.licensing.license_service import LicenseService
        import asyncio

        service = LicenseService()

        mock_phone_home_task = MagicMock(spec=asyncio.Task)
        mock_module_update_task = MagicMock(spec=asyncio.Task)

        service._phone_home_task = mock_phone_home_task
        service._module_update_task = mock_module_update_task

        with patch("asyncio.gather", new=AsyncMock()):
            await service.shutdown()

        mock_phone_home_task.cancel.assert_called_once()
        mock_module_update_task.cancel.assert_called_once()


class TestLicenseServiceFeatureChecks:
    """Tests for LicenseService feature/module check methods."""

    def test_has_feature_false_without_license(self):
        """Test has_feature returns False without license."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import FeatureCode

        service = LicenseService()
        assert service.has_feature(FeatureCode.HEALTH_ANALYSIS) is False

    def test_has_feature_true_with_feature(self):
        """Test has_feature returns True when feature is included."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import FeatureCode

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.features = ["health", "vuln"]
        service._cached_license = mock_license

        assert service.has_feature(FeatureCode.HEALTH_ANALYSIS) is True

    def test_has_feature_false_without_feature(self):
        """Test has_feature returns False when feature is not included."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import FeatureCode

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.features = ["health"]
        service._cached_license = mock_license

        assert service.has_feature(FeatureCode.VULNERABILITY_SCANNING) is False

    def test_has_module_false_without_license(self):
        """Test has_module returns False without license."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import ModuleCode

        service = LicenseService()
        assert service.has_module(ModuleCode.HEALTH_ENGINE) is False

    def test_has_module_true_with_module(self):
        """Test has_module returns True when module is included."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import ModuleCode

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.modules = ["health_engine", "vuln_engine"]
        service._cached_license = mock_license

        assert service.has_module(ModuleCode.HEALTH_ENGINE) is True

    def test_has_module_false_without_module(self):
        """Test has_module returns False when module is not included."""
        from backend.licensing.license_service import LicenseService
        from backend.licensing.features import ModuleCode

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.modules = ["health_engine"]
        service._cached_license = mock_license

        assert service.has_module(ModuleCode.VULN_ENGINE) is False


class TestLicenseServiceGetInfo:
    """Tests for LicenseService.get_license_info method."""

    def test_get_license_info_none_without_license(self):
        """Test get_license_info returns None without license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        assert service.get_license_info() is None

    def test_get_license_info_returns_dict(self):
        """Test get_license_info returns info dict with license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.license_id = "test-123"
        mock_license.tier.value = "professional"
        mock_license.features = ["health"]
        mock_license.modules = ["health_engine"]
        mock_license.expires_at.isoformat.return_value = "2025-12-31T00:00:00"
        mock_license.customer_name = "Test Customer"
        mock_license.parent_hosts = 5
        mock_license.child_hosts = 50

        service._cached_license = mock_license

        result = service.get_license_info()

        assert result["license_id"] == "test-123"
        assert result["tier"] == "professional"
        assert result["features"] == ["health"]
        assert result["modules"] == ["health_engine"]
        assert result["customer_name"] == "Test Customer"
        assert result["parent_hosts"] == 5
        assert result["child_hosts"] == 50


class TestLicenseServicePhoneHome:
    """Tests for LicenseService phone-home functionality."""

    @pytest.mark.asyncio
    async def test_phone_home_no_license(self):
        """Test _phone_home returns False without license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        result = await service._phone_home()
        assert result is False

    @pytest.mark.asyncio
    async def test_phone_home_no_url(self):
        """Test _phone_home returns True without URL configured."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._cached_license = MagicMock()
        service._license_key = "test-key"
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.license_service.get_config", return_value=mock_config
        ):
            result = await service._phone_home()

        assert result is True


class TestLicenseServiceOfflineGrace:
    """Tests for LicenseService offline grace period."""

    def test_check_offline_grace_no_license(self):
        """Test _check_offline_grace returns False without license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        result = service._check_offline_grace()
        assert result is False

    def test_check_offline_grace_no_record(self):
        """Test _check_offline_grace returns True without record."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.license_id = "test-123"
        service._cached_license = mock_license

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.licensing.license_service.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            with patch("backend.licensing.license_service.db_module.get_engine"):
                result = service._check_offline_grace()

        assert result is True

    def test_check_offline_grace_within_period(self):
        """Test _check_offline_grace returns True within grace period."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.license_id = "test-123"
        service._cached_license = mock_license

        mock_record = MagicMock()
        mock_record.last_phone_home_at = datetime.now() - timedelta(days=1)
        mock_record.offline_days = 7

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_record
        )

        with patch(
            "backend.licensing.license_service.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            with patch("backend.licensing.license_service.db_module.get_engine"):
                result = service._check_offline_grace()

        assert result is True


class TestLicenseServiceDeactivate:
    """Tests for LicenseService._deactivate_license method."""

    def test_deactivate_no_license(self):
        """Test _deactivate_license with no license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._deactivate_license()
        # Should complete without error

    def test_deactivate_clears_cached_license(self):
        """Test _deactivate_license clears cached license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_license = MagicMock()
        mock_license.license_id = "test-123"
        service._cached_license = mock_license
        service._license_key = "test-key"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            MagicMock()
        )

        with patch(
            "backend.licensing.license_service.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            with patch("backend.licensing.license_service.db_module.get_engine"):
                service._deactivate_license()

        assert service._cached_license is None
        assert service._license_key is None


class TestLicenseServiceInstall:
    """Tests for LicenseService.install_license method."""

    @pytest.mark.asyncio
    async def test_install_license_no_public_key(self):
        """Test install_license fails without public key."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()

        with patch(
            "backend.licensing.license_service.get_public_key_pem",
            new=AsyncMock(return_value=None),
        ):
            result = await service.install_license("test-key")

        assert result.valid is False
        assert "public key" in result.error.lower()


class TestLicenseServiceSaveAndLog:
    """Tests for LicenseService database methods."""

    def test_save_license_to_db_no_license(self):
        """Test _save_license_to_db with no cached license."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        service._save_license_to_db()
        # Should return early without error

    def test_log_validation_creates_entry(self):
        """Test _log_validation creates log entry."""
        from backend.licensing.license_service import LicenseService

        service = LicenseService()
        mock_session = MagicMock()

        with patch(
            "backend.licensing.license_service.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            with patch("backend.licensing.license_service.db_module.get_engine"):
                service._log_validation("local", "success")

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestLicenseServiceGlobal:
    """Tests for global license_service instance."""

    def test_license_service_instance_exists(self):
        """Test that global license_service instance exists."""
        from backend.licensing.license_service import license_service

        assert license_service is not None

    def test_license_service_is_license_service(self):
        """Test that global instance is LicenseService type."""
        from backend.licensing.license_service import (
            license_service,
            LicenseService,
        )

        assert isinstance(license_service, LicenseService)


class TestLicenseServiceConstants:
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
