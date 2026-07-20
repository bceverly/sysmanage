# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
API endpoint tests for child host distribution and KVM/bhyve endpoints.

Split from test_child_host_api_endpoints.py:
- Distribution management endpoints
- KVM networking, KVM module, and bhyve endpoints
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
            "backend.api.child_host_virtualization_enable._check_container_module"
        ), patch(
            "backend.api.child_host_virtualization_enable._try_init_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable._try_kvm_network_plan_path",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
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
            "backend.api.child_host_virtualization_enable._check_container_module"
        ), patch(
            "backend.api.child_host_virtualization_enable._try_init_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable._try_kvm_network_plan_path",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
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
            "backend.api.child_host_virtualization_enable._check_container_module"
        ), patch(
            "backend.api.child_host_virtualization_enable._try_init_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.authorize_on_main"
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
            "backend.api.child_host_virtualization_enable._check_container_module"
        ), patch(
            "backend.api.child_host_virtualization_enable._try_init_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable._try_kvm_network_plan_path",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
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
            "backend.api.child_host_virtualization_enable._check_container_module"
        ), patch(
            "backend.api.child_host_virtualization_enable._try_init_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable._try_kvm_network_plan_path",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
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
            "backend.api.child_host_virtualization_enable._check_container_module"
        ), patch(
            "backend.api.child_host_virtualization_enable._try_init_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable._try_kvm_network_plan_path",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.authorize_on_main"
        ) as mock_role_check, patch(
            "backend.api.child_host_virtualization_enable.get_host_or_404"
        ) as mock_get_host, patch(
            "backend.api.child_host_virtualization_enable.verify_host_active"
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
            "backend.api.child_host_virtualization_enable._check_container_module"
        ), patch(
            "backend.api.child_host_virtualization_enable._try_init_plan_dispatch",
            return_value=True,
        ), patch(
            "backend.api.child_host_virtualization_enable.request_sessionmaker"
        ) as mock_sessionmaker, patch(
            "backend.api.child_host_virtualization_enable.authorize_on_main"
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
