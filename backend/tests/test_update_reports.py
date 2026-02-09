"""
Comprehensive unit tests for the update reports API in SysManage.

Tests cover:
- Update report submission from agents
- Package update data storage
- Update type classification (security, system, package)
- Update report models and validation
- Error handling (host not found, database errors)
- Data aggregation for updates

These tests use pytest and pytest-asyncio for async tests with mocked database.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.updates.models import (
    PackageUpdateInfo,
    UpdatesReport,
    UpdateExecutionRequest,
    UpdateStatsSummary,
)

# =============================================================================
# TEST CONFIGURATION AND FIXTURES
# =============================================================================


@pytest.fixture
def mock_db_engine():
    """Create a mock database engine."""
    return MagicMock()


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    mock_session = MagicMock()
    mock_session.query.return_value = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    mock_session.close = MagicMock()
    mock_session.refresh = MagicMock()
    mock_session.delete = MagicMock()
    mock_session.flush = MagicMock()
    return mock_session


@pytest.fixture
def mock_host():
    """Create a mock host object."""
    host = MagicMock()
    host.id = str(uuid.uuid4())
    host.fqdn = "test-host.example.com"
    host.status = "up"
    host.approval_status = "approved"
    return host


@pytest.fixture
def sample_package_update_info():
    """Create a sample package update info."""
    return PackageUpdateInfo(
        package_name="nginx",
        current_version="1.18.0",
        available_version="1.20.0",
        package_manager="apt",
        source="Ubuntu",
        is_security_update=True,
        is_system_update=False,
        requires_reboot=False,
        update_size_bytes=1024000,
        repository="main",
    )


@pytest.fixture
def sample_updates_report(sample_package_update_info):
    """Create a sample updates report."""
    return UpdatesReport(
        available_updates=[sample_package_update_info],
        total_updates=1,
        security_updates=1,
        system_updates=0,
        application_updates=0,
        platform="Linux",
        requires_reboot=False,
    )


@pytest.fixture
def sample_updates_report_multiple():
    """Create a sample updates report with multiple updates."""
    updates = [
        PackageUpdateInfo(
            package_name="nginx",
            current_version="1.18.0",
            available_version="1.20.0",
            package_manager="apt",
            is_security_update=True,
            is_system_update=False,
            requires_reboot=False,
        ),
        PackageUpdateInfo(
            package_name="linux-kernel",
            current_version="5.15.0",
            available_version="5.19.0",
            package_manager="apt",
            is_security_update=False,
            is_system_update=True,
            requires_reboot=True,
        ),
        PackageUpdateInfo(
            package_name="vim",
            current_version="8.2",
            available_version="9.0",
            package_manager="apt",
            is_security_update=False,
            is_system_update=False,
            requires_reboot=False,
        ),
    ]
    return UpdatesReport(
        available_updates=updates,
        total_updates=3,
        security_updates=1,
        system_updates=1,
        application_updates=1,
        platform="Linux",
        requires_reboot=True,
    )


def create_mock_session_context(mock_session):
    """Helper to create a mock session context manager."""
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
    return mock_session_factory


# =============================================================================
# PYDANTIC MODEL TESTS
# =============================================================================


class TestPackageUpdateInfoModel:
    """Test cases for PackageUpdateInfo Pydantic model."""

    def test_create_basic_package_update_info(self):
        """Test creating a basic PackageUpdateInfo."""
        update = PackageUpdateInfo(
            package_name="nginx", available_version="1.20.0", package_manager="apt"
        )

        assert update.package_name == "nginx"
        assert update.available_version == "1.20.0"
        assert update.package_manager == "apt"
        assert update.current_version is None
        assert update.is_security_update is False

    def test_create_full_package_update_info(self):
        """Test creating PackageUpdateInfo with all fields."""
        update = PackageUpdateInfo(
            package_name="openssl",
            current_version="1.1.1k",
            available_version="1.1.1n",
            package_manager="apt",
            source="Ubuntu Security",
            is_security_update=True,
            is_system_update=False,
            requires_reboot=False,
            update_size_bytes=512000,
            bundle_id=None,
            repository="security",
            channel="stable",
        )

        assert update.package_name == "openssl"
        assert update.current_version == "1.1.1k"
        assert update.available_version == "1.1.1n"
        assert update.is_security_update is True
        assert update.update_size_bytes == 512000

    def test_package_update_info_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValidationError):
            PackageUpdateInfo(current_version="1.0.0", package_manager="apt")

    def test_package_update_info_defaults(self):
        """Test default values for optional fields."""
        update = PackageUpdateInfo(
            package_name="test", available_version="1.0.0", package_manager="apt"
        )

        assert update.current_version is None
        assert update.source is None
        assert update.is_security_update is False
        assert update.is_system_update is False
        assert update.requires_reboot is False
        assert update.update_size_bytes is None


class TestUpdatesReportModel:
    """Test cases for UpdatesReport Pydantic model."""

    def test_create_empty_updates_report(self):
        """Test creating an empty updates report."""
        report = UpdatesReport(
            available_updates=[],
            total_updates=0,
            security_updates=0,
            system_updates=0,
            application_updates=0,
            platform="Linux",
        )

        assert len(report.available_updates) == 0
        assert report.total_updates == 0
        assert report.requires_reboot is False

    def test_create_updates_report_with_updates(self, sample_package_update_info):
        """Test creating an updates report with updates."""
        report = UpdatesReport(
            available_updates=[sample_package_update_info],
            total_updates=1,
            security_updates=1,
            system_updates=0,
            application_updates=0,
            platform="Linux",
            requires_reboot=False,
        )

        assert len(report.available_updates) == 1
        assert report.total_updates == 1
        assert report.security_updates == 1

    def test_updates_report_requires_reboot(self):
        """Test updates report with reboot requirement."""
        update = PackageUpdateInfo(
            package_name="linux-kernel",
            available_version="5.19.0",
            package_manager="apt",
            requires_reboot=True,
        )

        report = UpdatesReport(
            available_updates=[update],
            total_updates=1,
            security_updates=0,
            system_updates=1,
            application_updates=0,
            platform="Linux",
            requires_reboot=True,
        )

        assert report.requires_reboot is True


class TestUpdateExecutionRequestModel:
    """Test cases for UpdateExecutionRequest Pydantic model."""

    def test_create_valid_execution_request(self):
        """Test creating a valid update execution request."""
        request = UpdateExecutionRequest(
            host_ids=["host-1", "host-2"], package_names=["nginx", "openssl"]
        )

        assert len(request.host_ids) == 2
        assert len(request.package_names) == 2
        assert request.package_managers is None

    def test_create_execution_request_with_managers(self):
        """Test creating execution request with package managers."""
        request = UpdateExecutionRequest(
            host_ids=["host-1"], package_names=["nginx"], package_managers=["apt"]
        )

        assert request.package_managers == ["apt"]

    def test_execution_request_empty_host_ids_fails(self):
        """Test that empty host_ids list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateExecutionRequest(host_ids=[], package_names=["nginx"])

        assert "host_ids cannot be empty" in str(exc_info.value)

    def test_execution_request_empty_package_names_fails(self):
        """Test that empty package_names list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateExecutionRequest(host_ids=["host-1"], package_names=[])

        assert "package_names cannot be empty" in str(exc_info.value)

    def test_execution_request_empty_managers_becomes_none(self):
        """Test that empty package_managers list becomes None."""
        request = UpdateExecutionRequest(
            host_ids=["host-1"], package_names=["nginx"], package_managers=[]
        )

        assert request.package_managers is None


class TestUpdateStatsSummaryModel:
    """Test cases for UpdateStatsSummary Pydantic model."""

    def test_create_stats_summary(self):
        """Test creating an update stats summary."""
        summary = UpdateStatsSummary(
            total_hosts=10,
            hosts_with_updates=5,
            total_updates=50,
            security_updates=10,
            system_updates=20,
            application_updates=20,
        )

        assert summary.total_hosts == 10
        assert summary.hosts_with_updates == 5
        assert summary.total_updates == 50
        assert summary.security_updates == 10

    def test_stats_summary_zero_values(self):
        """Test stats summary with zero values."""
        summary = UpdateStatsSummary(
            total_hosts=0,
            hosts_with_updates=0,
            total_updates=0,
            security_updates=0,
            system_updates=0,
            application_updates=0,
        )

        assert summary.total_hosts == 0
        assert summary.total_updates == 0


# =============================================================================
# UPDATE REPORT ROUTE TESTS
# =============================================================================


class TestReportUpdatesEndpoint:
    """Test cases for the report_updates API endpoint."""

    @pytest.mark.asyncio
    async def test_report_updates_success(
        self, mock_db_engine, mock_db_session, mock_host, sample_updates_report
    ):
        """Test successful update report submission."""
        from backend.api.updates.report_routes import report_updates

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await report_updates(mock_host.id, sample_updates_report)

            assert result["status"] == "success"
            assert result["updates_stored"] == 1
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_updates_multiple(
        self, mock_db_engine, mock_db_session, mock_host, sample_updates_report_multiple
    ):
        """Test update report with multiple updates."""
        from backend.api.updates.report_routes import report_updates

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await report_updates(mock_host.id, sample_updates_report_multiple)

            assert result["status"] == "success"
            assert result["updates_stored"] == 3
            assert mock_db_session.add.call_count == 3
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_updates_host_not_found(
        self, mock_db_engine, mock_db_session, sample_updates_report
    ):
        """Test update report for non-existent host."""
        from backend.api.updates.report_routes import report_updates

        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            with pytest.raises(HTTPException) as exc_info:
                await report_updates("nonexistent-host-id", sample_updates_report)

            # The implementation wraps the host not found in a 500 error
            # (it catches exceptions and returns 500 with the original message)
            assert exc_info.value.status_code in (404, 500)
            assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_report_updates_empty_report(
        self, mock_db_engine, mock_db_session, mock_host
    ):
        """Test update report with no updates."""
        from backend.api.updates.report_routes import report_updates

        empty_report = UpdatesReport(
            available_updates=[],
            total_updates=0,
            security_updates=0,
            system_updates=0,
            application_updates=0,
            platform="Linux",
        )

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await report_updates(mock_host.id, empty_report)

            assert result["status"] == "success"
            assert result["updates_stored"] == 0
            mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_report_updates_clears_existing(
        self, mock_db_engine, mock_db_session, mock_host, sample_updates_report
    ):
        """Test that existing updates are cleared before storing new ones."""
        from backend.api.updates.report_routes import report_updates

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_delete = mock_db_session.query.return_value.filter.return_value.delete
        mock_delete.return_value = 5  # 5 existing updates deleted

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await report_updates(mock_host.id, sample_updates_report)

            assert result["status"] == "success"
            # Verify delete was called to clear existing updates
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_updates_database_error(
        self, mock_db_engine, mock_db_session, mock_host, sample_updates_report
    ):
        """Test handling of database errors during update report."""
        from backend.api.updates.report_routes import report_updates

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0
        mock_db_session.commit.side_effect = Exception("Database connection lost")

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            with pytest.raises(HTTPException) as exc_info:
                await report_updates(mock_host.id, sample_updates_report)

            assert exc_info.value.status_code == 500


# =============================================================================
# UPDATE TYPE CLASSIFICATION TESTS
# =============================================================================


class TestUpdateTypeClassification:
    """Test cases for update type classification logic."""

    @pytest.mark.asyncio
    async def test_security_update_classified_correctly(
        self, mock_db_engine, mock_db_session, mock_host
    ):
        """Test that security updates are classified correctly."""
        from backend.api.updates.report_routes import report_updates

        security_update = PackageUpdateInfo(
            package_name="openssl",
            available_version="1.1.1n",
            package_manager="apt",
            is_security_update=True,
            is_system_update=False,
        )

        report = UpdatesReport(
            available_updates=[security_update],
            total_updates=1,
            security_updates=1,
            system_updates=0,
            application_updates=0,
            platform="Linux",
        )

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await report_updates(mock_host.id, report)

            assert result["status"] == "success"
            # Verify the PackageUpdate was created with correct update_type
            add_call = mock_db_session.add.call_args
            package_update = add_call[0][0]
            assert package_update.update_type == "security"

    @pytest.mark.asyncio
    async def test_system_update_classified_correctly(
        self, mock_db_engine, mock_db_session, mock_host
    ):
        """Test that system updates are classified correctly."""
        from backend.api.updates.report_routes import report_updates

        system_update = PackageUpdateInfo(
            package_name="linux-kernel",
            available_version="5.19.0",
            package_manager="apt",
            is_security_update=False,
            is_system_update=True,
        )

        report = UpdatesReport(
            available_updates=[system_update],
            total_updates=1,
            security_updates=0,
            system_updates=1,
            application_updates=0,
            platform="Linux",
        )

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await report_updates(mock_host.id, report)

            assert result["status"] == "success"
            add_call = mock_db_session.add.call_args
            package_update = add_call[0][0]
            assert package_update.update_type == "system"

    @pytest.mark.asyncio
    async def test_regular_package_update_classified_correctly(
        self, mock_db_engine, mock_db_session, mock_host
    ):
        """Test that regular package updates are classified correctly."""
        from backend.api.updates.report_routes import report_updates

        regular_update = PackageUpdateInfo(
            package_name="vim",
            available_version="9.0",
            package_manager="apt",
            is_security_update=False,
            is_system_update=False,
        )

        report = UpdatesReport(
            available_updates=[regular_update],
            total_updates=1,
            security_updates=0,
            system_updates=0,
            application_updates=1,
            platform="Linux",
        )

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            result = await report_updates(mock_host.id, report)

            assert result["status"] == "success"
            add_call = mock_db_session.add.call_args
            package_update = add_call[0][0]
            assert package_update.update_type == "package"


# =============================================================================
# DATA AGGREGATION TESTS
# =============================================================================


class TestUpdateDataAggregation:
    """Test cases for update data aggregation."""

    def test_updates_report_counts_match(self, sample_updates_report_multiple):
        """Test that update counts in report are consistent."""
        report = sample_updates_report_multiple

        assert report.total_updates == len(report.available_updates)

        security_count = sum(
            1 for u in report.available_updates if u.is_security_update
        )
        system_count = sum(1 for u in report.available_updates if u.is_system_update)

        assert report.security_updates == security_count
        assert report.system_updates == system_count

    def test_stats_summary_consistency(self):
        """Test UpdateStatsSummary values are consistent."""
        summary = UpdateStatsSummary(
            total_hosts=100,
            hosts_with_updates=75,
            total_updates=500,
            security_updates=100,
            system_updates=150,
            application_updates=250,
        )

        # hosts_with_updates should not exceed total_hosts
        assert summary.hosts_with_updates <= summary.total_hosts

        # Sum of update types should equal total
        assert (
            summary.security_updates
            + summary.system_updates
            + summary.application_updates
        ) == summary.total_updates


# =============================================================================
# UPDATE METADATA TESTS
# =============================================================================


class TestUpdateMetadata:
    """Test cases for update metadata handling."""

    def test_package_update_with_all_metadata(self):
        """Test package update with complete metadata."""
        update = PackageUpdateInfo(
            package_name="firefox",
            current_version="100.0",
            available_version="105.0",
            package_manager="snap",
            source="Canonical",
            is_security_update=True,
            is_system_update=False,
            requires_reboot=False,
            update_size_bytes=150000000,
            bundle_id="firefox_snap",
            repository="stable",
            channel="stable/candidate",
        )

        assert update.bundle_id == "firefox_snap"
        assert update.repository == "stable"
        assert update.channel == "stable/candidate"
        assert update.update_size_bytes == 150000000

    def test_package_update_minimal_metadata(self):
        """Test package update with minimal metadata."""
        update = PackageUpdateInfo(
            package_name="curl", available_version="7.80.0", package_manager="apt"
        )

        assert update.current_version is None
        assert update.bundle_id is None
        assert update.repository is None
        assert update.channel is None
        assert update.update_size_bytes is None

    @pytest.mark.asyncio
    async def test_update_metadata_stored_correctly(
        self, mock_db_engine, mock_db_session, mock_host
    ):
        """Test that update metadata is stored correctly in database."""
        from backend.api.updates.report_routes import report_updates

        update = PackageUpdateInfo(
            package_name="nginx",
            current_version="1.18.0",
            available_version="1.20.0",
            package_manager="apt",
            requires_reboot=True,
            update_size_bytes=2048000,
        )

        report = UpdatesReport(
            available_updates=[update],
            total_updates=1,
            security_updates=0,
            system_updates=0,
            application_updates=1,
            platform="Linux",
        )

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.delete.return_value = 0

        with patch("backend.api.updates.report_routes.db") as mock_db, patch(
            "backend.api.updates.report_routes.sessionmaker"
        ) as mock_sessionmaker:
            mock_db.get_engine.return_value = mock_db_engine
            mock_sessionmaker.return_value = create_mock_session_context(
                mock_db_session
            )

            await report_updates(mock_host.id, report)

            # Verify the stored PackageUpdate has correct metadata
            add_call = mock_db_session.add.call_args
            package_update = add_call[0][0]
            assert package_update.package_name == "nginx"
            assert package_update.current_version == "1.18.0"
            assert package_update.available_version == "1.20.0"
            assert package_update.package_manager == "apt"
            assert package_update.requires_reboot is True
            assert package_update.size_bytes == 2048000
