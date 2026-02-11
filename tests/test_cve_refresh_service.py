"""
Tests for backend/vulnerability/cve_refresh_service.py module.
Tests the thin wrapper for CVE refresh operations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.vulnerability.cve_sources import CveRefreshError


class TestGetModule:
    """Tests for _get_module function."""

    @patch("backend.vulnerability.cve_refresh_service.module_loader")
    @patch("backend.vulnerability.cve_refresh_service.license_service")
    def test_get_module_no_license(self, mock_license, mock_loader):
        """Test _get_module returns None when no license."""
        from backend.vulnerability.cve_refresh_service import _get_module

        mock_license.has_module.return_value = False

        result = _get_module()

        assert result is None
        mock_loader.get_module.assert_not_called()

    @patch("backend.vulnerability.cve_refresh_service.module_loader")
    @patch("backend.vulnerability.cve_refresh_service.license_service")
    def test_get_module_with_license(self, mock_license, mock_loader):
        """Test _get_module returns module when licensed."""
        from backend.vulnerability.cve_refresh_service import _get_module

        mock_license.has_module.return_value = True
        mock_module = MagicMock()
        mock_loader.get_module.return_value = mock_module

        result = _get_module()

        assert result == mock_module
        mock_loader.get_module.assert_called_once_with("vuln_engine")


class TestCveRefreshServiceInit:
    """Tests for CveRefreshService initialization."""

    def test_init_sets_module_not_configured(self):
        """Test init sets _module_configured to False."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        service = CveRefreshService()

        assert service._module_configured is False


class TestCveRefreshServiceEnsureModuleConfigured:
    """Tests for CveRefreshService._ensure_module_configured."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_ensure_module_configured_already_done(self, mock_get_module):
        """Test _ensure_module_configured returns early if already done."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        service = CveRefreshService()
        service._module_configured = True

        service._ensure_module_configured()

        mock_get_module.assert_not_called()

    @patch("backend.vulnerability.cve_refresh_service.db_module")
    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_ensure_module_configured_success(self, mock_get_module, mock_db_module):
        """Test _ensure_module_configured configures the module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_vuln_engine = MagicMock()
        mock_cve_service = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine
        mock_db_module.get_engine.return_value = MagicMock()

        service = CveRefreshService()
        service._ensure_module_configured()

        assert service._module_configured is True
        mock_cve_service.configure.assert_called_once()

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_ensure_module_configured_no_module(self, mock_get_module):
        """Test _ensure_module_configured when module not available."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._ensure_module_configured()

        assert service._module_configured is False


class TestCveRefreshServiceGetSettings:
    """Tests for CveRefreshService.get_settings."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_settings_success(self, mock_get_module):
        """Test get_settings delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.get_settings.return_value = {"enabled": True}
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        result = service.get_settings(mock_db)

        assert result == {"enabled": True}

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_settings_no_module(self, mock_get_module):
        """Test get_settings raises error when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError) as exc_info:
            service.get_settings(mock_db)

        assert "vuln_engine module required" in str(exc_info.value)


class TestCveRefreshServiceUpdateSettings:
    """Tests for CveRefreshService.update_settings."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_update_settings_success(self, mock_get_module):
        """Test update_settings delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.update_settings.return_value = {"enabled": False}
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        result = service.update_settings(mock_db, enabled=False)

        assert result == {"enabled": False}

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_update_settings_no_module(self, mock_get_module):
        """Test update_settings raises error when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            service.update_settings(mock_db, enabled=False)


class TestCveRefreshServiceGetAvailableSources:
    """Tests for CveRefreshService.get_available_sources."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_available_sources_with_module(self, mock_get_module):
        """Test get_available_sources delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.get_available_sources.return_value = {"nvd": {}}
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()

        result = service.get_available_sources()

        assert result == {"nvd": {}}

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_available_sources_no_module(self, mock_get_module):
        """Test get_available_sources returns CVE_SOURCES when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService
        from backend.vulnerability.cve_sources import CVE_SOURCES

        mock_get_module.return_value = None

        service = CveRefreshService()

        result = service.get_available_sources()

        assert result == CVE_SOURCES


class TestCveRefreshServiceGetIngestionHistory:
    """Tests for CveRefreshService.get_ingestion_history."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_ingestion_history_success(self, mock_get_module):
        """Test get_ingestion_history delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.get_ingestion_history.return_value = [{"source": "nvd"}]
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        result = service.get_ingestion_history(mock_db, limit=5)

        assert result == [{"source": "nvd"}]

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_ingestion_history_no_module(self, mock_get_module):
        """Test get_ingestion_history raises error when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            service.get_ingestion_history(mock_db)


