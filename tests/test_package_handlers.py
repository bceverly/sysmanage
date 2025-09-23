"""
Unit tests for package data handlers.
Tests the batch package handlers (handle_packages_batch_start, handle_packages_batch, handle_packages_batch_end).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.api.package_handlers import (
    handle_packages_batch,
    handle_packages_batch_end,
    handle_packages_batch_start,
)
from backend.persistence import models


class TestPackageHandlers:
    """Test cases for package data handlers."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection object."""
        from unittest.mock import AsyncMock

        connection = Mock()
        connection.host_id = "550e8400-e29b-41d4-a716-446655440001"
        connection.hostname = "test-host"
        connection.send_message = AsyncMock()
        return connection

    @pytest.fixture
    def sample_host(self, session):
        """Create a sample host for testing."""
        host = models.Host(
            id="550e8400-e29b-41d4-a716-446655440001",
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
        )
        session.add(host)
        session.commit()
        return host

    @pytest.fixture
    def sample_batch_start_data(self):
        """Create sample batch start message data for testing."""
        return {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "batch_id": "test-batch-123",
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "package_managers": ["apt", "snap"],
        }

    @pytest.fixture
    def sample_batch_data(self):
        """Create sample batch message data for testing."""
        return {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "batch_id": "test-batch-123",
            "package_managers": {
                "apt": [
                    {
                        "name": "nginx",
                        "version": "1.18.0",
                        "description": "High performance web server",
                    },
                    {
                        "name": "python3",
                        "version": "3.10.12",
                        "description": "Python 3 programming language",
                    },
                ],
                "snap": [
                    {
                        "name": "docker",
                        "version": "24.0.5",
                        "description": "Container platform",
                    }
                ],
            },
        }

    @pytest.fixture
    def sample_batch_end_data(self):
        """Create sample batch end message data for testing."""
        return {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "batch_id": "test-batch-123",
        }

    @pytest.mark.asyncio
    async def test_handle_packages_batch_start_success(
        self, session, mock_connection, sample_host, sample_batch_start_data
    ):
        """Test successful batch start handling."""
        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch_start(
                session, mock_connection, sample_batch_start_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "batch_started"
            assert result["batch_id"] == "test-batch-123"

    @pytest.mark.asyncio
    async def test_handle_packages_batch_start_no_host_id(
        self, session, sample_batch_start_data
    ):
        """Test batch start handling without host_id in connection."""
        from unittest.mock import AsyncMock

        connection = Mock()
        connection.host_id = None
        connection.send_message = AsyncMock()

        result = await handle_packages_batch_start(
            session, connection, sample_batch_start_data
        )

        assert result["message_type"] == "error"
        assert "host_not_registered" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_packages_batch_start_missing_batch_id(
        self, session, mock_connection, sample_host
    ):
        """Test batch start handling with missing batch_id."""
        message_data = {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "os_name": "Ubuntu",
            "os_version": "22.04",
            # Missing batch_id
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch_start(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "error"
            assert "Missing batch_id" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_packages_batch_success(
        self, session, mock_connection, sample_host, sample_batch_data
    ):
        """Test successful batch handling."""
        # First start a batch to set up the session
        from backend.api.package_handlers import _batch_sessions

        _batch_sessions["test-batch-123"] = {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "package_managers": ["apt", "snap"],
            "total_packages": 0,
            "started_at": datetime.now(timezone.utc),
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch(
                session, mock_connection, sample_batch_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "batch_processed"
            assert result["batch_id"] == "test-batch-123"
            assert result["packages_in_batch"] == 3

            # Verify packages were stored in database
            packages = session.query(models.AvailablePackage).all()
            assert len(packages) == 3

            # Check specific packages
            nginx_package = (
                session.query(models.AvailablePackage)
                .filter_by(package_name="nginx")
                .first()
            )
            assert nginx_package is not None
            assert nginx_package.package_version == "1.18.0"
            assert nginx_package.package_manager == "apt"
            assert nginx_package.os_name == "Ubuntu"
            assert nginx_package.os_version == "22.04"

    @pytest.mark.asyncio
    async def test_handle_packages_batch_invalid_batch_id(
        self, session, mock_connection, sample_host, sample_batch_data
    ):
        """Test batch handling with invalid batch_id."""
        # Don't set up batch session - batch_id will be invalid
        sample_batch_data["batch_id"] = "invalid-batch-id"

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch(
                session, mock_connection, sample_batch_data
            )

            assert result["message_type"] == "error"
            assert "Invalid or expired batch_id" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_packages_batch_end_success(
        self, session, mock_connection, sample_host, sample_batch_end_data
    ):
        """Test successful batch end handling."""
        # First set up a batch session
        from backend.api.package_handlers import _batch_sessions

        _batch_sessions["test-batch-123"] = {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "package_managers": ["apt", "snap"],
            "total_packages": 5,
            "started_at": datetime.now(timezone.utc),
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch_end(
                session, mock_connection, sample_batch_end_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "batch_completed"
            assert result["batch_id"] == "test-batch-123"
            assert result["total_packages_processed"] == 5

            # Verify batch session was cleaned up
            assert "test-batch-123" not in _batch_sessions

    @pytest.mark.asyncio
    async def test_handle_packages_batch_end_invalid_batch_id(
        self, session, mock_connection, sample_host, sample_batch_end_data
    ):
        """Test batch end handling with invalid batch_id."""
        # Don't set up batch session - batch_id will be invalid
        sample_batch_end_data["batch_id"] = "invalid-batch-id"

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch_end(
                session, mock_connection, sample_batch_end_data
            )

            assert result["message_type"] == "error"
            assert "Invalid or expired batch_id" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_packages_batch_wrong_host(
        self, session, mock_connection, sample_host, sample_batch_data
    ):
        """Test batch handling with wrong host for batch."""
        # Set up batch session for different host
        from backend.api.package_handlers import _batch_sessions

        _batch_sessions["test-batch-123"] = {
            "host_id": "different-host-id",  # Different from mock_connection.host_id
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "package_managers": ["apt"],
            "total_packages": 0,
            "started_at": datetime.now(timezone.utc),
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch(
                session, mock_connection, sample_batch_data
            )

            assert result["message_type"] == "error"
            assert "Batch belongs to different host" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_packages_batch_invalid_packages(
        self, session, mock_connection, sample_host
    ):
        """Test batch handling with invalid package data."""
        # Set up batch session
        from backend.api.package_handlers import _batch_sessions

        _batch_sessions["test-batch-123"] = {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "package_managers": ["apt"],
            "total_packages": 0,
            "started_at": datetime.now(timezone.utc),
        }

        message_data = {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "batch_id": "test-batch-123",
            "package_managers": {
                "apt": [
                    {
                        "name": "",  # Invalid: empty name
                        "version": "1.0.0",
                        "description": "Test package",
                    },
                    {
                        "name": "valid-package",
                        "version": "",  # Invalid: empty version
                        "description": "Test package",
                    },
                    {
                        "name": "another-valid-package",
                        "version": "2.0.0",
                        "description": "Valid test package",
                    },
                ]
            },
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch(session, mock_connection, message_data)

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "batch_processed"
            assert result["packages_in_batch"] == 1  # Only valid package processed

            # Verify only valid package was stored
            packages = session.query(models.AvailablePackage).all()
            assert len(packages) == 1
            assert packages[0].package_name == "another-valid-package"

    @pytest.mark.asyncio
    async def test_handle_packages_batch_long_description(
        self, session, mock_connection, sample_host
    ):
        """Test batch handling with long description."""
        # Set up batch session
        from backend.api.package_handlers import _batch_sessions

        _batch_sessions["test-batch-123"] = {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "package_managers": ["apt"],
            "total_packages": 0,
            "started_at": datetime.now(timezone.utc),
        }

        long_description = "A" * 1500  # Longer than 1000 chars
        message_data = {
            "host_id": "550e8400-e29b-41d4-a716-446655440001",
            "batch_id": "test-batch-123",
            "package_managers": {
                "apt": [
                    {
                        "name": "test-package",
                        "version": "1.0.0",
                        "description": long_description,
                    }
                ]
            },
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_batch(session, mock_connection, message_data)

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "batch_processed"

            # Verify description was truncated
            package = session.query(models.AvailablePackage).first()
            assert len(package.package_description) == 1000
            assert package.package_description.endswith("...")
