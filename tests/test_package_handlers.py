"""
Unit tests for package data handlers.
Tests the handle_packages_update function and related functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from backend.api.package_handlers import handle_packages_update
from backend.persistence import models


class TestPackageHandlers:
    """Test cases for package data handlers."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection object."""
        from unittest.mock import AsyncMock

        connection = Mock()
        connection.host_id = 1
        connection.hostname = "test-host"
        connection.send_message = AsyncMock()
        return connection

    @pytest.fixture
    def sample_host(self, session):
        """Create a sample host for testing."""
        host = models.Host(
            id=1,
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
    def sample_message_data(self):
        """Create sample message data for testing."""
        return {
            "host_id": 1,
            "os_name": "Ubuntu",
            "os_version": "22.04",
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

    @pytest.mark.asyncio
    async def test_handle_packages_update_success(
        self, session, mock_connection, sample_host, sample_message_data
    ):
        """Test successful package update handling."""
        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_update(
                session, mock_connection, sample_message_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "success"
            assert result["packages_processed"] == 3

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
    async def test_handle_packages_update_no_host_id(
        self, session, sample_message_data
    ):
        """Test package update handling without host_id in connection."""
        from unittest.mock import AsyncMock

        connection = Mock()
        connection.host_id = None
        connection.send_message = AsyncMock()

        result = await handle_packages_update(session, connection, sample_message_data)

        assert result["message_type"] == "error"
        assert result["error"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_handle_packages_update_invalid_host_id(
        self, session, mock_connection, sample_message_data
    ):
        """Test package update handling with invalid host_id."""
        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = False
            sample_message_data["host_id"] = 999

            result = await handle_packages_update(
                session, mock_connection, sample_message_data
            )

            assert result["message_type"] == "error"
            assert result["error"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_handle_packages_update_host_not_found(
        self, session, mock_connection, sample_message_data
    ):
        """Test package update handling when host not found in database."""
        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True
            mock_connection.host_id = 999  # Non-existent host

            result = await handle_packages_update(
                session, mock_connection, sample_message_data
            )

            assert result["message_type"] == "error"
            assert result["error"] == "Host not found"

    @pytest.mark.asyncio
    async def test_handle_packages_update_empty_packages(
        self, session, mock_connection, sample_host
    ):
        """Test package update handling with empty package list."""
        message_data = {"host_id": 1, "package_managers": {}}

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_update(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "success"
            assert result["packages_processed"] == 0

    @pytest.mark.asyncio
    async def test_handle_packages_update_invalid_packages(
        self, session, mock_connection, sample_host
    ):
        """Test package update handling with invalid package data."""
        message_data = {
            "host_id": 1,
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

            result = await handle_packages_update(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "success"
            assert result["packages_processed"] == 1  # Only valid package processed

            # Verify only valid package was stored
            packages = session.query(models.AvailablePackage).all()
            assert len(packages) == 1
            assert packages[0].package_name == "another-valid-package"

    @pytest.mark.asyncio
    async def test_handle_packages_update_long_description(
        self, session, mock_connection, sample_host
    ):
        """Test package update handling with long description."""
        long_description = "A" * 1500  # Longer than 1000 chars
        message_data = {
            "host_id": 1,
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

            result = await handle_packages_update(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "success"

            # Verify description was truncated
            package = session.query(models.AvailablePackage).first()
            assert len(package.package_description) == 1000
            assert package.package_description.endswith("...")

    @pytest.mark.asyncio
    async def test_handle_packages_update_replaces_existing(
        self, session, mock_connection, sample_host
    ):
        """Test that package update replaces existing packages for same OS/manager."""
        # First, add some existing packages
        now = datetime.now(timezone.utc)
        existing_package = models.AvailablePackage(
            os_name="Ubuntu",
            os_version="22.04",
            package_manager="apt",
            package_name="old-package",
            package_version="1.0.0",
            package_description="Old package",
            last_updated=now,
            created_at=now,
        )
        session.add(existing_package)
        session.commit()

        # Now send new package data
        message_data = {
            "host_id": 1,
            "package_managers": {
                "apt": [
                    {
                        "name": "new-package",
                        "version": "2.0.0",
                        "description": "New package",
                    }
                ]
            },
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_update(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "success"

            # Verify old package was replaced
            packages = (
                session.query(models.AvailablePackage)
                .filter_by(os_name="Ubuntu", os_version="22.04", package_manager="apt")
                .all()
            )
            assert len(packages) == 1
            assert packages[0].package_name == "new-package"

    @pytest.mark.asyncio
    async def test_handle_packages_update_uses_host_os_fallback(
        self, session, mock_connection, sample_host
    ):
        """Test that handler uses host OS info when not in message."""
        message_data = {
            "host_id": 1,
            # No os_name or os_version in message
            "package_managers": {
                "apt": [
                    {
                        "name": "test-package",
                        "version": "1.0.0",
                        "description": "Test package",
                    }
                ]
            },
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_update(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "success"

            # Verify package used host OS info
            package = session.query(models.AvailablePackage).first()
            assert package.os_name == "Ubuntu"  # From sample_host
            assert package.os_version == "22.04"  # From sample_host

    @pytest.mark.asyncio
    async def test_handle_packages_update_database_error(
        self, mock_connection, sample_message_data
    ):
        """Test package update handling with database error."""
        # Mock session that raises an exception
        mock_session = Mock()
        mock_session.query.side_effect = Exception("Database error")

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_update(
                mock_session, mock_connection, sample_message_data
            )

            assert result["message_type"] == "error"
            assert "Failed to process available packages" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_packages_update_no_description(
        self, session, mock_connection, sample_host
    ):
        """Test package update handling with packages that have no description."""
        message_data = {
            "host_id": 1,
            "package_managers": {
                "apt": [
                    {
                        "name": "test-package",
                        "version": "1.0.0",
                        # No description field
                    }
                ]
            },
        }

        with patch(
            "backend.utils.host_validation.validate_host_id", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = True

            result = await handle_packages_update(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "acknowledgment"
            assert result["status"] == "success"

            # Verify package was stored with None description
            package = session.query(models.AvailablePackage).first()
            assert package.package_name == "test-package"
            assert package.package_description is None
