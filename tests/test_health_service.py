"""
Tests for backend/health/health_service.py module.
Tests the HealthService wrapper for Pro+ health analysis.
"""

import backend.health.health_service as health_service_module
from unittest.mock import MagicMock, patch

import pytest

from backend.health.health_service import HealthAnalysisError, HealthService


class TestHealthAnalysisError:
    """Tests for HealthAnalysisError exception."""

    def test_error_message(self):
        """Test that error message is preserved."""
        error = HealthAnalysisError("Test error message")
        assert str(error) == "Test error message"

    def test_error_inheritance(self):
        """Test that it inherits from Exception."""
        error = HealthAnalysisError("Test")
        assert isinstance(error, Exception)


class TestHealthServiceInit:
    """Tests for HealthService initialization."""

    def test_health_service_instance(self):
        """Test that health_service global instance exists."""
        from backend.health.health_service import health_service

        assert health_service is not None
        assert isinstance(health_service, HealthService)


class TestHealthServiceGetModule:
    """Tests for HealthService._get_module method."""

    def test_get_module_no_license(self):
        """Test _get_module when license is not available."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(health_service_module, "module_loader"):
            mock_license_service.has_module.return_value = False

            service = HealthService()
            with pytest.raises(HealthAnalysisError) as exc_info:
                service._get_module()

            assert "Pro+ license" in str(exc_info.value)

    def test_get_module_not_loaded(self):
        """Test _get_module when module is licensed but not loaded."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader:
            mock_license_service.has_module.return_value = True
            mock_module_loader.get_module.return_value = None

            service = HealthService()
            with pytest.raises(HealthAnalysisError) as exc_info:
                service._get_module()

            assert "not loaded" in str(exc_info.value)

    def test_get_module_success(self):
        """Test _get_module when module is available."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader:
            mock_license_service.has_module.return_value = True
            mock_health_engine = MagicMock()
            mock_module_loader.get_module.return_value = mock_health_engine

            service = HealthService()
            result = service._get_module()

            assert result == mock_health_engine


class TestHealthServiceGetDbSession:
    """Tests for HealthService._get_db_session method."""

    def test_get_db_session(self):
        """Test _get_db_session returns a session."""
        with patch.object(health_service_module, "db_module") as mock_db_module:
            mock_engine = MagicMock()
            mock_db_module.get_engine.return_value = mock_engine

            service = HealthService()
            session = service._get_db_session()

            # Should return a session object
            assert session is not None


class TestHealthServiceAnalyzeHost:
    """Tests for HealthService.analyze_host method."""

    def test_analyze_host_success(self):
        """Test analyze_host with successful analysis."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader, patch.object(
            health_service_module, "db_module"
        ) as mock_db_module:
            mock_license_service.has_module.return_value = True

            mock_health_service = MagicMock()
            mock_health_service.analyze_host.return_value = {
                "host_id": "test-host",
                "health_score": 85,
            }
            mock_health_engine = MagicMock()
            mock_health_engine._health_service = mock_health_service
            mock_module_loader.get_module.return_value = mock_health_engine

            mock_engine = MagicMock()
            mock_db_module.get_engine.return_value = mock_engine

            service = HealthService()
            result = service.analyze_host("test-host-id")

            assert result["host_id"] == "test-host"
            assert result["health_score"] == 85

    def test_analyze_host_no_license(self):
        """Test analyze_host when no license available."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service:
            mock_license_service.has_module.return_value = False

            service = HealthService()
            with pytest.raises(HealthAnalysisError):
                service.analyze_host("test-host-id")


class TestHealthServiceGetLatestAnalysis:
    """Tests for HealthService.get_latest_analysis method."""

    def test_get_latest_analysis_success(self):
        """Test get_latest_analysis with existing analysis."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader, patch.object(
            health_service_module, "db_module"
        ) as mock_db_module:
            mock_license_service.has_module.return_value = True

            mock_health_service = MagicMock()
            mock_health_service.get_latest_analysis.return_value = {
                "host_id": "test-host",
                "timestamp": "2024-01-01T00:00:00Z",
            }
            mock_health_engine = MagicMock()
            mock_health_engine._health_service = mock_health_service
            mock_module_loader.get_module.return_value = mock_health_engine

            mock_engine = MagicMock()
            mock_db_module.get_engine.return_value = mock_engine

            service = HealthService()
            result = service.get_latest_analysis("test-host-id")

            assert result["host_id"] == "test-host"

    def test_get_latest_analysis_none(self):
        """Test get_latest_analysis when no analysis exists."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader, patch.object(
            health_service_module, "db_module"
        ) as mock_db_module:
            mock_license_service.has_module.return_value = True

            mock_health_service = MagicMock()
            mock_health_service.get_latest_analysis.return_value = None
            mock_health_engine = MagicMock()
            mock_health_engine._health_service = mock_health_service
            mock_module_loader.get_module.return_value = mock_health_engine

            mock_engine = MagicMock()
            mock_db_module.get_engine.return_value = mock_engine

            service = HealthService()
            result = service.get_latest_analysis("test-host-id")

            assert result is None


class TestHealthServiceGetAnalysisHistory:
    """Tests for HealthService.get_analysis_history method."""

    def test_get_analysis_history_success(self):
        """Test get_analysis_history with existing history."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader, patch.object(
            health_service_module, "db_module"
        ) as mock_db_module:
            mock_license_service.has_module.return_value = True

            mock_health_service = MagicMock()
            mock_health_service.get_analysis_history.return_value = [
                {"timestamp": "2024-01-02T00:00:00Z", "score": 90},
                {"timestamp": "2024-01-01T00:00:00Z", "score": 85},
            ]
            mock_health_engine = MagicMock()
            mock_health_engine._health_service = mock_health_service
            mock_module_loader.get_module.return_value = mock_health_engine

            mock_engine = MagicMock()
            mock_db_module.get_engine.return_value = mock_engine

            service = HealthService()
            result = service.get_analysis_history("test-host-id", limit=10)

            assert len(result) == 2
            assert result[0]["score"] == 90

    def test_get_analysis_history_empty(self):
        """Test get_analysis_history with empty history."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader, patch.object(
            health_service_module, "db_module"
        ) as mock_db_module:
            mock_license_service.has_module.return_value = True

            mock_health_service = MagicMock()
            mock_health_service.get_analysis_history.return_value = []
            mock_health_engine = MagicMock()
            mock_health_engine._health_service = mock_health_service
            mock_module_loader.get_module.return_value = mock_health_engine

            mock_engine = MagicMock()
            mock_db_module.get_engine.return_value = mock_engine

            service = HealthService()
            result = service.get_analysis_history("test-host-id")

            assert result == []

    def test_get_analysis_history_default_limit(self):
        """Test get_analysis_history uses default limit."""
        with patch.object(
            health_service_module, "license_service"
        ) as mock_license_service, patch.object(
            health_service_module, "module_loader"
        ) as mock_module_loader, patch.object(
            health_service_module, "db_module"
        ) as mock_db_module:
            mock_license_service.has_module.return_value = True

            mock_health_service = MagicMock()
            mock_health_service.get_analysis_history.return_value = []
            mock_health_engine = MagicMock()
            mock_health_engine._health_service = mock_health_service
            mock_module_loader.get_module.return_value = mock_health_engine

            mock_engine = MagicMock()
            mock_db_module.get_engine.return_value = mock_engine

            service = HealthService()
            service.get_analysis_history("test-host-id")

            # Verify default limit of 10 was used
            mock_health_service.get_analysis_history.assert_called_once()
            call_args = mock_health_service.get_analysis_history.call_args
            assert call_args[0][1] == 10  # second positional arg is limit
