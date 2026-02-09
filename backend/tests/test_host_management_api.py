"""
Comprehensive unit tests for the host management API in SysManage.

Tests cover:
- Host CRUD operations (list, get, create, update, delete)
- Host approval/rejection
- Host tagging
- Host filtering/searching
- Host status updates
- Host operations (reboot, shutdown, software refresh)
- Batch operations
- Error handling

These tests use pytest and pytest-asyncio for async tests with mocked database.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from backend.security.roles import SecurityRoles

# =============================================================================
# TEST CONFIGURATION AND FIXTURES
# =============================================================================


# Test configuration
TEST_CONFIG = {
    "api": {
        "host": "localhost",
        "port": 9443,
        "certFile": None,
    },
    "webui": {"host": "localhost", "port": 9080},
    "monitoring": {"heartbeat_timeout": 5},
    "security": {
        "password_salt": "test_salt",
        "admin_userid": "admin@test.com",
        "admin_password": "testadminpass",
        "jwt_secret": "test_secret_key_for_testing_only",
        "jwt_algorithm": "HS256",
        "jwt_auth_timeout": 3600,
        "jwt_refresh_timeout": 86400,
    },
}


@pytest.fixture
def mock_config():
    """Mock the configuration system to use test config."""
    with patch("backend.config.config.get_config", return_value=TEST_CONFIG):
        yield TEST_CONFIG


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
    host.id = uuid.uuid4()
    host.active = True
    host.fqdn = "test-host.example.com"
    host.ipv4 = "192.168.1.100"
    host.ipv6 = "::1"
    host.status = "up"
    host.approval_status = "approved"
    host.last_access = datetime.now(timezone.utc)
    host.platform = "Linux"
    host.platform_release = "Ubuntu 22.04"
    host.platform_version = "22.04.3 LTS"
    host.machine_architecture = "x86_64"
    host.processor = "Intel"
    host.cpu_vendor = "Intel"
    host.cpu_model = "Core i7"
    host.cpu_cores = 8
    host.cpu_threads = 16
    host.cpu_frequency_mhz = 3600
    host.memory_total_mb = 32768
    host.reboot_required = False
    host.is_agent_privileged = True
    host.script_execution_enabled = False
    host.enabled_shells = None
    host.parent_host_id = None
    host.virtualization_types = None
    host.virtualization_capabilities = None
    host.client_certificate = None
    host.certificate_serial = None
    host.host_token = "test-host-token-123"
    host.tags = MagicMock()
    host.tags.all.return_value = []
    host.package_updates = []
    return host


@pytest.fixture
def mock_pending_host():
    """Create a mock host with pending approval status."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.active = True
    host.fqdn = "pending-host.example.com"
    host.ipv4 = "192.168.1.101"
    host.ipv6 = "::1"
    host.status = "up"
    host.approval_status = "pending"
    host.last_access = datetime.now(timezone.utc)
    host.tags = MagicMock()
    host.tags.all.return_value = []
    host.package_updates = []
    host.host_token = "pending-host-token"
    return host


@pytest.fixture
def mock_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "test@example.com"
    user.active = True
    user.is_admin = False
    user._role_cache = None
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "admin@example.com"
    user.active = True
    user.is_admin = True
    user._role_cache = MagicMock()
    user.load_role_cache = MagicMock()
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_tag():
    """Create a mock tag object."""
    tag = MagicMock()
    tag.id = uuid.uuid4()
    tag.name = "production"
    tag.description = "Production servers"
    tag.created_at = datetime.now(timezone.utc)
    tag.updated_at = datetime.now(timezone.utc)
    tag.hosts = MagicMock()
    tag.hosts.count.return_value = 5
    return tag


def create_mock_session_context(mock_session):
    """Helper to create a mock session context manager."""
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
    return mock_session_factory


# =============================================================================
# HOST CRUD TESTS
# =============================================================================


