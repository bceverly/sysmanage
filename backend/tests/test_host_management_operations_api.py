# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Unit tests for host operations and data updates in the SysManage host
management API.

Split from test_host_management_api.py. Covers:
- Host operations (reboot, shutdown, software refresh, packages)
- Host data updates (hardware, system info, user access, bulk)
- Host tagging (add/remove tag on host)

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
# HOST OPERATIONS TESTS
# =============================================================================


class TestHostOperations:
    """Test cases for host operations (reboot, shutdown, etc.)."""

    @pytest.mark.asyncio
    async def test_reboot_host_success(self, mock_config, mock_admin_user, mock_host):
        """Test requesting host reboot successfully."""
        from backend.api.host_operations import reboot_host

        with patch("backend.api.host_operations.db_module") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            # Tenant-routed session returns the host.
            tenant_db = MagicMock()
            tenant_db.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            mock_session = MagicMock()

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await reboot_host(
                    str(mock_host.id),
                    tenant_db=tenant_db,
                    current_user=mock_admin_user,
                )

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_reboot_host_without_permission(
        self, mock_config, mock_user, mock_host
    ):
        """Test reboot host without REBOOT_HOST permission."""
        from backend.api.host_operations import reboot_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.host_operations.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            tenant_db = MagicMock()

            with patch("backend.api.host_operations.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    MagicMock()
                )

                with pytest.raises(HTTPException) as exc_info:
                    await reboot_host(
                        str(mock_host.id),
                        tenant_db=tenant_db,
                        current_user=mock_user,
                    )

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_shutdown_host_success(self, mock_config, mock_admin_user, mock_host):
        """Test requesting host shutdown successfully."""
        from backend.api.host_operations import shutdown_host

        with patch("backend.api.host_operations.db_module") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            tenant_db = MagicMock()
            tenant_db.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            mock_session = MagicMock()

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await shutdown_host(
                    str(mock_host.id),
                    tenant_db=tenant_db,
                    current_user=mock_admin_user,
                )

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_host_without_permission(
        self, mock_config, mock_user, mock_host
    ):
        """Test shutdown host without SHUTDOWN_HOST permission."""
        from backend.api.host_operations import shutdown_host

        mock_user.has_role = MagicMock(return_value=False)

        with patch("backend.api.host_operations.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            tenant_db = MagicMock()

            with patch("backend.api.host_operations.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    MagicMock()
                )

                with pytest.raises(HTTPException) as exc_info:
                    await shutdown_host(
                        str(mock_host.id),
                        tenant_db=tenant_db,
                        current_user=mock_user,
                    )

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_refresh_host_software_success(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test requesting software inventory refresh successfully."""
        from backend.api.host_operations import refresh_host_software

        with patch("backend.api.host_operations.db_module") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            tenant_db = MagicMock()
            tenant_db.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            mock_session = MagicMock()

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await refresh_host_software(
                    str(mock_host.id),
                    tenant_db=tenant_db,
                    current_user=mock_admin_user,
                )

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_packages_success(
        self, mock_config, mock_admin_user, mock_host
    ):
        """Test requesting package collection successfully."""
        from backend.api.host_operations import request_packages

        with patch("backend.api.host_operations.db_module") as mock_db, patch(
            "backend.api.host_operations.queue_ops"
        ) as mock_queue:
            mock_db.get_engine.return_value = MagicMock()

            tenant_db = MagicMock()
            tenant_db.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            mock_session = MagicMock()

            with patch(
                "backend.api.host_operations.sessionmaker"
            ) as mock_sessionmaker, patch("backend.api.host_operations.AuditService"):
                mock_sessionmaker.return_value = create_mock_session_context(
                    mock_session
                )

                result = await request_packages(
                    str(mock_host.id),
                    tenant_db=tenant_db,
                    current_user=mock_admin_user,
                )

                assert result["result"] is True
                mock_queue.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_operations_host_not_found(self, mock_config, mock_admin_user):
        """Test operations on non-existent host."""
        from backend.api.host_operations import reboot_host

        with patch("backend.api.host_operations.db_module") as mock_db:
            mock_db.get_engine.return_value = MagicMock()

            tenant_db = MagicMock()
            tenant_db.query.return_value.filter.return_value.first.return_value = (
                None  # Host not found
            )

            with patch("backend.api.host_operations.sessionmaker") as mock_sessionmaker:
                mock_sessionmaker.return_value = create_mock_session_context(
                    MagicMock()
                )

                with pytest.raises(HTTPException) as exc_info:
                    await reboot_host(
                        str(uuid.uuid4()),
                        tenant_db=tenant_db,
                        current_user=mock_admin_user,
                    )

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

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch(
            "backend.api.host_data_updates.request_sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(mock_session)

            result = await update_host_hardware(str(mock_host.id), hardware_data)

            assert result["result"] is True
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_host_hardware_not_found(self, mock_config):
        """Test updating hardware for non-existent host."""
        from backend.api.host_data_updates import update_host_hardware

        hardware_data = {"cpu_vendor": "Intel"}

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.api.host_data_updates.request_sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value = create_mock_session_context(mock_session)

            with pytest.raises(HTTPException) as exc_info:
                await update_host_hardware(str(uuid.uuid4()), hardware_data)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_request_hardware_update_success(self, mock_config, mock_host):
        """Test requesting hardware update successfully."""
        from backend.api.host_data_updates import request_hardware_update

        with patch("backend.api.host_data_updates.queue_ops") as mock_queue:

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch(
                "backend.api.host_data_updates.request_sessionmaker"
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

        with patch("backend.api.host_data_updates.queue_ops") as mock_queue:

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch(
                "backend.api.host_data_updates.request_sessionmaker"
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

        with patch("backend.api.host_data_updates.queue_ops") as mock_queue:

            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_host
            )

            with patch(
                "backend.api.host_data_updates.request_sessionmaker"
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

        with patch("backend.api.host_data_updates.queue_ops") as mock_queue:

            # Phase 6 N+1 audit refactored ``request_hardware_update_bulk``
            # to bulk-fetch via ``.filter(Host.id.in_(host_ids)).all()``
            # and dict-lookup per id, instead of one ``.first()`` per
            # host.  Mock ``.all()`` with only the host that "exists" —
            # the missing id is reported as not-found by the dict
            # ``.get()`` returning ``None``.
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_host,
            ]

            with patch(
                "backend.api.host_data_updates.request_sessionmaker"
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
            "backend.api.tag.get_tenant_db"
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
                    str(mock_host.id), str(mock_tag.id), mock_db, mock_admin_user
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
            "backend.api.tag.get_tenant_db"
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
                        str(mock_host.id), str(mock_tag.id), mock_db, mock_user
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
            "backend.api.tag.get_tenant_db"
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
                    str(mock_host.id), str(mock_tag.id), mock_db, mock_admin_user
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
            "backend.api.tag.get_tenant_db"
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
                        mock_admin_user,
                    )

                assert exc_info.value.status_code == 404
