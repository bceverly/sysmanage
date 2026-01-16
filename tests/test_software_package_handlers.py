"""
Comprehensive unit tests for software_package_handlers module.
Tests handle_software_update, handle_package_updates_update, handle_package_collection,
handle_third_party_repository_update, and handle_antivirus_status_update.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.api.handlers.software_package_handlers import (
    handle_antivirus_status_update,
    handle_package_collection,
    handle_package_updates_update,
    handle_software_update,
    handle_third_party_repository_update,
)
from backend.persistence import models


class TestHandleSoftwareUpdate:
    """Test cases for handle_software_update function."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection object."""
        connection = Mock()
        connection.host_id = "550e8400-e29b-41d4-a716-446655440001"
        connection.hostname = "test-host"
        return connection

    @pytest.fixture
    def sample_host(self, session):
        """Create a sample host for testing."""
        host = models.Host(
            id="550e8400-e29b-41d4-a716-446655440001",
            fqdn="test-host.example.com",
            ipv4="192.168.1.100",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()
        return host

    @pytest.mark.asyncio
    async def test_handle_software_update_success(
        self, session, mock_connection, sample_host
    ):
        """Test successful software inventory update."""
        message_data = {
            "software_packages": [
                {
                    "package_name": "nginx",
                    "version": "1.18.0",
                    "package_manager": "apt",
                    "description": "Web server",
                    "architecture": "amd64",
                    "installation_path": "/usr/sbin/nginx",
                },
                {
                    "package_name": "python3",
                    "version": "3.10.0",
                    "package_manager": "apt",
                    "description": "Python interpreter",
                    "architecture": "amd64",
                },
            ]
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_software_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "success"
        assert "software_inventory_updated" in result["result"]

        # Verify packages were added
        packages = (
            session.query(models.SoftwarePackage)
            .filter_by(host_id=mock_connection.host_id)
            .all()
        )
        assert len(packages) == 2
        assert packages[0].package_name == "nginx"
        assert packages[0].package_version == "1.18.0"
        assert packages[1].package_name == "python3"

    @pytest.mark.asyncio
    async def test_handle_software_update_empty_packages(
        self, session, mock_connection, sample_host
    ):
        """Test software update with empty package list."""
        message_data = {"software_packages": []}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_software_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "success"

    @pytest.mark.asyncio
    async def test_handle_software_update_no_packages_key(
        self, session, mock_connection, sample_host
    ):
        """Test software update without packages key."""
        message_data = {}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_software_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "success"

    @pytest.mark.asyncio
    async def test_handle_software_update_replaces_existing(
        self, session, mock_connection, sample_host
    ):
        """Test that software update replaces existing packages."""
        # Add initial package
        old_package = models.SoftwarePackage(
            host_id=mock_connection.host_id,
            package_name="old-package",
            package_version="1.0.0",
            package_manager="apt",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(old_package)
        session.commit()

        message_data = {
            "software_packages": [
                {
                    "package_name": "new-package",
                    "version": "2.0.0",
                    "package_manager": "apt",
                }
            ]
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_software_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "success"

        # Verify old package is gone and new one exists
        packages = (
            session.query(models.SoftwarePackage)
            .filter_by(host_id=mock_connection.host_id)
            .all()
        )
        assert len(packages) == 1
        assert packages[0].package_name == "new-package"

    @pytest.mark.asyncio
    async def test_handle_software_update_no_host_id(self, session):
        """Test software update with missing host_id."""
        connection = Mock()
        connection.host_id = None
        message_data = {"software_packages": []}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_software_update(session, connection, message_data)

        assert result["message_type"] == "error"
        assert "Host not registered" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_software_update_invalid_host_id(
        self, session, mock_connection, sample_host
    ):
        """Test software update with invalid host_id in message."""
        message_data = {
            "host_id": "invalid-host-id",
            "software_packages": [],
        }

        with patch(
            "backend.utils.host_validation.validate_host_id",
            return_value=False,
        ):
            result = await handle_software_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "error"
        assert result["error_type"] == "host_not_registered"

    @pytest.mark.asyncio
    async def test_handle_software_update_missing_version(
        self, session, mock_connection, sample_host
    ):
        """Test software update with package missing version."""
        message_data = {
            "software_packages": [
                {"package_name": "test-package", "package_manager": "apt"}
            ]
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_software_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "success"

        # Verify package was added with "unknown" version
        packages = (
            session.query(models.SoftwarePackage)
            .filter_by(host_id=mock_connection.host_id)
            .all()
        )
        assert len(packages) == 1
        assert packages[0].package_version == "unknown"

    @pytest.mark.asyncio
    async def test_handle_software_update_database_error(
        self, session, mock_connection, sample_host
    ):
        """Test software update with database error."""
        message_data = {
            "software_packages": [
                {"package_name": "test", "version": "1.0", "package_manager": "apt"}
            ]
        }

        with patch("backend.utils.host_validation.validate_host_id"), patch.object(
            session, "execute", side_effect=Exception("Database error")
        ):
            result = await handle_software_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "error"
        assert "Failed to update software inventory" in result["message"]


class TestHandlePackageUpdatesUpdate:
    """Test cases for handle_package_updates_update function."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection object."""
        connection = Mock()
        connection.host_id = "550e8400-e29b-41d4-a716-446655440002"
        connection.hostname = "test-host"
        return connection

    @pytest.fixture
    def sample_host(self, session):
        """Create a sample host for testing."""
        host = models.Host(
            id="550e8400-e29b-41d4-a716-446655440002",
            fqdn="test-host2.example.com",
            ipv4="192.168.1.101",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()
        return host

    @pytest.mark.asyncio
    async def test_handle_package_updates_success(
        self, session, mock_connection, sample_host
    ):
        """Test successful package updates update."""
        message_data = {
            "available_updates": [
                {
                    "package_name": "nginx",
                    "current_version": "1.18.0",
                    "new_version": "1.20.0",
                    "package_manager": "apt",
                    "update_type": "security",
                },
                {
                    "package_name": "python3",
                    "current_version": "3.10.0",
                    "available_version": "3.11.0",
                    "package_manager": "apt",
                    "update_type": "enhancement",
                },
            ]
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_package_updates_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "success"

        # Verify package updates were added
        updates = (
            session.query(models.PackageUpdate)
            .filter_by(host_id=mock_connection.host_id)
            .all()
        )
        assert len(updates) == 2

    @pytest.mark.asyncio
    async def test_handle_package_updates_empty_list(
        self, session, mock_connection, sample_host
    ):
        """Test package updates with empty list."""
        message_data = {"available_updates": []}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_package_updates_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "success"

    @pytest.mark.asyncio
    async def test_handle_package_updates_no_host_id(self, session):
        """Test package updates with missing host_id."""
        connection = Mock()
        connection.host_id = None
        message_data = {"available_updates": []}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_package_updates_update(
                session, connection, message_data
            )

        assert result["message_type"] == "error"


class TestHandlePackageCollection:
    """Test cases for handle_package_collection function."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection object."""
        connection = Mock()
        connection.host_id = "550e8400-e29b-41d4-a716-446655440003"
        connection.hostname = "test-host"
        return connection

    @pytest.fixture
    def sample_host(self, session):
        """Create a sample host for testing."""
        host = models.Host(
            id="550e8400-e29b-41d4-a716-446655440003",
            fqdn="test-host3.example.com",
            ipv4="192.168.1.102",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()
        return host

    @pytest.mark.asyncio
    async def test_handle_package_collection_success(
        self, session, mock_connection, sample_host
    ):
        """Test successful available package collection."""
        message_data = {
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "hostname": "test-host3.example.com",
            "total_packages": 2,
            "packages": {
                "apt": [
                    {
                        "name": "htop",
                        "version": "3.0.5",
                        "description": "Interactive process viewer",
                    },
                    {
                        "name": "vim",
                        "version": "8.2",
                        "description": "Text editor",
                    },
                ]
            },
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_package_collection(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "package_collection_result_ack"
        assert result["status"] in ["processed", "no_data"]

    @pytest.mark.asyncio
    async def test_handle_package_collection_empty(
        self, session, mock_connection, sample_host
    ):
        """Test package collection with empty list."""
        message_data = {
            "os_name": "Ubuntu",
            "os_version": "22.04",
            "packages": {},
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_package_collection(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "package_collection_result_ack"
        assert result["status"] == "no_data"

    @pytest.mark.asyncio
    async def test_handle_package_collection_no_host_id(self, session):
        """Test package collection with missing host_id."""
        connection = Mock()
        connection.host_id = None
        message_data = {"packages": {}}

        # This handler doesn't check host_id, it processes regardless
        result = await handle_package_collection(session, connection, message_data)

        assert result["message_type"] == "package_collection_result_ack"


class TestHandleThirdPartyRepositoryUpdate:
    """Test cases for handle_third_party_repository_update function."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection object."""
        connection = Mock()
        connection.host_id = "550e8400-e29b-41d4-a716-446655440004"
        connection.hostname = "test-host"
        return connection

    @pytest.fixture
    def sample_host(self, session):
        """Create a sample host for testing."""
        host = models.Host(
            id="550e8400-e29b-41d4-a716-446655440004",
            fqdn="test-host4.example.com",
            ipv4="192.168.1.103",
            active=True,
            platform="Ubuntu",
            platform_release="22.04",
            approval_status="approved",
        )
        session.add(host)
        session.commit()
        return host

    @pytest.mark.asyncio
    async def test_handle_third_party_repo_success(
        self, session, mock_connection, sample_host
    ):
        """Test successful third-party repository update."""
        message_data = {
            "repositories": [
                {
                    "name": "docker",
                    "type": "ppa",
                    "url": "https://download.docker.com/linux/ubuntu",
                    "enabled": True,
                    "file_path": "/etc/apt/sources.list.d/docker.list",
                },
                {
                    "name": "nodejs",
                    "type": "ppa",
                    "url": "https://deb.nodesource.com/node_18.x",
                    "enabled": False,
                    "file_path": "/etc/apt/sources.list.d/nodejs.list",
                },
            ]
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_third_party_repository_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "third_party_repository_update_ack"
        assert result["status"] == "processed"

        # Verify repositories were added
        repos = (
            session.query(models.ThirdPartyRepository)
            .filter_by(host_id=mock_connection.host_id)
            .all()
        )
        assert len(repos) == 2
        assert repos[0].name == "docker"
        assert repos[0].enabled is True

    @pytest.mark.asyncio
    async def test_handle_third_party_repo_empty(
        self, session, mock_connection, sample_host
    ):
        """Test third-party repository update with empty list."""
        message_data = {"repositories": []}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_third_party_repository_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "third_party_repository_update_ack"
        assert result["status"] == "processed"

    @pytest.mark.asyncio
    async def test_handle_third_party_repo_no_host_id(self, session):
        """Test third-party repository update with missing host_id."""
        connection = Mock()
        connection.host_id = None
        message_data = {"repositories": []}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_third_party_repository_update(
                session, connection, message_data
            )

        assert result["message_type"] == "error"


class TestHandleAntivirusStatusUpdate:
    """Test cases for handle_antivirus_status_update function."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock connection object."""
        connection = Mock()
        connection.host_id = "550e8400-e29b-41d4-a716-446655440005"
        connection.hostname = "test-host"
        return connection

    @pytest.fixture
    def sample_host(self, session):
        """Create a sample host for testing."""
        host = models.Host(
            id="550e8400-e29b-41d4-a716-446655440005",
            fqdn="test-host5.example.com",
            ipv4="192.168.1.104",
            active=True,
            platform="Windows",
            platform_release="10",
            approval_status="approved",
        )
        session.add(host)
        session.commit()
        return host

    @pytest.mark.asyncio
    async def test_handle_antivirus_status_new(
        self, session, mock_connection, sample_host
    ):
        """Test creating new antivirus status."""
        message_data = {
            "software_name": "Windows Defender",
            "install_path": "C:\\Program Files\\Windows Defender",
            "version": "4.18.23110.3",
            "enabled": True,
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_antivirus_status_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "antivirus_status_update_ack"
        assert result["status"] == "processed"

        # Verify antivirus status was added
        av_status = (
            session.query(models.AntivirusStatus)
            .filter_by(host_id=mock_connection.host_id)
            .first()
        )
        assert av_status is not None
        assert av_status.software_name == "Windows Defender"
        assert av_status.enabled is True

    @pytest.mark.asyncio
    async def test_handle_antivirus_status_update_existing(
        self, session, mock_connection, sample_host
    ):
        """Test updating existing antivirus status."""
        # Create existing status
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        existing = models.AntivirusStatus(
            host_id=mock_connection.host_id,
            software_name="Windows Defender",
            install_path="C:\\Program Files\\Windows Defender",
            version="4.18.0.0",
            enabled=False,
            last_updated=now,
        )
        session.add(existing)
        session.commit()

        message_data = {
            "software_name": "Windows Defender",
            "install_path": "C:\\Program Files\\Windows Defender",
            "version": "4.18.23110.3",
            "enabled": True,
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_antivirus_status_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "antivirus_status_update_ack"
        assert result["status"] == "processed"

        # Verify status was updated (handler deletes old and adds new)
        av_status = (
            session.query(models.AntivirusStatus)
            .filter_by(host_id=mock_connection.host_id)
            .first()
        )
        assert av_status.enabled is True
        assert av_status.version == "4.18.23110.3"

    @pytest.mark.asyncio
    async def test_handle_antivirus_status_no_software(
        self, session, mock_connection, sample_host
    ):
        """Test antivirus status update with no software detected."""
        message_data = {
            "software_name": None,
            "enabled": None,
        }

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_antivirus_status_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "antivirus_status_update_ack"
        assert result["status"] == "processed"

        # Verify no status was added
        av_status = (
            session.query(models.AntivirusStatus)
            .filter_by(host_id=mock_connection.host_id)
            .first()
        )
        assert av_status is None

    @pytest.mark.asyncio
    async def test_handle_antivirus_status_no_host_id(self, session):
        """Test antivirus status update with missing host_id."""
        connection = Mock()
        connection.host_id = None
        message_data = {"software_name": "Test AV"}

        with patch("backend.utils.host_validation.validate_host_id"):
            result = await handle_antivirus_status_update(
                session, connection, message_data
            )

        assert result["message_type"] == "error"
        assert "Host not registered" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_antivirus_status_database_error(
        self, session, mock_connection, sample_host
    ):
        """Test antivirus status update with database error."""
        message_data = {
            "software_name": "Test AV",
            "enabled": True,
        }

        with patch("backend.utils.host_validation.validate_host_id"), patch.object(
            session, "execute", side_effect=Exception("Database error")
        ):
            result = await handle_antivirus_status_update(
                session, mock_connection, message_data
            )

        assert result["message_type"] == "error"
        assert "Failed to process antivirus status update" in result["message"]