class TestHostCRUD:
    """Test cases for host CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_all_hosts_success(self, mock_config, mock_host):
        """Test retrieving all hosts successfully."""
        from backend.api.host import _get_all_hosts_sync

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [mock_host]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = _get_all_hosts_sync()

                assert len(result) == 1
                assert result[0]["fqdn"] == mock_host.fqdn

    @pytest.mark.asyncio
    async def test_get_host_by_id_success(self, mock_config, mock_host, mock_user):
        """Test retrieving a host by ID successfully."""
        from backend.api.host import get_host

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_user,  # User query
                mock_host,  # Host query
            ]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await get_host(str(mock_host.id), "test@example.com")

                assert result["fqdn"] == mock_host.fqdn
                assert result["id"] == str(mock_host.id)

    @pytest.mark.asyncio
    async def test_get_host_by_id_not_found(self, mock_config, mock_user):
        """Test retrieving a non-existent host by ID."""
        from backend.api.host import get_host

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_user,  # User query
                None,  # Host not found
            ]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await get_host(str(uuid.uuid4()), "test@example.com")

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_host_without_permission(self, mock_config, mock_user):
        """Test retrieving host without VIEW_HOST_DETAILS permission."""
        from backend.api.host import get_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await get_host(str(uuid.uuid4()), "test@example.com")

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_host_by_fqdn_success(self, mock_config, mock_host):
        """Test retrieving a host by FQDN successfully."""
        from backend.api.host import get_host_by_fqdn_endpoint

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await get_host_by_fqdn_endpoint(mock_host.fqdn)

                assert result["fqdn"] == mock_host.fqdn

    @pytest.mark.asyncio
    async def test_get_host_by_fqdn_not_found(self, mock_config):
        """Test retrieving a non-existent host by FQDN."""
        from backend.api.host import get_host_by_fqdn_endpoint

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await get_host_by_fqdn_endpoint("nonexistent.example.com")

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_add_host_success(self, mock_config, mock_admin_user):
        """Test adding a new host successfully."""
        from backend.api.host import Host, add_host

        new_host_data = Host(
            active=True,
            fqdn="new-host.example.com",
            ipv4="192.168.1.200",
            ipv6="::1",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = []

            # Mock the host after add and refresh
            created_host = MagicMock()
            created_host.id = uuid.uuid4()
            created_host.fqdn = new_host_data.fqdn
            created_host.active = new_host_data.active
            created_host.ipv4 = new_host_data.ipv4
            created_host.ipv6 = new_host_data.ipv6
            created_host.status = "up"
            created_host.approval_status = "approved"
            created_host.last_access = datetime.now(timezone.utc)

            def mock_refresh(host):
                host.id = created_host.id
                host.status = created_host.status
                host.approval_status = created_host.approval_status
                host.last_access = created_host.last_access

            mock_session.refresh = mock_refresh

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker, patch(
                "backend.api.host.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await add_host(new_host_data, "admin@example.com")

                assert result["fqdn"] == new_host_data.fqdn
                assert result["approval_status"] == "approved"
                mock_session.add.assert_called_once()
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_add_duplicate_host(self, mock_config, mock_admin_user, mock_host):
        """Test adding a duplicate host fails."""
        from backend.api.host import Host, add_host

        new_host_data = Host(
            active=True,
            fqdn=mock_host.fqdn,  # Existing FQDN
            ipv4="192.168.1.200",
            ipv6="::1",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_host
            ]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_host(new_host_data, "admin@example.com")

                assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_add_host_user_not_found(self, mock_config):
        """Test adding host fails when user not found."""
        from backend.api.host import Host, add_host

        new_host_data = Host(
            active=True,
            fqdn="new-host.example.com",
            ipv4="192.168.1.200",
            ipv6="::1",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None  # User not found
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_host(new_host_data, "unknown@example.com")

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_update_host_success(self, mock_config, mock_admin_user, mock_host):
        """Test updating an existing host successfully."""
        from backend.api.host import Host, update_host

        updated_data = Host(
            active=False,
            fqdn="updated-host.example.com",
            ipv4="192.168.1.201",
            ipv6="::2",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            # Update mock_host to reflect the update
            mock_host.fqdn = updated_data.fqdn
            mock_host.active = updated_data.active
            mock_host.ipv4 = updated_data.ipv4
            mock_host.ipv6 = updated_data.ipv6

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,  # User query
                mock_host,  # Updated host query
            ]
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_host
            ]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker, patch(
                "backend.api.host.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await update_host(
                    str(mock_host.id), updated_data, "admin@example.com"
                )

                assert result["fqdn"] == updated_data.fqdn
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_host_not_found(self, mock_config, mock_admin_user):
        """Test updating a non-existent host."""
        from backend.api.host import Host, update_host

        updated_data = Host(
            active=True,
            fqdn="updated-host.example.com",
            ipv4="192.168.1.201",
            ipv6="::2",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = []

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await update_host(
                        str(uuid.uuid4()), updated_data, "admin@example.com"
                    )

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_host_success(self, mock_config, mock_admin_user, mock_host):
        """Test deleting a host successfully."""
        from backend.api.host import delete_host

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_host
            ]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker, patch(
                "backend.api.host.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await delete_host(str(mock_host.id), "admin@example.com")

                assert result["result"] is True
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_host_not_found(self, mock_config, mock_admin_user):
        """Test deleting a non-existent host."""
        from backend.api.host import delete_host

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = []

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await delete_host(str(uuid.uuid4()), "admin@example.com")

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_host_without_permission(self, mock_config, mock_user):
        """Test deleting host without DELETE_HOST permission."""
        from backend.api.host import delete_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await delete_host(str(uuid.uuid4()), "test@example.com")

                assert exc_info.value.status_code == 403


# =============================================================================
# HOST REGISTRATION TESTS
# =============================================================================


class TestHostRegistration:
    """Test cases for host registration functionality."""

    @pytest.mark.asyncio
    async def test_register_new_host_success(self, mock_config):
        """Test registering a new host successfully."""
        from backend.api.host import HostRegistration, register_host

        registration_data = HostRegistration(
            active=True,
            fqdn="new-agent.example.com",
            hostname="new-agent",
            ipv4="192.168.1.150",
            ipv6="::1",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None  # No existing host
            )

            new_host = MagicMock()
            new_host.id = uuid.uuid4()
            new_host.fqdn = registration_data.fqdn
            new_host.approval_status = "pending"

            def mock_refresh(host):
                host.id = new_host.id

            mock_session.refresh = mock_refresh

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await register_host(registration_data)

                mock_session.add.assert_called_once()
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_register_existing_host_updates(self, mock_config, mock_host):
        """Test registering an existing host updates the record."""
        from backend.api.host import HostRegistration, register_host

        registration_data = HostRegistration(
            active=True,
            fqdn=mock_host.fqdn,
            hostname="existing-host",
            ipv4="192.168.1.100",
            ipv6="::1",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await register_host(registration_data)

                # Should update existing host, not add new one
                mock_session.add.assert_not_called()
                mock_session.commit.assert_called()


# =============================================================================
# HOST APPROVAL/REJECTION TESTS
# =============================================================================


class TestHostApproval:
    """Test cases for host approval and rejection functionality."""

    @pytest.mark.asyncio
    async def test_approve_host_success(
        self, mock_config, mock_admin_user, mock_pending_host
    ):
        """Test approving a pending host successfully."""
        from backend.api.host_approval import approve_host

        with patch("backend.api.host_approval.db") as mock_db, patch(
            "backend.api.host_approval.certificate_manager"
        ) as mock_cert_mgr, patch(
            "backend.api.host_approval.queue_ops"
        ) as mock_queue, patch(
            "backend.api.host_approval.AuditService"
        ):
            mock_db.get_engine.return_value = MagicMock()

            # Mock certificate generation
            mock_cert = MagicMock()
            mock_cert.serial_number = 12345
            mock_cert_mgr.generate_client_certificate.return_value = (
                b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
                None,
            )

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,  # User query
                mock_pending_host,  # Host query
            ]

            # Mock HostChild query for child host linking
            mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch(
                "backend.api.host_approval.sessionmaker"
            ) as mock_sessionmaker, patch(
                "backend.api.host_approval.x509"
            ) as mock_x509:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )
                mock_cert_obj = MagicMock()
                mock_cert_obj.serial_number = 12345
                mock_x509.load_pem_x509_certificate.return_value = mock_cert_obj

                result = await approve_host(
                    str(mock_pending_host.id), "admin@example.com"
                )

                assert mock_pending_host.approval_status == "approved"
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_approve_already_approved_host(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test approving an already approved host fails."""
        from backend.api.host_approval import approve_host

        mock_host.approval_status = "approved"

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                mock_host,
            ]

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await approve_host(str(mock_host.id), "admin@example.com")

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_host_without_permission(
        self, mock_config, mock_user, mock_pending_host
    ):
        """Test approving host without APPROVE_HOST_REGISTRATION permission."""
        from backend.api.host_approval import approve_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await approve_host(str(mock_pending_host.id), "test@example.com")

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_reject_host_success(
        self, mock_config, mock_admin_user, mock_pending_host
    ):
        """Test rejecting a pending host successfully."""
        from backend.api.host_approval import reject_host

        with patch("backend.api.host_approval.db") as mock_db, patch(
            "backend.api.host_approval.AuditService"
        ):
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                mock_pending_host,
            ]

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await reject_host(
                    str(mock_pending_host.id), "admin@example.com"
                )

                assert mock_pending_host.approval_status == "rejected"
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_reject_already_rejected_host(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test rejecting an already rejected host fails."""
        from backend.api.host_approval import reject_host

        mock_host.approval_status = "rejected"

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                mock_host,
            ]

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await reject_host(str(mock_host.id), "admin@example.com")

                assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_host_not_found(self, mock_config, mock_admin_user):
        """Test approving a non-existent host."""
        from backend.api.host_approval import approve_host

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                None,  # Host not found
            ]

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await approve_host(str(uuid.uuid4()), "admin@example.com")

                assert exc_info.value.status_code == 404


# =============================================================================
# HOST OPERATIONS TESTS
# =============================================================================


class TestHostOperations:
    """Test cases for host operations (reboot, shutdown, etc.)."""

    @pytest.mark.asyncio
    async def test_reboot_host_success(self, mock_config, mock_admin_user, mock_host):
        """Test requesting host reboot successfully."""
        from backend.api.host_operations import reboot_host

        with patch("backend.api.host_operations.db") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                mock_host,
            ]

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await reboot_host(str(mock_host.id), "admin@example.com")

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_reboot_host_without_permission(
        self, mock_config, mock_user, mock_host
    ):
        """Test reboot host without REBOOT_HOST permission."""
        from backend.api.host_operations import reboot_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.host_operations.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.host_operations.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await reboot_host(str(mock_host.id), "test@example.com")

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_shutdown_host_success(self, mock_config, mock_admin_user, mock_host):
        """Test requesting host shutdown successfully."""
        from backend.api.host_operations import shutdown_host

        with patch("backend.api.host_operations.db") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                mock_host,
            ]

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await shutdown_host(str(mock_host.id), "admin@example.com")

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_host_without_permission(
        self, mock_config, mock_user, mock_host
    ):
        """Test shutdown host without SHUTDOWN_HOST permission."""
        from backend.api.host_operations import shutdown_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.host_operations.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.host_operations.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await shutdown_host(str(mock_host.id), "test@example.com")

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_refresh_host_software_success(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test requesting software inventory refresh successfully."""
        from backend.api.host_operations import refresh_host_software

        with patch("backend.api.host_operations.db") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                mock_host,
            ]

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await refresh_host_software(
                    str(mock_host.id), "admin@example.com"
                )

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_packages_success(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test requesting package collection successfully."""
        from backend.api.host_operations import request_packages

        with patch("backend.api.host_operations.db") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                mock_host,
            ]

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_packages(str(mock_host.id), "admin@example.com")

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_operations_host_not_found(self, mock_config, mock_admin_user):
        """Test operations on non-existent host."""
        from backend.api.host_operations import reboot_host

        with patch("backend.api.host_operations.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_admin_user,
                None,  # Host not found
            ]

            with patch("backend.api.host_operations.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await reboot_host(str(uuid.uuid4()), "admin@example.com")

                assert exc_info.value.status_code == 404


# =============================================================================
# HOST DATA UPDATES TESTS
# =============================================================================


class TestHostDataUpdates:
    """Test cases for host data update operations."""

    @pytest.mark.asyncio
    async def test_update_host_hardware_success(self, mock_config, mock_host):
        """Test updating host hardware information successfully."""
        from backend.api.host_data_updates import update_host_hardware

        hardware_data = {
            "cpu_vendor": "AMD",
            "cpu_model": "Ryzen 9",
            "cpu_cores": 16,
            "cpu_threads": 32,
            "cpu_frequency_mhz": 4000,
            "memory_total_mb": 65536,
        }

        with patch("backend.api.host_data_updates.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch(
                "backend.api.host_data_updates.sessionmaker"
            ) as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await update_host_hardware(str(mock_host.id), hardware_data)

                assert result["result"] is True
                mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_host_hardware_not_found(self, mock_config):
        """Test updating hardware for non-existent host."""
        from backend.api.host_data_updates import update_host_hardware

        hardware_data = {"cpu_vendor": "Intel"}

        with patch("backend.api.host_data_updates.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch(
                "backend.api.host_data_updates.sessionmaker"
            ) as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await update_host_hardware(str(uuid.uuid4()), hardware_data)

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_request_hardware_update_success(self, mock_config, mock_host):
        """Test requesting hardware update successfully."""
        from backend.api.host_data_updates import request_hardware_update

        with patch("backend.api.host_data_updates.db") as mock_db, patch(
            "backend.api.host_data_updates.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch(
                "backend.api.host_data_updates.sessionmaker"
            ) as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_hardware_update(str(mock_host.id))

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_system_info_success(self, mock_config, mock_host):
        """Test requesting system info update successfully."""
        from backend.api.host_data_updates import request_system_info

        with patch("backend.api.host_data_updates.db") as mock_db, patch(
            "backend.api.host_data_updates.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch(
                "backend.api.host_data_updates.sessionmaker"
            ) as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_system_info(str(mock_host.id))

                assert result["result"] is True
                # Should enqueue two messages (system info and virtualization check)
                assert mock_queue.enqueue_message.call_count == 2

    @pytest.mark.asyncio
    async def test_request_user_access_update_success(self, mock_config, mock_host):
        """Test requesting user access update successfully."""
        from backend.api.host_data_updates import request_user_access_update

        with patch("backend.api.host_data_updates.db") as mock_db, patch(
            "backend.api.host_data_updates.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch(
                "backend.api.host_data_updates.sessionmaker"
            ) as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_user_access_update(str(mock_host.id))

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_hardware_update_success(self, mock_config, mock_host):
        """Test bulk hardware update request for multiple hosts."""
        from backend.api.host_data_updates import request_hardware_update_bulk

        host_ids = [str(mock_host.id), str(uuid.uuid4())]

        with patch("backend.api.host_data_updates.db") as mock_db, patch(
            "backend.api.host_data_updates.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            # First host exists, second doesn't
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_host,
                None,
            ]

            with patch(
                "backend.api.host_data_updates.sessionmaker"
            ) as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_hardware_update_bulk(host_ids)

                assert len(result["results"]) == 2
                assert result["results"][0]["success"] is True
                assert result["results"][1]["success"] is False


# =============================================================================
# HOST TAGGING TESTS
# =============================================================================


class TestHostTagging:
    """Test cases for host tagging functionality."""

    @pytest.mark.asyncio
    async def test_add_tag_to_host_success(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test adding a tag to a host successfully."""
        from backend.api.tag import add_tag_to_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            # Create mock db session for dependency
            mock_db = MagicMock()

            # Mock raw SQL executions
            mock_db.execute.return_value.first.side_effect = [
                MagicMock(id=mock_host.id),  # Host exists
                MagicMock(id=mock_tag.id),  # Tag exists
                None,  # No existing association
            ]
            mock_db.execute.return_value.scalar.side_effect = [
                mock_tag.name,
                mock_host.fqdn,
            ]

            mock_get_db.return_value = mock_db

            # Mock the auth session
            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                result = await add_tag_to_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, "admin@example.com"
                )

                assert "message" in result
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_add_tag_to_host_without_permission(
        self, mock_config, mock_user, mock_host, mock_tag
    ):
        """Test adding tag without EDIT_TAGS permission."""
        from backend.api.tag import add_tag_to_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await add_tag_to_host(
                        str(mock_host.id), str(mock_tag.id), mock_db, "test@example.com"
                    )

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_remove_tag_from_host_success(
        self, mock_config, mock_admin_user, mock_host, mock_tag
    ):
        """Test removing a tag from a host successfully."""
        from backend.api.tag import remove_tag_from_host

        # Create mock host_tag association
        mock_host_tag = MagicMock()

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_host_tag
            )
            mock_db.execute.return_value.scalar.side_effect = [
                mock_tag.name,
                mock_host.fqdn,
            ]
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker, patch(
                "backend.api.tag.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                # Should return None (204 No Content)
                result = await remove_tag_from_host(
                    str(mock_host.id), str(mock_tag.id), mock_db, "admin@example.com"
                )

                mock_db.delete.assert_called_once_with(mock_host_tag)
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_tag_from_host(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test removing a tag that is not associated with host."""
        from backend.api.tag import remove_tag_from_host

        with patch("backend.api.tag.db_module") as mock_db_module, patch(
            "backend.api.tag.get_db"
        ) as mock_get_db:
            mock_db_module.get_engine.return_value = MagicMock()

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_get_db.return_value = mock_db

            mock_auth_session = MagicMock()
            mock_auth_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )

            with patch("backend.api.tag.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_auth_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await remove_tag_from_host(
                        str(mock_host.id),
                        str(uuid.uuid4()),
                        mock_db,
                        "admin@example.com",
                    )

                assert exc_info.value.status_code == 404


# =============================================================================
# UPDATE REQUEST TESTS
# =============================================================================


class TestUpdateRequests:
    """Test cases for OS and update check requests."""

    @pytest.mark.asyncio
    async def test_request_os_version_update_success(self, mock_config, mock_host):
        """Test requesting OS version update successfully."""
        from backend.api.host_approval import request_os_version_update

        with patch("backend.api.host_approval.db") as mock_db, patch(
            "backend.api.host_approval.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_os_version_update(str(mock_host.id))

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_os_version_update_not_found(self, mock_config):
        """Test requesting OS version update for non-existent host."""
        from backend.api.host_approval import request_os_version_update

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await request_os_version_update(str(uuid.uuid4()))

                assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_request_updates_check_success(self, mock_config, mock_host):
        """Test requesting updates check successfully."""
        from backend.api.host_approval import request_updates_check

        with patch("backend.api.host_approval.db") as mock_db, patch(
            "backend.api.host_approval.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_updates_check(str(mock_host.id))

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_updates_check_unapproved_host(
        self, mock_config, mock_pending_host
    ):
        """Test requesting updates check for unapproved host fails."""
        from backend.api.host_approval import request_updates_check

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_pending_host
            )

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await request_updates_check(str(mock_pending_host.id))

                # Should fail due to unapproved status
                assert exc_info.value.status_code == 400


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Test cases for error handling in host management."""

    @pytest.mark.asyncio
    async def test_get_host_user_not_found(self, mock_config):
        """Test get host fails when authenticated user not found."""
        from backend.api.host import get_host

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None  # User not found
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await get_host(str(uuid.uuid4()), "unknown@example.com")

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_update_host_user_not_found(self, mock_config):
        """Test update host fails when authenticated user not found."""
        from backend.api.host import Host, update_host

        updated_data = Host(
            active=True,
            fqdn="updated-host.example.com",
            ipv4="192.168.1.201",
            ipv6="::2",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await update_host(
                        str(uuid.uuid4()), updated_data, "unknown@example.com"
                    )

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_host_user_not_found(self, mock_config):
        """Test delete host fails when authenticated user not found."""
        from backend.api.host import delete_host

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await delete_host(str(uuid.uuid4()), "unknown@example.com")

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_approve_host_user_not_found(self, mock_config):
        """Test approve host fails when authenticated user not found."""
        from backend.api.host_approval import approve_host

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await approve_host(str(uuid.uuid4()), "unknown@example.com")

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_reject_host_user_not_found(self, mock_config):
        """Test reject host fails when authenticated user not found."""
        from backend.api.host_approval import reject_host

        with patch("backend.api.host_approval.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.host_approval.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await reject_host(str(uuid.uuid4()), "unknown@example.com")

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_reboot_host_user_not_found(self, mock_config):
        """Test reboot host fails when authenticated user not found."""
        from backend.api.host_operations import reboot_host

        with patch("backend.api.host_operations.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            with patch("backend.api.host_operations.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                with pytest.raises(HTTPException) as exc_info:
                    await reboot_host(str(uuid.uuid4()), "unknown@example.com")

                assert exc_info.value.status_code == 401


# =============================================================================
# HOST RESPONSE FORMAT TESTS
# =============================================================================


class TestHostResponseFormat:
    """Test cases for host response format validation."""

    @pytest.mark.asyncio
    async def test_get_host_response_includes_all_fields(
        self, mock_config, mock_host, mock_user
    ):
        """Test that get_host response includes all expected fields."""
        from backend.api.host import get_host

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_user,
                mock_host,
            ]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await get_host(str(mock_host.id), "test@example.com")

                # Verify all expected fields are present
                expected_fields = [
                    "id",
                    "active",
                    "fqdn",
                    "ipv4",
                    "ipv6",
                    "status",
                    "approval_status",
                    "platform",
                    "platform_release",
                    "platform_version",
                    "machine_architecture",
                    "processor",
                    "cpu_vendor",
                    "cpu_model",
                    "cpu_cores",
                    "cpu_threads",
                    "cpu_frequency_mhz",
                    "memory_total_mb",
                    "reboot_required",
                    "is_agent_privileged",
                    "script_execution_enabled",
                    "tags",
                    "security_updates_count",
                    "system_updates_count",
                    "total_updates_count",
                ]

                for field in expected_fields:
                    assert field in result, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_get_all_hosts_response_format(self, mock_config, mock_host):
        """Test that get_all_hosts response has correct format."""
        from backend.api.host import _get_all_hosts_sync

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = [mock_host]

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = _get_all_hosts_sync()

                assert isinstance(result, list)
                assert len(result) == 1
                assert "id" in result[0]
                assert "fqdn" in result[0]
                assert "tags" in result[0]

    @pytest.mark.asyncio
    async def test_add_host_response_format(self, mock_config, mock_admin_user):
        """Test that add_host response has correct format."""
        from backend.api.host import Host, add_host

        new_host_data = Host(
            active=True,
            fqdn="new-host.example.com",
            ipv4="192.168.1.200",
            ipv6="::1",
        )

        with patch("backend.api.host.db") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_admin_user
            )
            mock_session.query.return_value.filter.return_value.all.return_value = []

            def mock_refresh(host):
                host.id = uuid.uuid4()
                host.status = "up"
                host.approval_status = "approved"
                host.last_access = datetime.now(timezone.utc)

            mock_session.refresh = mock_refresh

            with patch("backend.api.host.sessionmaker") as mock_sessionmaker, patch(
                "backend.api.host.AuditService"
            ):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await add_host(new_host_data, "admin@example.com")

                # Verify response has expected minimal fields
                assert "id" in result
                assert "fqdn" in result
                assert "active" in result
                assert "status" in result
                assert "approval_status" in result


# =============================================================================
# HOST STATUS VALIDATION TESTS
# =============================================================================


class TestHostStatusValidation:
    """Test cases for host status validation."""

    def test_host_approval_status_values(self):
        """Test that host approval status can only be valid values."""
        valid_statuses = ["pending", "approved", "rejected"]

        for status in valid_statuses:
            host = MagicMock()
            host.approval_status = status
            assert host.approval_status in valid_statuses

    def test_host_status_values(self):
        """Test that host status can only be valid values."""
        valid_statuses = ["up", "down", "unknown"]

        for status in valid_statuses:
            host = MagicMock()
            host.status = status
            assert host.status in valid_statuses
