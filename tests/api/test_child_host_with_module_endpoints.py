# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
API endpoint tests for child host operations when the container_engine module is present.

Split from test_child_host_api_endpoints.py:
- Child host control with module
- Child host delete with module
- Distribution CRUD with module
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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
# CHILD HOST CONTROL WITH MODULE TESTS
# =============================================================================


class TestChildHostControlWithModule:
    """Tests for child host control endpoints when container_engine module is present."""

    @pytest.mark.asyncio
    async def test_start_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test starting a child host with module present."""
        mock_child_host.parent_host_id = mock_host.id

        with patch("backend.api.child_host_control._check_container_module"), patch(
            "backend.api.child_host_control._try_lifecycle_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control._try_update_agent_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_control.db"
        ), patch(
            "backend.api.child_host_control.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active"
        ), patch(
            "backend.api.child_host_control.audit_log"
        ):
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_child_host
            )
            from backend.api.child_host_control import start_child_host

            result = await start_child_host(
                str(mock_host.id), str(mock_child_host.id), "admin@sysmanage.org"
            )

            assert result["result"] is True
            assert "start" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_stop_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test stopping a child host with module present."""
        mock_child_host.parent_host_id = mock_host.id

        with patch("backend.api.child_host_control._check_container_module"), patch(
            "backend.api.child_host_control._try_lifecycle_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control._try_update_agent_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_control.db"
        ), patch(
            "backend.api.child_host_control.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active"
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
            assert "stop" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_restart_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test restarting a child host with module present."""
        mock_child_host.parent_host_id = mock_host.id

        with patch("backend.api.child_host_control._check_container_module"), patch(
            "backend.api.child_host_control._try_lifecycle_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control._try_update_agent_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_control.db"
        ), patch(
            "backend.api.child_host_control.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active"
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
            assert "restart" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_start_child_host_not_found(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test starting a non-existent child host."""
        from fastapi import HTTPException

        with patch("backend.api.child_host_control._check_container_module"), patch(
            "backend.api.child_host_control._try_lifecycle_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control._try_update_agent_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_control.db"
        ), patch(
            "backend.api.child_host_control.authorize_on_main"
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

    @pytest.mark.asyncio
    async def test_start_child_host_inactive(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test starting a child host on an inactive parent."""
        from fastapi import HTTPException

        mock_host.active = False

        with patch("backend.api.child_host_control._check_container_module"), patch(
            "backend.api.child_host_control._try_lifecycle_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control._try_update_agent_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_control.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_control.db"
        ), patch(
            "backend.api.child_host_control.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_control.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_control.verify_host_active",
            side_effect=HTTPException(status_code=400, detail="Host is not active"),
        ):
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host

            from backend.api.child_host_control import start_child_host

            with pytest.raises(HTTPException) as exc_info:
                await start_child_host(
                    str(mock_host.id), str(uuid.uuid4()), "admin@sysmanage.org"
                )

            assert exc_info.value.status_code == 400


# =============================================================================
# CHILD HOST DELETE WITH MODULE TESTS
# =============================================================================


class TestChildHostDeleteWithModule:
    """Tests for child host delete endpoint when container_engine module is present."""

    @pytest.mark.asyncio
    async def test_delete_child_host_success(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Test deleting a child host with module present."""
        mock_child_host.parent_host_id = mock_host.id

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.authorize_on_main"
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
            # Plan-based delete: row pruned immediately rather than
            # transitioning through a "deleting" state.
            mock_db_session.delete.assert_any_call(mock_child_host)

    @pytest.mark.asyncio
    async def test_delete_child_host_not_found(
        self, mock_db_session, mock_user, mock_host
    ):
        """Test deleting a non-existent child host."""
        from fastapi import HTTPException

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_crud.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_crud.verify_host_active"
        ):
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_get_host.return_value = mock_host
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            from backend.api.child_host_crud import delete_child_host

            with pytest.raises(HTTPException) as exc_info:
                await delete_child_host(
                    str(mock_host.id), str(uuid.uuid4()), "admin@sysmanage.org"
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_wsl_child_forwards_guid_to_engine(
        self, mock_db_session, mock_user, mock_host, mock_child_host
    ):
        """Plan-based deletion of a WSL child must forward the wsl_guid to
        ``_try_plan_based_deletion`` so the engine plan can target the
        correct distro instance."""
        mock_child_host.parent_host_id = mock_host.id
        mock_child_host.child_type = "wsl"
        mock_child_host.wsl_guid = "12345-abcde-67890"

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ) as mock_try_plan, patch(
            "backend.api.child_host_crud.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.authorize_on_main"
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
            # The plan-based deletion helper receives the child row, which
            # carries the ``wsl_guid`` it needs to target the right WSL
            # distro instance in the generated plan.
            mock_try_plan.assert_called_once()
            child_arg = mock_try_plan.call_args[0][0]
            assert child_arg.wsl_guid == "12345-abcde-67890"


# =============================================================================
# DISTRIBUTION CRUD WITH MODULE TESTS
# =============================================================================


class TestDistributionCrudWithModule:
    """Tests for distribution CRUD endpoints when container_engine module is present."""

    @pytest.mark.asyncio
    async def test_create_distribution_success(self, mock_db_session, mock_user):
        """Test creating a new distribution."""
        from backend.api.child_host_models import CreateDistributionRequest

        request = CreateDistributionRequest(
            child_type="lxd",
            distribution_name="Ubuntu",
            distribution_version="24.04",
            display_name="Ubuntu 24.04 LTS",
            is_active=True,
        )

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user

            # No duplicate found
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            # Mock session.add, session.commit, session.refresh
            def mock_refresh(obj):
                obj.id = uuid.uuid4()
                from datetime import datetime, timezone

                obj.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
                obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            mock_db_session.refresh = mock_refresh

            from backend.api.child_host_crud import create_distribution

            result = await create_distribution(request, "admin@sysmanage.org")

            assert result.distribution_name == "Ubuntu"
            assert result.distribution_version == "24.04"
            assert result.child_type == "lxd"
            mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_distribution_duplicate(
        self, mock_db_session, mock_user, mock_distribution
    ):
        """Test creating a duplicate distribution."""
        from fastapi import HTTPException

        from backend.api.child_host_models import CreateDistributionRequest

        request = CreateDistributionRequest(
            child_type="lxd",
            distribution_name="Ubuntu",
            distribution_version="22.04",
            display_name="Ubuntu 22.04 LTS",
        )

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user

            # Duplicate found
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_distribution
            )

            from backend.api.child_host_crud import create_distribution

            with pytest.raises(HTTPException) as exc_info:
                await create_distribution(request, "admin@sysmanage.org")

            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_update_distribution_success(
        self, mock_db_session, mock_user, mock_distribution
    ):
        """Test updating a distribution."""
        from backend.api.child_host_models import UpdateDistributionRequest

        request = UpdateDistributionRequest(display_name="Ubuntu 22.04 Updated")

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_distribution
            )

            from backend.api.child_host_crud import update_distribution

            result = await update_distribution(
                str(mock_distribution.id), request, "admin@sysmanage.org"
            )

            assert result.distribution_name == "Ubuntu"
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_distribution_not_found(self, mock_db_session, mock_user):
        """Test updating a non-existent distribution."""
        from fastapi import HTTPException

        from backend.api.child_host_models import UpdateDistributionRequest

        request = UpdateDistributionRequest(display_name="Updated")

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            from backend.api.child_host_crud import update_distribution

            with pytest.raises(HTTPException) as exc_info:
                await update_distribution(
                    str(uuid.uuid4()), request, "admin@sysmanage.org"
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_distribution_success(
        self, mock_db_session, mock_user, mock_distribution
    ):
        """Test deleting a distribution."""
        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                mock_distribution
            )

            from backend.api.child_host_crud import delete_distribution

            result = await delete_distribution(
                str(mock_distribution.id), "admin@sysmanage.org"
            )

            assert result["result"] is True
            mock_db_session.delete.assert_called_once_with(mock_distribution)

    @pytest.mark.asyncio
    async def test_delete_distribution_not_found(self, mock_db_session, mock_user):
        """Test deleting a non-existent distribution."""
        from fastapi import HTTPException

        with patch("backend.api.child_host_crud._check_container_module"), patch(
            "backend.api.child_host_crud._try_plan_based_deletion",
            return_value=True,
        ), patch(
            "backend.api.child_host_crud.sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_crud.db"
        ), patch(
            "backend.api.child_host_crud.get_user_with_role_check"
        ) as mock_role_check:
            mock_sessionmaker.return_value.return_value = mock_db_session
            mock_role_check.return_value = mock_user
            mock_db_session.query.return_value.filter.return_value.first.return_value = (
                None
            )

            from backend.api.child_host_crud import delete_distribution

            with pytest.raises(HTTPException) as exc_info:
                await delete_distribution(str(uuid.uuid4()), "admin@sysmanage.org")

            assert exc_info.value.status_code == 404
