"""
Comprehensive tests for child host message handlers.

This module tests the handlers that process messages from agents:
- Virtualization support updates
- WSL/LXD/VMM/KVM/bhyve initialization results
- Child host list updates
- Child host creation progress and completion
- Child host control results (start, stop, restart, delete)
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
# VIRTUALIZATION SUPPORT HANDLER TESTS
# =============================================================================


class TestVirtualizationSupportHandler:
    """Tests for virtualization support update handler."""

    @pytest.mark.asyncio
    async def test_handle_virtualization_support_update_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful virtualization support update."""
        message_data = {
            "success": True,
            "result": {
                "supported_types": ["lxd", "kvm"],
                "capabilities": {
                    "lxd": {
                        "available": True,
                        "installed": True,
                        "initialized": True,
                    },
                    "kvm": {
                        "available": True,
                        "enabled": True,
                        "running": True,
                    },
                },
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_virtualization_support_update,
            )

            result = await handle_virtualization_support_update(
                mock_db_session, mock_connection, message_data
            )

            # Handler returns acknowledgment with message_type
            assert result is not None
            # Host should have been updated
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_handle_virtualization_support_update_host_not_found(
        self, mock_db_session, mock_connection
    ):
        """Test handling virtualization update when host not found."""
        message_data = {
            "success": True,
            "result": {
                "supported_types": ["lxd"],
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_virtualization_support_update,
            )

            result = await handle_virtualization_support_update(
                mock_db_session, mock_connection, message_data
            )

            # Should still return a result (likely ack or error)
            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_virtualization_support_update_failure(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling failed virtualization support update."""
        message_data = {
            "success": False,
            "error": "Failed to detect virtualization support",
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_virtualization_support_update,
            )

            result = await handle_virtualization_support_update(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# WSL ENABLE HANDLER TESTS
# =============================================================================


class TestWslEnableHandler:
    """Tests for WSL enable result handler."""

    @pytest.mark.asyncio
    async def test_handle_wsl_enable_result_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful WSL enablement."""
        message_data = {
            "success": True,
            "result": {
                "requires_reboot": True,
                "message": "WSL enabled successfully. Please reboot.",
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_wsl_enable_result,
            )

            result = await handle_wsl_enable_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_wsl_enable_result_failure(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling WSL enablement failure."""
        message_data = {
            "success": False,
            "error": "Failed to enable WSL: insufficient permissions",
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_wsl_enable_result,
            )

            result = await handle_wsl_enable_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# LXD INITIALIZE HANDLER TESTS
# =============================================================================


class TestLxdInitializeHandler:
    """Tests for LXD initialization result handler."""

    @pytest.mark.asyncio
    async def test_handle_lxd_initialize_result_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful LXD initialization."""
        message_data = {
            "success": True,
            "result": {
                "message": "LXD installed and initialized successfully",
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_lxd_initialize_result,
            )

            result = await handle_lxd_initialize_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_lxd_initialize_result_failure(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling LXD initialization failure."""
        message_data = {
            "success": False,
            "error": "Failed to initialize LXD: snap installation failed",
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_lxd_initialize_result,
            )

            result = await handle_lxd_initialize_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# VMM INITIALIZE HANDLER TESTS
# =============================================================================


class TestVmmInitializeHandler:
    """Tests for VMM initialization result handler."""

    @pytest.mark.asyncio
    async def test_handle_vmm_initialize_result_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful VMM initialization."""
        message_data = {
            "success": True,
            "result": {
                "message": "VMM enabled and vmd started successfully",
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_vmm_initialize_result,
            )

            result = await handle_vmm_initialize_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# KVM INITIALIZE HANDLER TESTS
# =============================================================================


class TestKvmInitializeHandler:
    """Tests for KVM initialization result handler."""

    @pytest.mark.asyncio
    async def test_handle_kvm_initialize_result_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful KVM initialization."""
        message_data = {
            "success": True,
            "result": {
                "message": "KVM/libvirt initialized successfully",
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_kvm_initialize_result,
            )

            result = await handle_kvm_initialize_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# BHYVE INITIALIZE HANDLER TESTS
# =============================================================================


class TestBhyveInitializeHandler:
    """Tests for bhyve initialization result handler."""

    @pytest.mark.asyncio
    async def test_handle_bhyve_initialize_result_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful bhyve initialization."""
        message_data = {
            "success": True,
            "result": {
                "message": "bhyve vmm.ko loaded successfully",
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_bhyve_initialize_result,
            )

            result = await handle_bhyve_initialize_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# KVM MODULE HANDLER TESTS
# =============================================================================


class TestKvmModuleHandlers:
    """Tests for KVM module enable/disable handlers."""

    @pytest.mark.asyncio
    async def test_handle_kvm_modules_enable_result_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful KVM modules enablement."""
        message_data = {
            "success": True,
            "result": {
                "message": "KVM modules loaded successfully",
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_kvm_modules_enable_result,
            )

            result = await handle_kvm_modules_enable_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_kvm_modules_disable_result_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling successful KVM modules disablement."""
        message_data = {
            "success": True,
            "result": {
                "message": "KVM modules unloaded successfully",
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )

        with patch("backend.api.handlers.child_host.virtualization.logger"):
            from backend.api.handlers.child_host.virtualization import (
                handle_kvm_modules_disable_result,
            )

            result = await handle_kvm_modules_disable_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# CHILD HOST LIST UPDATE HANDLER TESTS
# =============================================================================


class TestChildHostListHandler:
    """Tests for child host list update handler."""

    @pytest.mark.asyncio
    async def test_handle_child_hosts_list_update_success(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling child host list update."""
        message_data = {
            "success": True,
            "result": {
                "child_hosts": [
                    {
                        "name": "Ubuntu-24.04",
                        "type": "wsl",
                        "status": "running",
                        "wsl_guid": str(uuid.uuid4()),
                    },
                    {
                        "name": "my-container",
                        "type": "lxd",
                        "status": "running",
                    },
                ]
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        with patch("backend.api.handlers.child_host.listing.logger"):
            from backend.api.handlers.child_host.listing import (
                handle_child_hosts_list_update,
            )

            result = await handle_child_hosts_list_update(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_child_hosts_list_update_empty(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling empty child host list."""
        message_data = {"success": True, "result": {"child_hosts": []}}

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        with patch("backend.api.handlers.child_host.listing.logger"):
            from backend.api.handlers.child_host.listing import (
                handle_child_hosts_list_update,
            )

            result = await handle_child_hosts_list_update(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# CHILD HOST CREATION PROGRESS HANDLER TESTS
# =============================================================================


class TestChildHostCreationProgressHandler:
    """Tests for child host creation progress handler."""

    @pytest.mark.asyncio
    async def test_handle_child_host_creation_progress(
        self, mock_db_session, mock_connection, mock_child_host
    ):
        """Test handling child host creation progress update."""
        message_data = {
            "child_host_id": str(mock_child_host.id),
            "step": "downloading_image",
            "message": "Downloading cloud image...",
            "progress": 50,
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_child_host
        )

        with patch("backend.api.handlers.child_host.creation.logger"):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_creation_progress,
            )

            result = await handle_child_host_creation_progress(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_child_host_creation_progress_child_not_found(
        self, mock_db_session, mock_connection
    ):
        """Test handling progress when child host not found."""
        message_data = {
            "child_host_id": str(uuid.uuid4()),
            "step": "installing",
            "message": "Installing...",
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.api.handlers.child_host.creation.logger"):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_creation_progress,
            )

            result = await handle_child_host_creation_progress(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# CHILD HOST CREATED HANDLER TESTS
# =============================================================================


class TestChildHostCreatedHandler:
    """Tests for child host created handler."""

    @pytest.mark.asyncio
    async def test_handle_child_host_created_success(
        self, mock_db_session, mock_connection, mock_child_host
    ):
        """Test handling successful child host creation."""
        message_data = {
            "success": True,
            "child_host_id": str(mock_child_host.id),
            "child_name": "test-vm",
            "child_type": "kvm",
            "hostname": "test-vm.local",
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_child_host
        )

        with patch("backend.api.handlers.child_host.creation.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_created,
            )

            result = await handle_child_host_created(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_child_host_created_failure(
        self, mock_db_session, mock_connection, mock_child_host
    ):
        """Test handling child host creation failure."""
        message_data = {
            "success": False,
            "child_host_id": str(mock_child_host.id),
            "error": "Failed to create VM: disk space insufficient",
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_child_host
        )

        with patch("backend.api.handlers.child_host.creation.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_created,
            )

            result = await handle_child_host_created(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# CHILD HOST CONTROL RESULT HANDLER TESTS
# =============================================================================


class TestChildHostControlResultHandlers:
    """Tests for child host control result handlers."""

    @pytest.mark.asyncio
    async def test_handle_child_host_start_result_success(
        self, mock_db_session, mock_connection, mock_host, mock_child_host
    ):
        """Test handling successful child host start."""
        mock_child_host.status = "stopped"
        mock_child_host.parent_host_id = mock_host.id

        message_data = {
            "success": True,
            "child_host_id": str(mock_child_host.id),
            "child_name": mock_child_host.child_name,
        }

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,
            mock_child_host,
        ]

        with patch("backend.api.handlers.child_host.control.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.control import (
                handle_child_host_start_result,
            )

            result = await handle_child_host_start_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_child_host_stop_result_success(
        self, mock_db_session, mock_connection, mock_host, mock_child_host
    ):
        """Test handling successful child host stop."""
        mock_child_host.parent_host_id = mock_host.id

        message_data = {
            "success": True,
            "child_host_id": str(mock_child_host.id),
            "child_name": mock_child_host.child_name,
        }

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,
            mock_child_host,
        ]

        with patch("backend.api.handlers.child_host.control.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.control import (
                handle_child_host_stop_result,
            )

            result = await handle_child_host_stop_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_child_host_restart_result_success(
        self, mock_db_session, mock_connection, mock_host, mock_child_host
    ):
        """Test handling successful child host restart."""
        mock_child_host.parent_host_id = mock_host.id

        message_data = {
            "success": True,
            "child_host_id": str(mock_child_host.id),
            "child_name": mock_child_host.child_name,
        }

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,
            mock_child_host,
        ]

        with patch("backend.api.handlers.child_host.control.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.control import (
                handle_child_host_restart_result,
            )

            result = await handle_child_host_restart_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_child_host_delete_result_success(
        self, mock_db_session, mock_connection, mock_host, mock_child_host
    ):
        """Test handling successful child host delete."""
        mock_child_host.parent_host_id = mock_host.id
        mock_child_host.status = "uninstalling"

        message_data = {
            "success": True,
            "child_host_id": str(mock_child_host.id),
            "child_name": mock_child_host.child_name,
        }

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,
            mock_child_host,
        ]

        with patch("backend.api.handlers.child_host.control.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.control import (
                handle_child_host_delete_result,
            )

            result = await handle_child_host_delete_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_child_host_control_failure(
        self, mock_db_session, mock_connection, mock_host, mock_child_host
    ):
        """Test handling child host control failure."""
        mock_child_host.parent_host_id = mock_host.id

        message_data = {
            "success": False,
            "child_host_id": str(mock_child_host.id),
            "child_name": mock_child_host.child_name,
            "error": "Failed to start: hypervisor error",
        }

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_host,
            mock_child_host,
        ]

        with patch("backend.api.handlers.child_host.control.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.control import (
                handle_child_host_start_result,
            )

            result = await handle_child_host_start_result(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestHandlerEdgeCases:
    """Tests for edge cases in handlers."""

    @pytest.mark.asyncio
    async def test_handle_missing_child_host_id(self, mock_db_session, mock_connection):
        """Test handling message with missing child_host_id."""
        message_data = {
            "success": True,
            # Missing child_host_id
        }

        with patch("backend.api.handlers.child_host.creation.logger"):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_creation_progress,
            )

            result = await handle_child_host_creation_progress(
                mock_db_session, mock_connection, message_data
            )

            # Should handle gracefully
            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_invalid_uuid(self, mock_db_session, mock_connection):
        """Test handling message with invalid UUID."""
        message_data = {
            "success": True,
            "child_host_id": "not-a-valid-uuid",
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with patch("backend.api.handlers.child_host.creation.logger"):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_creation_progress,
            )

            result = await handle_child_host_creation_progress(
                mock_db_session, mock_connection, message_data
            )

            # Should handle gracefully
            assert result is not None

    @pytest.mark.asyncio
    async def test_handle_empty_message_data(self, mock_db_session, mock_connection):
        """Test handling empty message data."""
        message_data = {}

        with patch("backend.api.handlers.child_host.creation.logger"):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_creation_progress,
            )

            result = await handle_child_host_creation_progress(
                mock_db_session, mock_connection, message_data
            )

            # Should handle gracefully
            assert result is not None


# =============================================================================
# WSL GUID VALIDATION TESTS
# =============================================================================


class TestWslGuidValidation:
    """Tests for WSL GUID validation in handlers."""

    @pytest.mark.asyncio
    async def test_handle_child_host_list_with_wsl_guid(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling child host list with WSL GUID."""
        wsl_guid = str(uuid.uuid4())
        message_data = {
            "success": True,
            "result": {
                "child_hosts": [
                    {
                        "name": "Ubuntu-24.04",
                        "type": "wsl",
                        "status": "running",
                        "wsl_guid": wsl_guid,
                    }
                ]
            },
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        with patch("backend.api.handlers.child_host.listing.logger"):
            from backend.api.handlers.child_host.listing import (
                handle_child_hosts_list_update,
            )

            result = await handle_child_hosts_list_update(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# AUTO-APPROVE TOKEN HANDLER TESTS
# =============================================================================


class TestAutoApproveTokenHandling:
    """Tests for auto-approve token handling in creation handler."""

    @pytest.mark.asyncio
    async def test_handle_child_created_with_auto_approve_token(
        self, mock_db_session, mock_connection, mock_child_host
    ):
        """Test handling child host creation with auto-approve token."""
        auto_approve_token = str(uuid.uuid4())
        mock_child_host.auto_approve_token = auto_approve_token

        message_data = {
            "success": True,
            "child_host_id": str(mock_child_host.id),
            "child_name": "test-vm",
            "child_type": "kvm",
            "auto_approve_token": auto_approve_token,
        }

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_child_host
        )

        with patch("backend.api.handlers.child_host.creation.logger"), patch(
            "backend.services.audit_service.AuditService"
        ):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_created,
            )

            result = await handle_child_host_created(
                mock_db_session, mock_connection, message_data
            )

            assert result is not None


# =============================================================================
# CONCURRENT UPDATE TESTS
# =============================================================================


class TestConcurrentUpdates:
    """Tests for handling concurrent updates."""

    @pytest.mark.asyncio
    async def test_rapid_progress_updates(
        self, mock_db_session, mock_connection, mock_child_host
    ):
        """Test handling rapid progress updates."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_child_host
        )

        steps = [
            "downloading_image",
            "creating_disk",
            "starting_vm",
            "waiting_for_boot",
            "configuring_network",
            "installing_agent",
        ]

        with patch("backend.api.handlers.child_host.creation.logger"):
            from backend.api.handlers.child_host.creation import (
                handle_child_host_creation_progress,
            )

            for step in steps:
                message_data = {
                    "child_host_id": str(mock_child_host.id),
                    "step": step,
                    "message": f"Step: {step}",
                }

                result = await handle_child_host_creation_progress(
                    mock_db_session, mock_connection, message_data
                )

                assert result is not None

    @pytest.mark.asyncio
    async def test_multiple_child_hosts_list_updates(
        self, mock_db_session, mock_connection, mock_host
    ):
        """Test handling multiple child host list updates."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            mock_host
        )
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        with patch("backend.api.handlers.child_host.listing.logger"):
            from backend.api.handlers.child_host.listing import (
                handle_child_hosts_list_update,
            )

            for i in range(5):
                message_data = {
                    "success": True,
                    "result": {
                        "child_hosts": [
                            {
                                "name": f"vm-{j}",
                                "type": "kvm",
                                "status": "running",
                            }
                            for j in range(i + 1)
                        ]
                    },
                }

                result = await handle_child_hosts_list_update(
                    mock_db_session, mock_connection, message_data
                )

                assert result is not None