class TestCveRefreshServiceGetDatabaseStats:
    """Tests for CveRefreshService.get_database_stats."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_database_stats_success(self, mock_get_module):
        """Test get_database_stats delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.get_database_stats.return_value = {"total_cves": 1000}
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        result = service.get_database_stats(mock_db)

        assert result == {"total_cves": 1000}

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_get_database_stats_no_module(self, mock_get_module):
        """Test get_database_stats raises error when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            service.get_database_stats(mock_db)


class TestCveRefreshServiceRefreshFromSource:
    """Tests for CveRefreshService.refresh_from_source."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    @pytest.mark.asyncio
    async def test_refresh_from_source_success(self, mock_get_module):
        """Test refresh_from_source delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.refresh_from_source = AsyncMock(
            return_value={"cves_added": 50}
        )
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        result = await service.refresh_from_source(mock_db, "nvd")

        assert result == {"cves_added": 50}

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    @pytest.mark.asyncio
    async def test_refresh_from_source_no_module(self, mock_get_module):
        """Test refresh_from_source raises error when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            await service.refresh_from_source(mock_db, "nvd")


class TestCveRefreshServiceRefreshAll:
    """Tests for CveRefreshService.refresh_all."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    @pytest.mark.asyncio
    async def test_refresh_all_success(self, mock_get_module):
        """Test refresh_all delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.refresh_all = AsyncMock(return_value={"total_added": 200})
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        result = await service.refresh_all(mock_db)

        assert result == {"total_added": 200}

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    @pytest.mark.asyncio
    async def test_refresh_all_no_module(self, mock_get_module):
        """Test refresh_all raises error when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._module_configured = True
        mock_db = MagicMock()

        with pytest.raises(CveRefreshError):
            await service.refresh_all(mock_db)


class TestCveRefreshServiceScheduler:
    """Tests for CveRefreshService scheduler methods."""

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_start_scheduler_success(self, mock_get_module):
        """Test start_scheduler delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()
        service._module_configured = True

        service.start_scheduler()

        mock_cve_service.start_scheduler.assert_called_once()

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    def test_start_scheduler_no_module(self, mock_get_module):
        """Test start_scheduler logs warning when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()
        service._module_configured = True

        # Should not raise, just log warning
        service.start_scheduler()

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    @pytest.mark.asyncio
    async def test_stop_scheduler_success(self, mock_get_module):
        """Test stop_scheduler delegates to module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_cve_service = MagicMock()
        mock_cve_service.stop_scheduler = AsyncMock()
        mock_vuln_engine = MagicMock()
        mock_vuln_engine._cve_refresh_service = mock_cve_service
        mock_get_module.return_value = mock_vuln_engine

        service = CveRefreshService()

        await service.stop_scheduler()

        mock_cve_service.stop_scheduler.assert_called_once()

    @patch("backend.vulnerability.cve_refresh_service._get_module")
    @pytest.mark.asyncio
    async def test_stop_scheduler_no_module(self, mock_get_module):
        """Test stop_scheduler does nothing when no module."""
        from backend.vulnerability.cve_refresh_service import CveRefreshService

        mock_get_module.return_value = None

        service = CveRefreshService()

        # Should not raise
        await service.stop_scheduler()


class TestCveRefreshServiceSingleton:
    """Tests for the global cve_refresh_service singleton."""

    def test_singleton_exists(self):
        """Test that cve_refresh_service singleton exists."""
        from backend.vulnerability.cve_refresh_service import cve_refresh_service

        assert cve_refresh_service is not None

    def test_singleton_type(self):
        """Test that singleton is correct type."""
        from backend.vulnerability.cve_refresh_service import (
            CveRefreshService,
            cve_refresh_service,
        )

        assert isinstance(cve_refresh_service, CveRefreshService)
