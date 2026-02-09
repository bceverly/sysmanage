"""
Comprehensive API endpoint tests for child host management.

This module tests the FastAPI endpoints with proper mocking:
- Child host CRUD endpoints
- VM lifecycle endpoints (start, stop, restart)
- Virtualization status and enablement endpoints
- Distribution management endpoints
- Error responses and edge cases
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# =============================================================================
# MOCK FIXTURES
# =============================================================================


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


@pytest.fixture
def mock_queue_ops():
    """Create a mock queue operations."""
    mock = MagicMock()
    mock.enqueue_message = MagicMock()
    return mock


@pytest.fixture
def mock_user():
    """Create a mock user with roles."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.userid = "admin@sysmanage.org"
    user._role_cache = MagicMock()
    user._role_cache.has_role.return_value = True
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_host():
    """Create a mock host."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "testhost.example.com"
    host.active = True
    host.platform = "Linux"
    host.is_agent_privileged = True
    return host


@pytest.fixture
def mock_windows_host():
    """Create a mock Windows host."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "windowshost.example.com"
    host.active = True
    host.platform = "Windows"
    host.is_agent_privileged = True
    host.reboot_required = False
    host.reboot_required_reason = None
    host.virtualization_capabilities = None
    host.virtualization_types = None
    return host


@pytest.fixture
def mock_openbsd_host():
    """Create a mock OpenBSD host."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "openbsdhost.example.com"
    host.active = True
    host.platform = "OpenBSD"
    host.is_agent_privileged = True
    return host


@pytest.fixture
def mock_freebsd_host():
    """Create a mock FreeBSD host."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "freebsdhost.example.com"
    host.active = True
    host.platform = "FreeBSD"
    host.is_agent_privileged = True
    return host


@pytest.fixture
def mock_child_host():
    """Create a mock child host."""
    child = MagicMock()
    child.id = uuid.uuid4()
    child.parent_host_id = uuid.uuid4()
    child.child_host_id = None
    child.child_name = "test-vm"
    child.child_type = "kvm"
    child.distribution = "Debian"
    child.distribution_version = "12"
    child.hostname = "test-vm.local"
    child.status = "running"
    child.installation_step = None
    child.error_message = None
    child.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    child.installed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    child.wsl_guid = None
    return child


@pytest.fixture
def mock_distribution():
    """Create a mock distribution."""
    dist = MagicMock()
    dist.id = uuid.uuid4()
    dist.child_type = "lxd"
    dist.distribution_name = "Ubuntu"
    dist.distribution_version = "22.04"
    dist.display_name = "Ubuntu 22.04 LTS"
    dist.install_identifier = "ubuntu:22.04"
    dist.executable_name = None
    dist.agent_install_method = "apt_launchpad"
    dist.agent_install_commands = json.dumps(
        ["apt update", "apt install sysmanage-agent"]
    )
    dist.is_active = True
    dist.min_agent_version = None
    dist.notes = None
    dist.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    dist.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return dist


# =============================================================================
# CHILD HOST UTILS TESTS
# =============================================================================


