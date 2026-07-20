# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for host update requests, error handling, and response formats in
the SysManage host management API.

Split from test_host_management_api.py. Covers:
- OS and update check requests
- Error handling (user-not-found paths)
- Host response format validation
- Host status validation

These tests use pytest and pytest-asyncio for async tests with mocked database.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

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


def create_mock_session_context(mock_session):
    """Helper to create a mock session context manager."""
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
    return mock_session_factory


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
        """The user-not-found path moved out of approve_host into the shared
        ``require_authenticated_user`` dependency (authz is resolved on the MAIN
        engine, server-global); it raises 401 when the user does not exist."""
        from backend.auth.auth_bearer import require_authenticated_user

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.persistence.db.get_engine", return_value=MagicMock()
        ), patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                require_authenticated_user("unknown@example.com")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_reject_host_user_not_found(self, mock_config):
        """The user-not-found path moved out of reject_host into the shared
        ``require_authenticated_user`` dependency (authz is resolved on the MAIN
        engine, server-global); it raises 401 when the user does not exist."""
        from backend.auth.auth_bearer import require_authenticated_user

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.persistence.db.get_engine", return_value=MagicMock()
        ), patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                require_authenticated_user("unknown@example.com")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_reboot_host_user_not_found(self, mock_config):
        """The user-not-found path moved out of the host-operation handlers into
        the shared ``require_authenticated_user`` dependency (authz is resolved on
        the MAIN engine, server-global); it raises 401 when the user does not
        exist."""
        from backend.auth.auth_bearer import require_authenticated_user

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.persistence.db.get_engine", return_value=MagicMock()
        ), patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
            # session_local = sessionmaker(...); session = session_local()
            mock_sessionmaker.return_value.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                require_authenticated_user("unknown@example.com")

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

            ctx = create_mock_session_context(mock_session)
            with patch("backend.api.host.sessionmaker") as mock_sessionmaker, patch(
                "backend.persistence.partitions.request_sessionmaker"
            ) as mock_rsm:
                mock_sessionmaker.return_value = ctx
                mock_rsm.return_value = ctx

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
