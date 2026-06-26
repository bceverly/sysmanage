"""
Comprehensive tests for child host message handlers.

This module tests the handlers that process messages from agents:
- Virtualization support updates
- WSL/LXD/VMM/KVM/bhyve initialization results
- Child host list updates
- Child host creation progress and completion
- Child host control results (start, stop, restart, delete)
"""

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
    session.commit = MagicMock()
    session.flush = MagicMock()
    session.refresh = MagicMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    return session


@pytest.fixture
def mock_connection():
    """Create a mock WebSocket connection."""
    connection = MagicMock()
    connection.host_id = str(uuid.uuid4())
    return connection


@pytest.fixture
def mock_host():
    """Create a mock host."""
    host = MagicMock()
    host.id = uuid.uuid4()
    host.fqdn = "testhost.example.com"
    host.active = True
    host.platform = "Linux"
    host.virtualization_types = None
    host.virtualization_capabilities = None
    host.virtualization_updated_at = None
    host.reboot_required = False
    host.reboot_required_reason = None
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
    child.wsl_guid = None
    child.auto_approve_token = None
    child.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    child.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return child


# =============================================================================
# PRO+ GATE TESTS
# =============================================================================


class TestProPlusGate:
    """When the Pro+ engine is not loaded, public child-host handlers must
    refuse the operation with ``feature_not_licensed`` instead of running
    the OSS shim that's slated for Phase-2 deletion."""

    _GATE = {"message_type": "error", "error_type": "feature_not_licensed"}

    @pytest.mark.asyncio
    async def test_creation_progress_returns_proplus_required(
        self, mock_db_session, mock_connection
    ):
        from backend.api.handlers.child_host.creation import (
            handle_child_host_creation_progress,
        )

        with patch(
            "backend.api.handlers.child_host.creation.module_loader.get_module",
            return_value=None,
        ):
            result = await handle_child_host_creation_progress(
                mock_db_session, mock_connection, {"success": True}
            )
        assert result["error_type"] == "feature_not_licensed"

    @pytest.mark.asyncio
    async def test_created_returns_proplus_required(
        self, mock_db_session, mock_connection
    ):
        from backend.api.handlers.child_host.creation import handle_child_host_created

        with patch(
            "backend.api.handlers.child_host.creation.module_loader.get_module",
            return_value=None,
        ):
            result = await handle_child_host_created(
                mock_db_session, mock_connection, {"success": True}
            )
        assert result["error_type"] == "feature_not_licensed"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        [
            "handle_child_host_start_result",
            "handle_child_host_stop_result",
            "handle_child_host_restart_result",
            "handle_child_host_delete_result",
        ],
    )
    async def test_control_returns_proplus_required(
        self, mock_db_session, mock_connection, name
    ):
        import backend.api.handlers.child_host.control as control_mod

        handler = getattr(control_mod, name)
        with patch.object(control_mod.module_loader, "get_module", return_value=None):
            result = await handler(mock_db_session, mock_connection, {"success": True})
        assert result["error_type"] == "feature_not_licensed"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        [
            "handle_virtualization_support_update",
            "handle_wsl_enable_result",
            "handle_lxd_initialize_result",
            "handle_vmm_initialize_result",
            "handle_kvm_initialize_result",
            "handle_bhyve_initialize_result",
            "handle_kvm_modules_enable_result",
            "handle_kvm_modules_disable_result",
        ],
    )
    async def test_virtualization_returns_proplus_required(
        self, mock_db_session, mock_connection, name
    ):
        import backend.api.handlers.child_host.virtualization as virt_mod

        handler = getattr(virt_mod, name)
        with patch.object(virt_mod.module_loader, "get_module", return_value=None):
            result = await handler(mock_db_session, mock_connection, {"success": True})
        assert result["error_type"] == "feature_not_licensed"

    @pytest.mark.asyncio
    async def test_listing_returns_proplus_required(
        self, mock_db_session, mock_connection
    ):
        from backend.api.handlers.child_host.listing import (
            handle_child_hosts_list_update,
        )

        with patch(
            "backend.api.handlers.child_host.listing.module_loader.get_module",
            return_value=None,
        ):
            result = await handle_child_hosts_list_update(
                mock_db_session, mock_connection, {"success": True}
            )
        assert result["error_type"] == "feature_not_licensed"
