"""
Comprehensive unit tests for the health service functionality.

Tests cover:
- HealthService wrapper class
- HealthAnalysisError exception handling
- Licensing and module loading integration
- Database session management
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.health.health_service import HealthAnalysisError, HealthService
from backend.licensing.features import ModuleCode
from backend.persistence import models

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def test_engine():
    """Create a shared in-memory SQLite database for testing.

    Note: Uses checkfirst=True to handle potential duplicate index issues.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        models.Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception:
        # If there's an issue with model definitions, create a minimal engine
        pass
    return engine


@pytest.fixture
def mock_engine():
    """Create a mock database engine for tests that don't need real DB."""
    engine = MagicMock()
    return engine


@pytest.fixture
def test_session(test_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def mock_health_engine():
    """Create a mock health_engine module with _health_service."""
    mock_engine = MagicMock()
    mock_engine._health_service = MagicMock()
    return mock_engine


@pytest.fixture
def health_service():
    """Create a fresh HealthService instance."""
    return HealthService()


# =============================================================================
# HealthAnalysisError TESTS
# =============================================================================


class TestHealthAnalysisError:
    """Test cases for the HealthAnalysisError exception."""

    def test_exception_creation(self):
        """Test creating a HealthAnalysisError."""
        error = HealthAnalysisError("Test error message")
        assert str(error) == "Test error message"

    def test_exception_is_exception_subclass(self):
        """Test that HealthAnalysisError is an Exception subclass."""
        assert issubclass(HealthAnalysisError, Exception)

    def test_exception_can_be_raised(self):
        """Test that HealthAnalysisError can be raised and caught."""
        with pytest.raises(HealthAnalysisError) as exc_info:
            raise HealthAnalysisError("Pro+ license required")
        assert "Pro+ license required" in str(exc_info.value)

    def test_exception_with_no_message(self):
        """Test creating a HealthAnalysisError with no message."""
        error = HealthAnalysisError()
        assert str(error) == ""


# =============================================================================
# HealthService._get_module() TESTS
# =============================================================================


class TestHealthServiceGetModule:
    """Test cases for HealthService._get_module() method."""

    def test_get_module_no_license(self, health_service):
        """Test _get_module raises error when no Pro+ license."""
        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service:
            mock_license_service.has_module.return_value = False

            with pytest.raises(HealthAnalysisError) as exc_info:
                health_service._get_module()

            assert "Pro+ license" in str(exc_info.value)
            assert "health_engine module" in str(exc_info.value)
            mock_license_service.has_module.assert_called_once_with(
                ModuleCode.HEALTH_ENGINE
            )

    def test_get_module_license_but_not_loaded(self, health_service):
        """Test _get_module raises error when module not loaded."""
        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader:
            mock_license_service.has_module.return_value = True
            mock_module_loader.get_module.return_value = None

            with pytest.raises(HealthAnalysisError) as exc_info:
                health_service._get_module()

            assert "not loaded" in str(exc_info.value)
            mock_module_loader.get_module.assert_called_once_with("health_engine")

    def test_get_module_success(self, health_service, mock_health_engine):
        """Test _get_module returns module when available."""
        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader:
            mock_license_service.has_module.return_value = True
            mock_module_loader.get_module.return_value = mock_health_engine

            result = health_service._get_module()

            assert result == mock_health_engine
            mock_license_service.has_module.assert_called_once_with(
                ModuleCode.HEALTH_ENGINE
            )
            mock_module_loader.get_module.assert_called_once_with("health_engine")


# =============================================================================
# HealthService._get_db_session() TESTS
# =============================================================================


class TestHealthServiceGetDbSession:
    """Test cases for HealthService._get_db_session() method."""

    def test_get_db_session_returns_session(self, health_service, mock_engine):
        """Test _get_db_session returns a valid database session."""
        with patch("backend.health.health_service.db_module") as mock_db_module, patch(
            "sqlalchemy.orm.sessionmaker"
        ) as mock_sessionmaker:
            mock_db_module.get_engine.return_value = mock_engine
            mock_session = MagicMock()
            mock_sessionmaker.return_value.return_value = mock_session

            session = health_service._get_db_session()

            assert session is not None
            mock_sessionmaker.assert_called_once()

    def test_get_db_session_uses_correct_settings(self, health_service, mock_engine):
        """Test _get_db_session creates session with correct settings."""
        with patch("backend.health.health_service.db_module") as mock_db_module, patch(
            "sqlalchemy.orm.sessionmaker"
        ) as mock_sessionmaker:
            mock_db_module.get_engine.return_value = mock_engine
            mock_session = MagicMock()
            mock_session.is_active = True
            mock_sessionmaker.return_value.return_value = mock_session

            session = health_service._get_db_session()

            # Verify sessionmaker was called with correct args
            call_kwargs = mock_sessionmaker.call_args.kwargs
            assert call_kwargs.get("autocommit") is False
            assert call_kwargs.get("autoflush") is False


# =============================================================================
# HealthService.analyze_host() TESTS
# =============================================================================


class TestHealthServiceAnalyzeHost:
    """Test cases for HealthService.analyze_host() method."""

    def test_analyze_host_no_license(self, health_service):
        """Test analyze_host raises error without Pro+ license."""
        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service:
            mock_license_service.has_module.return_value = False

            with pytest.raises(HealthAnalysisError) as exc_info:
                health_service.analyze_host("host-123")

            assert "Pro+ license" in str(exc_info.value)

    def test_analyze_host_success(self, health_service, mock_engine):
        """Test analyze_host returns analysis results."""
        expected_result = {
            "host_id": "host-123",
            "score": 85,
            "grade": "B",
            "issues": [],
            "recommendations": [],
        }

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.analyze_host.return_value = (
                expected_result
            )
            mock_module_loader.get_module.return_value = mock_health_engine

            result = health_service.analyze_host("host-123")

            assert result == expected_result
            mock_health_engine._health_service.analyze_host.assert_called_once()

    def test_analyze_host_passes_correct_args(self, health_service, mock_engine):
        """Test analyze_host passes correct arguments to health_engine."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.analyze_host.return_value = {}
            mock_module_loader.get_module.return_value = mock_health_engine

            health_service.analyze_host("host-456")

            # Verify the call was made with host_id, db session, and models
            call_args = mock_health_engine._health_service.analyze_host.call_args
            assert call_args[0][0] == "host-456"  # host_id
            # Second arg should be a session (can't compare directly)
            assert call_args[0][2] == models  # models module


# =============================================================================
# HealthService.get_latest_analysis() TESTS
# =============================================================================


class TestHealthServiceGetLatestAnalysis:
    """Test cases for HealthService.get_latest_analysis() method."""

    def test_get_latest_analysis_no_license(self, health_service):
        """Test get_latest_analysis raises error without Pro+ license."""
        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service:
            mock_license_service.has_module.return_value = False

            with pytest.raises(HealthAnalysisError):
                health_service.get_latest_analysis("host-123")

    def test_get_latest_analysis_returns_result(self, health_service, mock_engine):
        """Test get_latest_analysis returns analysis when available."""
        expected_result = {
            "host_id": "host-123",
            "score": 92,
            "grade": "A-",
            "analyzed_at": "2024-01-15T10:30:00Z",
        }

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.get_latest_analysis.return_value = (
                expected_result
            )
            mock_module_loader.get_module.return_value = mock_health_engine

            result = health_service.get_latest_analysis("host-123")

            assert result == expected_result

    def test_get_latest_analysis_returns_none_when_no_analysis(
        self, health_service, mock_engine
    ):
        """Test get_latest_analysis returns None when no analysis exists."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.get_latest_analysis.return_value = None
            mock_module_loader.get_module.return_value = mock_health_engine

            result = health_service.get_latest_analysis("host-123")

            assert result is None


# =============================================================================
# HealthService.get_analysis_history() TESTS
# =============================================================================


class TestHealthServiceGetAnalysisHistory:
    """Test cases for HealthService.get_analysis_history() method."""

    def test_get_analysis_history_no_license(self, health_service):
        """Test get_analysis_history raises error without Pro+ license."""
        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service:
            mock_license_service.has_module.return_value = False

            with pytest.raises(HealthAnalysisError):
                health_service.get_analysis_history("host-123")

    def test_get_analysis_history_returns_list(self, health_service, mock_engine):
        """Test get_analysis_history returns list of analyses."""
        expected_result = [
            {"host_id": "host-123", "score": 92, "analyzed_at": "2024-01-15T10:30:00Z"},
            {"host_id": "host-123", "score": 88, "analyzed_at": "2024-01-14T10:30:00Z"},
            {"host_id": "host-123", "score": 85, "analyzed_at": "2024-01-13T10:30:00Z"},
        ]

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.get_analysis_history.return_value = (
                expected_result
            )
            mock_module_loader.get_module.return_value = mock_health_engine

            result = health_service.get_analysis_history("host-123")

            assert result == expected_result
            assert len(result) == 3

    def test_get_analysis_history_with_limit(self, health_service, mock_engine):
        """Test get_analysis_history respects limit parameter."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.get_analysis_history.return_value = []
            mock_module_loader.get_module.return_value = mock_health_engine

            health_service.get_analysis_history("host-123", limit=5)

            # Verify limit was passed correctly
            call_args = (
                mock_health_engine._health_service.get_analysis_history.call_args
            )
            assert call_args[0][0] == "host-123"  # host_id
            assert call_args[0][1] == 5  # limit

    def test_get_analysis_history_default_limit(self, health_service, mock_engine):
        """Test get_analysis_history uses default limit of 10."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.get_analysis_history.return_value = []
            mock_module_loader.get_module.return_value = mock_health_engine

            health_service.get_analysis_history("host-123")

            # Verify default limit of 10 was used
            call_args = (
                mock_health_engine._health_service.get_analysis_history.call_args
            )
            assert call_args[0][1] == 10  # default limit

    def test_get_analysis_history_empty_list(self, health_service, mock_engine):
        """Test get_analysis_history returns empty list when no history."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.get_analysis_history.return_value = []
            mock_module_loader.get_module.return_value = mock_health_engine

            result = health_service.get_analysis_history("host-123")

            assert result == []
            assert isinstance(result, list)


# =============================================================================
# GLOBAL health_service INSTANCE TESTS
# =============================================================================


class TestGlobalHealthServiceInstance:
    """Test cases for the global health_service instance."""

    def test_global_instance_exists(self):
        """Test that global health_service instance exists."""
        from backend.health.health_service import health_service as global_instance

        assert global_instance is not None
        assert isinstance(global_instance, HealthService)

    def test_global_instance_is_singleton(self):
        """Test that importing health_service returns same instance."""
        from backend.health.health_service import health_service as instance1
        from backend.health.health_service import health_service as instance2

        # Both imports should return the same instance
        assert instance1 is instance2


# =============================================================================
# HEALTH MODULE __init__.py TESTS
# =============================================================================


class TestHealthModuleInit:
    """Test cases for the health module __init__.py."""

    def test_health_service_exported(self):
        """Test that health_service is exported from health module."""
        from backend.health import health_service

        assert health_service is not None

    def test_all_exports(self):
        """Test __all__ exports from health module."""
        from backend import health

        assert "health_service" in health.__all__


# =============================================================================
# INTEGRATION-STYLE TESTS (with mocked external dependencies)
# =============================================================================


class TestHealthServiceIntegration:
    """Integration-style tests with full mock chain."""

    def test_full_analysis_flow(self, mock_engine):
        """Test complete analysis flow from service to module."""
        # Create analysis result that would come from health_engine
        analysis_result = {
            "host_id": "integration-test-host",
            "score": 78,
            "grade": "C+",
            "issues": [
                {
                    "severity": "warning",
                    "category": "security",
                    "message": "SSH password authentication enabled",
                    "remediation": "Disable password authentication in sshd_config",
                }
            ],
            "recommendations": [
                {
                    "priority": "high",
                    "category": "security",
                    "message": "Enable automatic security updates",
                }
            ],
            "analyzed_at": "2024-01-15T10:30:00Z",
        }

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch(
            "sqlalchemy.orm.sessionmaker"
        ) as mock_sessionmaker:
            # Setup mocks
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.analyze_host.return_value = (
                analysis_result
            )
            mock_module_loader.get_module.return_value = mock_health_engine
            mock_sessionmaker.return_value.return_value = mock_session

            # Create service and run analysis
            service = HealthService()
            result = service.analyze_host("integration-test-host")

            # Verify result structure
            assert result["host_id"] == "integration-test-host"
            assert result["score"] == 78
            assert result["grade"] == "C+"
            assert len(result["issues"]) == 1
            assert len(result["recommendations"]) == 1
            assert result["issues"][0]["severity"] == "warning"
            assert result["recommendations"][0]["priority"] == "high"

    def test_analysis_with_excellent_score(self, mock_engine):
        """Test analysis returning excellent health score."""
        analysis_result = {
            "host_id": "healthy-host",
            "score": 98,
            "grade": "A+",
            "issues": [],
            "recommendations": [],
            "analyzed_at": "2024-01-15T10:30:00Z",
        }

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch(
            "sqlalchemy.orm.sessionmaker"
        ) as mock_sessionmaker:
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.analyze_host.return_value = (
                analysis_result
            )
            mock_module_loader.get_module.return_value = mock_health_engine
            mock_sessionmaker.return_value.return_value = mock_session

            service = HealthService()
            result = service.analyze_host("healthy-host")

            assert result["score"] == 98
            assert result["grade"] == "A+"
            assert result["issues"] == []
            assert result["recommendations"] == []

    def test_analysis_with_critical_issues(self, mock_engine):
        """Test analysis returning critical health issues."""
        analysis_result = {
            "host_id": "critical-host",
            "score": 25,
            "grade": "F",
            "issues": [
                {
                    "severity": "critical",
                    "category": "security",
                    "message": "Root login with password enabled",
                },
                {
                    "severity": "critical",
                    "category": "updates",
                    "message": "Kernel has known critical vulnerabilities",
                },
                {
                    "severity": "high",
                    "category": "disk",
                    "message": "Root filesystem is 95% full",
                },
            ],
            "recommendations": [
                {
                    "priority": "critical",
                    "category": "security",
                    "message": "Immediately disable root password login",
                },
                {
                    "priority": "critical",
                    "category": "updates",
                    "message": "Update kernel immediately",
                },
            ],
            "analyzed_at": "2024-01-15T10:30:00Z",
        }

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch(
            "sqlalchemy.orm.sessionmaker"
        ) as mock_sessionmaker:
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.analyze_host.return_value = (
                analysis_result
            )
            mock_module_loader.get_module.return_value = mock_health_engine
            mock_sessionmaker.return_value.return_value = mock_session

            service = HealthService()
            result = service.analyze_host("critical-host")

            assert result["score"] == 25
            assert result["grade"] == "F"
            assert len(result["issues"]) == 3

            # Verify critical issues present
            critical_issues = [
                i for i in result["issues"] if i["severity"] == "critical"
            ]
            assert len(critical_issues) == 2


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestHealthServiceErrorHandling:
    """Test cases for error handling in HealthService."""

    def test_module_raises_exception(self, health_service, mock_engine):
        """Test handling when health_engine raises an exception."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch.object(
            health_service, "_get_db_session", return_value=mock_session
        ):
            mock_license_service.has_module.return_value = True

            mock_health_engine = MagicMock()
            mock_health_engine._health_service.analyze_host.side_effect = RuntimeError(
                "Database connection failed"
            )
            mock_module_loader.get_module.return_value = mock_health_engine

            with pytest.raises(RuntimeError) as exc_info:
                health_service.analyze_host("host-123")

            assert "Database connection failed" in str(exc_info.value)

    def test_db_connection_failure(self, health_service):
        """Test handling when database connection fails."""
        with patch(
            "backend.health.health_service.license_service"
        ) as mock_license_service, patch(
            "backend.health.health_service.module_loader"
        ) as mock_module_loader, patch(
            "backend.health.health_service.db_module"
        ) as mock_db_module:
            mock_license_service.has_module.return_value = True
            mock_module_loader.get_module.return_value = MagicMock()
            mock_db_module.get_engine.side_effect = RuntimeError("DB unavailable")

            with pytest.raises(RuntimeError) as exc_info:
                health_service.analyze_host("host-123")

            assert "DB unavailable" in str(exc_info.value)
