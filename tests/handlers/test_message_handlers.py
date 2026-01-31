"""
Tests for the message handlers module.

This module tests the main message handler functions that route
messages from agents to appropriate handlers.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.message_handlers import (
    handle_command_result,
    handle_config_acknowledgment,
    handle_diagnostic_result,
    handle_command_acknowledgment,
    handle_installation_status,
)


class TestHandleCommandResult:
    """Test cases for handle_command_result function."""

    @pytest.mark.asyncio
    async def test_routes_script_execution_result(self, mock_connection):
        """Test that script execution results are routed correctly."""
        message_data = {
            "execution_id": "exec-123",
            "result": {"status": "completed"},
        }

        with patch(
            "backend.api.handlers.handle_script_execution_result",
            new_callable=AsyncMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_virtualization_support_result(self, mock_connection):
        """Test that virtualization support results are routed correctly."""
        message_data = {
            "result": {
                "supported_types": ["lxd", "kvm"],
                "capabilities": {"nested": True},
            }
        }

        with patch(
            "backend.api.handlers.handle_virtualization_support_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_hosts_list_result(self, mock_connection):
        """Test that child hosts list results are routed correctly."""
        message_data = {
            "result": {
                "child_hosts": [
                    {"name": "vm1", "type": "kvm"},
                    {"name": "container1", "type": "lxd"},
                ]
            }
        }

        with patch(
            "backend.api.handlers.handle_child_hosts_list_update",
            new_callable=AsyncMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_host_start_result(self, mock_connection):
        """Test that child host start results are routed correctly."""
        message_data = {
            "command_type": "start_child_host",
            "result": {"child_name": "vm1", "child_type": "kvm", "status": "running"},
        }

        with patch(
            "backend.api.handlers.child_host_handlers.handle_child_host_start_result",
            new_callable=AsyncMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_host_stop_result(self, mock_connection):
        """Test that child host stop results are routed correctly."""
        message_data = {
            "command_type": "stop_child_host",
            "result": {"child_name": "vm1", "child_type": "kvm", "status": "stopped"},
        }

        with patch(
            "backend.api.handlers.child_host_handlers.handle_child_host_stop_result",
            new_callable=AsyncMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_host_restart_result(self, mock_connection):
        """Test that child host restart results are routed correctly."""
        message_data = {
            "command_type": "restart_child_host",
            "result": {"child_name": "vm1", "child_type": "kvm", "status": "running"},
        }

        with patch(
            "backend.api.handlers.child_host_handlers.handle_child_host_restart_result",
            new_callable=AsyncMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_child_host_delete_result(self, mock_connection):
        """Test that child host delete results are routed correctly."""
        message_data = {
            "command_type": "delete_child_host",
            "result": {"child_name": "vm1", "child_type": "kvm"},
        }

        with patch(
            "backend.api.handlers.child_host_handlers.handle_child_host_delete_result",
            new_callable=AsyncMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_package_collection_result(self, mock_connection):
        """Test that package collection results are routed correctly."""
        message_data = {
            "packages": [{"name": "nginx", "version": "1.24"}],
            "package_managers": ["apt"],
        }

        with patch(
            "backend.api.handlers.handle_package_collection",
            new_callable=MagicMock,
        ) as mock_handler:
            with patch("backend.persistence.db.get_db") as mock_get_db:
                mock_session = MagicMock()
                mock_get_db.return_value = iter([mock_session])
                mock_handler.return_value = {"status": "processed"}

                result = await handle_command_result(mock_connection, message_data)

                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_ack_for_regular_command(self, mock_connection):
        """Test that regular command results return acknowledgment."""
        message_data = {
            "result": {"status": "success"},
        }

        result = await handle_command_result(mock_connection, message_data)

        assert result["message_type"] == "command_result_ack"
        assert "timestamp" in result


class TestHandleConfigAcknowledgment:
    """Test cases for handle_config_acknowledgment function."""

    @pytest.mark.asyncio
    async def test_returns_config_ack_received(self, mock_connection):
        """Test that config acknowledgment returns proper response."""
        message_data = {"status": "applied"}

        result = await handle_config_acknowledgment(mock_connection, message_data)

        assert result["message_type"] == "config_ack_received"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_handles_unknown_status(self, mock_connection):
        """Test that unknown status is handled gracefully."""
        message_data = {}

        result = await handle_config_acknowledgment(mock_connection, message_data)

        assert result["message_type"] == "config_ack_received"


class TestHandleDiagnosticResult:
    """Test cases for handle_diagnostic_result function."""

    @pytest.mark.asyncio
    async def test_processes_diagnostic_result(self, mock_connection, session):
        """Test that diagnostic result is processed."""
        message_data = {
            "data": {"cpu": "50%", "memory": "4GB"},
        }

        with patch(
            "backend.api.diagnostics.process_diagnostic_result",
            new_callable=AsyncMock,
        ) as mock_process:
            result = await handle_diagnostic_result(
                session, mock_connection, message_data
            )

            mock_process.assert_called_once_with(message_data)
            assert result["message_type"] == "diagnostic_result_ack"
            assert result["status"] == "processed"

    @pytest.mark.asyncio
    async def test_handles_processing_error(self, mock_connection, session):
        """Test that processing errors are handled gracefully."""
        message_data = {"data": {}}

        with patch(
            "backend.api.diagnostics.process_diagnostic_result",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_process.side_effect = Exception("Processing error")

            result = await handle_diagnostic_result(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "error"
            assert result["error_type"] == "operation_failed"


class TestHandleCommandAcknowledgment:
    """Test cases for handle_command_acknowledgment function."""

    @pytest.mark.asyncio
    async def test_marks_message_as_acknowledged(self, mock_connection, session):
        """Test that acknowledged message is marked as completed."""
        message_data = {"message_id": "msg-123"}

        with patch(
            "backend.websocket.queue_manager.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_acknowledged.return_value = True

            result = await handle_command_acknowledgment(
                session, mock_connection, message_data
            )

            mock_queue.mark_acknowledged.assert_called_once_with("msg-123", db=session)
            assert result["message_type"] == "command_acknowledgment_received"
            assert result["message_id"] == "msg-123"

    @pytest.mark.asyncio
    async def test_handles_missing_message_id(self, mock_connection, session):
        """Test that missing message_id returns error."""
        message_data = {}

        result = await handle_command_acknowledgment(
            session, mock_connection, message_data
        )

        assert result["message_type"] == "error"
        assert result["error_type"] == "missing_message_id"

    @pytest.mark.asyncio
    async def test_handles_mark_failed(self, mock_connection, session):
        """Test that failed mark returns success but logs warning."""
        message_data = {"message_id": "msg-123"}

        with patch(
            "backend.websocket.queue_manager.server_queue_manager"
        ) as mock_queue:
            mock_queue.mark_acknowledged.return_value = False

            result = await handle_command_acknowledgment(
                session, mock_connection, message_data
            )

            # Should still return success response
            assert result["message_type"] == "command_acknowledgment_received"


class TestHandleInstallationStatus:
    """Test cases for handle_installation_status function."""

    @pytest.mark.asyncio
    async def test_updates_installation_log(self, mock_connection, session):
        """Test that installation status updates the log."""
        from backend.persistence.models import SoftwareInstallationLog

        # Create an installation log entry
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        log_entry = SoftwareInstallationLog(
            installation_id=installation_id,
            host_id=uuid.uuid4(),
            package_name="nginx",
            requested_version="1.24",
            package_manager="apt",
            status="pending",
            requested_by="test@example.com",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(log_entry)
        session.commit()

        message_data = {
            "installation_id": installation_id,
            "status": "installing",
            "package_name": "nginx",
        }

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_installation_status(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "package_installation_status_ack"
            assert result["installation_id"] == installation_id

            # Verify the log was updated
            updated_log = (
                session.query(SoftwareInstallationLog)
                .filter_by(installation_id=installation_id)
                .first()
            )
            assert updated_log.status == "installing"

    @pytest.mark.asyncio
    async def test_handles_missing_installation_id(self, mock_connection, session):
        """Test that missing installation_id returns error."""
        message_data = {"status": "completed"}

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_installation_status(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "error"
            assert result["error_type"] == "missing_installation_id"

    @pytest.mark.asyncio
    async def test_handles_installation_not_found(self, mock_connection, session):
        """Test that non-existent installation returns error."""
        message_data = {
            "installation_id": "nonexistent-id",
            "status": "completed",
        }

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_installation_status(
                session, mock_connection, message_data
            )

            assert result["message_type"] == "error"
            assert result["error_type"] == "installation_not_found"

    @pytest.mark.asyncio
    async def test_updates_completed_status(self, mock_connection, session):
        """Test that completed status updates log properly."""
        from backend.persistence.models import SoftwareInstallationLog

        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        log_entry = SoftwareInstallationLog(
            installation_id=installation_id,
            host_id=uuid.uuid4(),
            package_name="nginx",
            requested_version="1.24",
            package_manager="apt",
            status="installing",
            requested_by="test@example.com",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(log_entry)
        session.commit()

        message_data = {
            "installation_id": installation_id,
            "status": "completed",
            "package_name": "nginx",
            "installed_version": "1.24.0",
        }

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_installation_status(
                session, mock_connection, message_data
            )

            updated_log = (
                session.query(SoftwareInstallationLog)
                .filter_by(installation_id=installation_id)
                .first()
            )
            assert updated_log.status == "completed"
            assert updated_log.success is True
            assert updated_log.installed_version == "1.24.0"
            assert updated_log.completed_at is not None

    @pytest.mark.asyncio
    async def test_updates_failed_status(self, mock_connection, session):
        """Test that failed status updates log properly."""
        from backend.persistence.models import SoftwareInstallationLog

        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        log_entry = SoftwareInstallationLog(
            installation_id=installation_id,
            host_id=uuid.uuid4(),
            package_name="nginx",
            requested_version="1.24",
            package_manager="apt",
            status="installing",
            requested_by="test@example.com",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(log_entry)
        session.commit()

        message_data = {
            "installation_id": installation_id,
            "status": "failed",
            "package_name": "nginx",
            "error_message": "Package not found",
        }

        with patch(
            "backend.utils.host_validation.validate_host_id",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await handle_installation_status(
                session, mock_connection, message_data
            )

            updated_log = (
                session.query(SoftwareInstallationLog)
                .filter_by(installation_id=installation_id)
                .first()
            )
            assert updated_log.status == "failed"
            assert updated_log.success is False
            assert updated_log.error_message == "Package not found"
            assert updated_log.completed_at is not None