class TestChildHostUtils:
    """Tests for child host utility functions."""

    def test_get_user_with_role_check_success(self, mock_db_session, mock_user):
        """Test get_user_with_role_check with valid user and role."""
        from backend.security.roles import SecurityRoles

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with patch("backend.api.child_host_utils.models") as mock_models:
            mock_models.User = MagicMock()
            from backend.api.child_host_utils import get_user_with_role_check

            result = get_user_with_role_check(
                mock_db_session, "admin@sysmanage.org", SecurityRoles.VIEW_CHILD_HOST
            )

            assert result == mock_user

    def test_get_user_with_role_check_user_not_found(self, mock_db_session):
        """Test get_user_with_role_check when user not found."""
        from fastapi import HTTPException
        from backend.security.roles import SecurityRoles

        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.api.child_host_utils.models") as mock_models:
            mock_models.User = MagicMock()
            from backend.api.child_host_utils import get_user_with_role_check

            with pytest.raises(HTTPException) as exc_info:
                get_user_with_role_check(
                    mock_db_session,
                    "unknown@example.com",
                    SecurityRoles.VIEW_CHILD_HOST,
                )

            assert exc_info.value.status_code == 401

    def test_get_user_with_role_check_no_permission(self, mock_db_session, mock_user):
        """Test get_user_with_role_check when user lacks permission."""
        from fastapi import HTTPException
        from backend.security.roles import SecurityRoles

        mock_user.has_role.return_value = False
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_user
        )

        with patch("backend.api.child_host_utils.models") as mock_models:
            mock_models.User = MagicMock()
            from backend.api.child_host_utils import get_user_with_role_check

            with pytest.raises(HTTPException) as exc_info:
                get_user_with_role_check(
                    mock_db_session,
                    "admin@sysmanage.org",
                    SecurityRoles.CREATE_CHILD_HOST,
                )

            assert exc_info.value.status_code == 403

    def test_get_host_or_404_success(self, mock_db_session, mock_host):
        """Test get_host_or_404 when host exists."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.child_host_utils.models") as mock_models:
            mock_models.Host = MagicMock()
            from backend.api.child_host_utils import get_host_or_404

            result = get_host_or_404(mock_db_session, str(mock_host.id))

            assert result == mock_host

    def test_get_host_or_404_not_found(self, mock_db_session):
        """Test get_host_or_404 when host not found."""
        from fastapi import HTTPException

        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.api.child_host_utils.models") as mock_models:
            mock_models.Host = MagicMock()
            from backend.api.child_host_utils import get_host_or_404

            with pytest.raises(HTTPException) as exc_info:
                get_host_or_404(mock_db_session, str(uuid.uuid4()))

            assert exc_info.value.status_code == 404

    def test_verify_host_active_success(self, mock_host):
        """Test verify_host_active with active host."""
        from backend.api.child_host_utils import verify_host_active

        # Should not raise
        verify_host_active(mock_host)

    def test_verify_host_active_inactive(self, mock_host):
        """Test verify_host_active with inactive host."""
        from fastapi import HTTPException
        from backend.api.child_host_utils import verify_host_active

        mock_host.active = False

        with pytest.raises(HTTPException) as exc_info:
            verify_host_active(mock_host)

        assert exc_info.value.status_code == 400


# =============================================================================
# CHILD HOST CONTROL ENDPOINT TESTS
# =============================================================================


class TestChildHostControlEndpoints:
    """Tests for child host control (start/stop/restart) endpoints."""

    @pytest.mark.asyncio
    async def test_start_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host, mock_queue_ops
    ):
        """Test successful child host start."""
        mock_child_host.status = "stopped"
        mock_child_host.parent_host_id = mock_host.id

        with patch(
            "backend.api.child_host_control.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_control.db"
        ) as mock_db, patch(
            "backend.api.child_host_control.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active"
        ), patch(
            "backend.api.child_host_control.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_control.create_command_message"
        ) as mock_create_msg, patch(
            "backend.api.child_host_control.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )
            mock_create_msg.return_value = {
                "type": "command",
                "command": "start_child_host",
            }

            from backend.api.child_host_control import start_child_host

            result = await start_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True
            mock_q.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test successful child host stop."""
        mock_child_host.parent_host_id = mock_host.id

        with patch(
            "backend.api.child_host_control.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_control.db"), patch(
            "backend.api.child_host_control.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active"
        ), patch(
            "backend.api.child_host_control.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_control.create_command_message"
        ), patch(
            "backend.api.child_host_control.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )

            from backend.api.child_host_control import stop_child_host

            result = await stop_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_restart_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test successful child host restart."""
        mock_child_host.parent_host_id = mock_host.id

        with patch(
            "backend.api.child_host_control.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_control.db"), patch(
            "backend.api.child_host_control.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active"
        ), patch(
            "backend.api.child_host_control.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_control.create_command_message"
        ), patch(
            "backend.api.child_host_control.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )

            from backend.api.child_host_control import restart_child_host

            result = await restart_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_control_child_not_found(self, mock_db_session, mock_user, mock_host):
        """Test control operation when child host not found."""
        from fastapi import HTTPException

        with patch(
            "backend.api.child_host_control.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_control.db"), patch(
            "backend.api.child_host_control.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            from backend.api.child_host_control import start_child_host

            with pytest.raises(HTTPException) as exc_info:
                await start_child_host(
                    str(mock_host.id), str(uuid.uuid4()), "admin@sysmanage.org"
                )

            assert exc_info.value.status_code == 404


# =============================================================================
# CHILD HOST CRUD ENDPOINT TESTS
# =============================================================================


class TestChildHostCrudEndpoints:
    """Tests for child host CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_child_hosts_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test listing child hosts."""
        mock_child_host.parent_host_id = mock_host.id

        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
                mock_child_host
            ]

            from backend.api.child_host_crud import list_child_hosts

            result = await list_child_hosts(str(mock_host.id), "admin@sysmanage.org")

            assert len(result) == 1
            assert result[0].child_name == mock_child_host.child_name

    @pytest.mark.asyncio
    async def test_list_child_hosts_empty(self, mock_db_session, mock_user, mock_host):
        """Test listing child hosts when none exist."""
        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )

            from backend.api.child_host_crud import list_child_hosts

            result = await list_child_hosts(str(mock_host.id), "admin@sysmanage.org")

            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test getting a specific child host."""
        mock_child_host.parent_host_id = mock_host.id

        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )

            from backend.api.child_host_crud import get_child_host

            result = await get_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result.child_name == mock_child_host.child_name
            assert result.status == mock_child_host.status

    @pytest.mark.asyncio
    async def test_get_child_host_not_found(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test getting a non-existent child host."""
        from fastapi import HTTPException

        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            from backend.api.child_host_crud import get_child_host

            with pytest.raises(HTTPException) as exc_info:
                await get_child_host(
                    str(mock_host.id), str(uuid.uuid4()), "admin@sysmanage.org"
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_refresh_child_hosts(self, mock_db_session, mock_user, mock_host):
        """Test refreshing child hosts list."""
        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_crud.verify_host_active"
        ), patch(
            "backend.api.child_host_crud.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_crud.create_command_message"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_crud import refresh_child_hosts

            result = await refresh_child_hosts(str(mock_host.id), "admin@sysmanage.org")

            assert result["result"] is True
            mock_q.enqueue_message.assert_called_once()


# =============================================================================
# CHILD HOST DELETE ENDPOINT TESTS
# =============================================================================


class TestChildHostDeleteEndpoints:
    """Tests for child host delete operations."""

    @pytest.mark.asyncio
    async def test_delete_pending_child_host(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test deleting a pending child host (no command sent to agent)."""
        mock_child_host.parent_host_id = mock_host.id
        mock_child_host.status = "pending"
        mock_child_host.child_host_id = None
        mock_child_host.hostname = None

        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_crud.verify_host_active"
        ), patch(
            "backend.api.child_host_crud.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )

            from backend.api.child_host_crud import delete_child_host

            result = await delete_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True
            mock_db_session.delete.assert_called()

    @pytest.mark.asyncio
    async def test_delete_running_child_host(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test deleting a running child host (sends command to agent)."""
        mock_child_host.parent_host_id = mock_host.id
        mock_child_host.status = "running"

        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_crud.verify_host_active"
        ), patch(
            "backend.api.child_host_crud.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_crud.create_command_message"
        ), patch(
            "backend.api.child_host_crud.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )

            from backend.api.child_host_crud import delete_child_host

            result = await delete_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True
            assert mock_child_host.status == "uninstalling"
            mock_q.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_failed_child_host(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test deleting a failed child host (direct DB delete)."""
        mock_child_host.parent_host_id = mock_host.id
        mock_child_host.status = "failed"
        mock_child_host.child_host_id = None
        mock_child_host.hostname = None

        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_crud.verify_host_active"
        ), patch(
            "backend.api.child_host_crud.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )

            from backend.api.child_host_crud import delete_child_host

            result = await delete_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True


# =============================================================================
# VIRTUALIZATION STATUS ENDPOINT TESTS
# =============================================================================


class TestVirtualizationStatusEndpoints:
    """Tests for virtualization status endpoints."""

    @pytest.mark.asyncio
    async def test_get_virtualization_support(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test getting virtualization support."""
        with patch(
            "backend.api.child_host_virtualization_status.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_status.db"
        ), patch(
            "backend.api.child_host_virtualization_status.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_status.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_status.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_status.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_status.create_command_message"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_status import (
                get_virtualization_support,
            )

            result = await get_virtualization_support(
                str(mock_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True
            mock_q.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_virtualization_status_windows(
        self, mock_db_session, mock_user, mock_windows_host
    ):
        """Test getting virtualization status for Windows host."""
        with patch(
            "backend.api.child_host_virtualization_status.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_status.db"
        ), patch(
            "backend.api.child_host_virtualization_status.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_status.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_status.models"
        ) as mock_models:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_windows_host
            mock_db_session.query.return_value.filter.return_value.count.return_value = (
                0
            )

            from backend.api.child_host_virtualization_status import (
                get_virtualization_status,
            )

            result = await get_virtualization_status(
                str(mock_windows_host.id), "admin@sysmanage.org"
            )

            assert "wsl" in result["supported_types"]

    @pytest.mark.asyncio
    async def test_get_virtualization_status_linux(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test getting virtualization status for Linux host."""
        mock_host.virtualization_capabilities = None
        mock_host.virtualization_types = None

        with patch(
            "backend.api.child_host_virtualization_status.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_status.db"
        ), patch(
            "backend.api.child_host_virtualization_status.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_status.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_status.models"
        ) as mock_models:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.count.return_value = (
                0
            )

            from backend.api.child_host_virtualization_status import (
                get_virtualization_status,
            )

            result = await get_virtualization_status(
                str(mock_host.id), "admin@sysmanage.org"
            )

            assert "lxd" in result["supported_types"]
            assert "kvm" in result["supported_types"]

    @pytest.mark.asyncio
    async def test_get_virtualization_status_openbsd(
        self, mock_db_session, mock_user, mock_openbsd_host
    ):
        """Test getting virtualization status for OpenBSD host."""
        mock_openbsd_host.virtualization_capabilities = None
        mock_openbsd_host.virtualization_types = None

        with patch(
            "backend.api.child_host_virtualization_status.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_status.db"
        ), patch(
            "backend.api.child_host_virtualization_status.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_status.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_status.models"
        ) as mock_models:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_openbsd_host
            mock_db_session.query.return_value.filter.return_value.count.return_value = (
                0
            )

            from backend.api.child_host_virtualization_status import (
                get_virtualization_status,
            )

            result = await get_virtualization_status(
                str(mock_openbsd_host.id), "admin@sysmanage.org"
            )

            assert "vmm" in result["supported_types"]


# =============================================================================
# VIRTUALIZATION ENABLE ENDPOINT TESTS
# =============================================================================


class TestVirtualizationEnableEndpoints:
    """Tests for virtualization enable/initialize endpoints."""

    @pytest.mark.asyncio
    async def test_enable_wsl_success(
        self, mock_db_session, mock_user, mock_windows_host
    ):
        """Test enabling WSL on Windows host."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_windows_host

            from backend.api.child_host_virtualization_enable import enable_wsl

            result = await enable_wsl(str(mock_windows_host.id), "admin@sysmanage.org")

            assert result["result"] is True
            mock_q.enqueue_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_wsl_wrong_platform(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test enabling WSL on non-Windows host."""
        from fastapi import HTTPException

        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host  # Linux host

            from backend.api.child_host_virtualization_enable import enable_wsl

            with pytest.raises(HTTPException) as exc_info:
                await enable_wsl(str(mock_host.id), "admin@sysmanage.org")

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_initialize_lxd_success(self, mock_db_session, mock_user, mock_host):
        """Test initializing LXD on Linux host."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import initialize_lxd

            result = await initialize_lxd(str(mock_host.id), "admin@sysmanage.org")

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_initialize_vmm_success(
        self, mock_db_session, mock_user, mock_openbsd_host
    ):
        """Test initializing VMM on OpenBSD host."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_openbsd_host

            from backend.api.child_host_virtualization_enable import initialize_vmm

            result = await initialize_vmm(
                str(mock_openbsd_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_initialize_kvm_success(self, mock_db_session, mock_user, mock_host):
        """Test initializing KVM on Linux host."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import initialize_kvm

            result = await initialize_kvm(str(mock_host.id), "admin@sysmanage.org")

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_initialize_bhyve_success(
        self, mock_db_session, mock_user, mock_freebsd_host
    ):
        """Test initializing bhyve on FreeBSD host."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_freebsd_host

            from backend.api.child_host_virtualization_enable import initialize_bhyve

            result = await initialize_bhyve(
                str(mock_freebsd_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_enable_without_privileged_agent(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test enabling virtualization without privileged agent."""
        from fastapi import HTTPException

        mock_host.is_agent_privileged = False

        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import initialize_lxd

            with pytest.raises(HTTPException) as exc_info:
                await initialize_lxd(str(mock_host.id), "admin@sysmanage.org")

            assert exc_info.value.status_code == 400


# =============================================================================
# DISTRIBUTION ENDPOINT TESTS
# =============================================================================


class TestDistributionEndpoints:
    """Tests for distribution management endpoints."""

    @pytest.mark.asyncio
    async def test_list_distributions(
        self, mock_db_session, mock_user, mock_distribution
    ):
        """Test listing active distributions."""
        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"):

            mock_sessionmaker.return_value.return_value = mock_db_session
            query = mock_db_session.query.return_value
            query.filter.return_value = query
            query.order_by.return_value.all.return_value = [mock_distribution]

            from backend.api.child_host_crud import list_distributions

            result = await list_distributions(None, "admin@sysmanage.org")

            assert len(result) == 1
            assert result[0].distribution_name == "Ubuntu"

    @pytest.mark.asyncio
    async def test_list_distributions_by_type(
        self, mock_db_session, mock_user, mock_distribution
    ):
        """Test listing distributions filtered by type."""
        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"):

            mock_sessionmaker.return_value.return_value = mock_db_session
            query = mock_db_session.query.return_value
            query.filter.return_value = query
            query.order_by.return_value.all.return_value = [mock_distribution]

            from backend.api.child_host_crud import list_distributions

            result = await list_distributions("lxd", "admin@sysmanage.org")

            assert len(result) == 1
            assert result[0].child_type == "lxd"

    @pytest.mark.asyncio
    async def test_get_distribution(
        self, mock_db_session, mock_user, mock_distribution
    ):
        """Test getting a specific distribution."""
        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_distribution
            )

            from backend.api.child_host_crud import get_distribution

            result = await get_distribution(
                str(mock_distribution.id), "admin@sysmanage.org"
            )

            assert result.distribution_name == "Ubuntu"
            assert result.distribution_version == "22.04"

    @pytest.mark.asyncio
    async def test_get_distribution_not_found(self, mock_db_session, mock_user):
        """Test getting a non-existent distribution."""
        from fastapi import HTTPException

        with patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch("backend.api.child_host_crud.db"), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            from backend.api.child_host_crud import get_distribution

            with pytest.raises(HTTPException) as exc_info:
                await get_distribution(str(uuid.uuid4()), "admin@sysmanage.org")

            assert exc_info.value.status_code == 404


# =============================================================================
# KVM NETWORKING ENDPOINT TESTS
# =============================================================================


class TestKvmNetworkingEndpoints:
    """Tests for KVM networking configuration endpoints."""

    @pytest.mark.asyncio
    async def test_configure_kvm_networking_nat(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test configuring NAT networking for KVM."""
        from backend.api.child_host_models import ConfigureKvmNetworkingRequest

        request = ConfigureKvmNetworkingRequest(mode="nat", network_name="default")

        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import (
                configure_kvm_networking,
            )

            result = await configure_kvm_networking(
                str(mock_host.id), request, "admin@sysmanage.org"
            )

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_configure_kvm_networking_bridged(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test configuring bridged networking for KVM."""
        from backend.api.child_host_models import ConfigureKvmNetworkingRequest

        request = ConfigureKvmNetworkingRequest(mode="bridged", bridge="br0")

        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import (
                configure_kvm_networking,
            )

            result = await configure_kvm_networking(
                str(mock_host.id), request, "admin@sysmanage.org"
            )

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_configure_kvm_networking_bridged_without_bridge(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test configuring bridged networking without bridge interface."""
        from fastapi import HTTPException
        from backend.api.child_host_models import ConfigureKvmNetworkingRequest

        request = ConfigureKvmNetworkingRequest(mode="bridged")  # No bridge specified

        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import (
                configure_kvm_networking,
            )

            with pytest.raises(HTTPException) as exc_info:
                await configure_kvm_networking(
                    str(mock_host.id), request, "admin@sysmanage.org"
                )

            assert exc_info.value.status_code == 400


# =============================================================================
# KVM MODULE ENDPOINT TESTS
# =============================================================================


class TestKvmModuleEndpoints:
    """Tests for KVM module enable/disable endpoints."""

    @pytest.mark.asyncio
    async def test_enable_kvm_modules(self, mock_db_session, mock_user, mock_host):
        """Test enabling KVM kernel modules."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import enable_kvm_modules

            result = await enable_kvm_modules(str(mock_host.id), "admin@sysmanage.org")

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_disable_kvm_modules(self, mock_db_session, mock_user, mock_host):
        """Test disabling KVM kernel modules."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_virtualization_enable import disable_kvm_modules

            result = await disable_kvm_modules(str(mock_host.id), "admin@sysmanage.org")

            assert result["result"] is True


# =============================================================================
# BHYVE ENDPOINT TESTS
# =============================================================================


class TestBhyveEndpoints:
    """Tests for bhyve-specific endpoints."""

    @pytest.mark.asyncio
    async def test_disable_bhyve(self, mock_db_session, mock_user, mock_freebsd_host):
        """Test disabling bhyve on FreeBSD host."""
        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ), patch(
            "backend.api.child_host_virtualization_enable.queue_ops"
        ) as mock_q, patch(
            "backend.api.child_host_virtualization_enable.create_command_message"
        ), patch(
            "backend.api.child_host_virtualization_enable.audit_log"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_freebsd_host

            from backend.api.child_host_virtualization_enable import disable_bhyve

            result = await disable_bhyve(
                str(mock_freebsd_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True

    @pytest.mark.asyncio
    async def test_disable_bhyve_wrong_platform(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test disabling bhyve on non-FreeBSD host."""
        from fastapi import HTTPException

        with patch(
            "backend.api.child_host_virtualization_enable.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.db"
        ), patch(
            "backend.api.child_host_virtualization_enable.get_user_with_role_check"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
        ):

            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host  # Linux host

            from backend.api.child_host_virtualization_enable import disable_bhyve

            with pytest.raises(HTTPException) as exc_info:
                await disable_bhyve(str(mock_host.id), "admin@sysmanage.org")

            assert exc_info.value.status_code == 400
