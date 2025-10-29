"""
Unit tests for fleet management API endpoints.
Tests fleet status, agent management, and command sending endpoints.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.websocket.messages import CommandType, MessageType


class TestFleetStatus:
    """Test cases for GET /fleet/status endpoint."""

    @patch("backend.api.fleet.connection_manager")
    def test_get_fleet_status_success(
        self, mock_connection_manager, client, auth_headers
    ):
        """Test getting fleet status with connected agents."""
        # Mock active agents
        mock_agents = [
            {
                "hostname": "agent1.example.com",
                "platform": "Linux",
                "last_seen": "2023-01-01T12:00:00Z",
                "status": "connected",
            },
            {
                "hostname": "agent2.example.com",
                "platform": "Windows",
                "last_seen": "2023-01-01T12:01:00Z",
                "status": "connected",
            },
        ]
        mock_connection_manager.get_active_agents.return_value = mock_agents

        response = client.get("/api/fleet/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total_agents"] == 2
        assert len(data["agents"]) == 2
        assert data["agents"][0]["hostname"] == "agent1.example.com"
        assert data["agents"][1]["hostname"] == "agent2.example.com"

    @patch("backend.api.fleet.connection_manager")
    def test_get_fleet_status_empty(
        self, mock_connection_manager, client, auth_headers
    ):
        """Test getting fleet status with no connected agents."""
        mock_connection_manager.get_active_agents.return_value = []

        response = client.get("/api/fleet/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total_agents"] == 0
        assert data["agents"] == []

    def test_get_fleet_status_unauthorized(self, client):
        """Test getting fleet status without authentication."""
        response = client.get("/api/fleet/status")
        assert response.status_code == 403


class TestListAgents:
    """Test cases for GET /fleet/agents endpoint."""

    @patch("backend.api.fleet.connection_manager")
    def test_list_agents_success(self, mock_connection_manager, client, auth_headers):
        """Test listing all connected agents."""
        mock_agents = [
            {
                "id": "agent1",
                "hostname": "agent1.example.com",
                "platform": "Linux",
                "last_seen": "2023-01-01T12:00:00Z",
            }
        ]
        mock_connection_manager.get_active_agents.return_value = mock_agents

        response = client.get("/api/fleet/agents", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["hostname"] == "agent1.example.com"

    @patch("backend.api.fleet.connection_manager")
    def test_list_agents_empty(self, mock_connection_manager, client, auth_headers):
        """Test listing agents when none are connected."""
        mock_connection_manager.get_active_agents.return_value = []

        response = client.get("/api/fleet/agents", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_agents_unauthorized(self, client):
        """Test listing agents without authentication."""
        response = client.get("/api/fleet/agents")
        assert response.status_code == 403


class TestGetAgent:
    """Test cases for GET /fleet/agent/{hostname} endpoint."""

    @patch("backend.api.fleet.connection_manager")
    def test_get_agent_success(self, mock_connection_manager, client, auth_headers):
        """Test getting specific agent by hostname."""
        mock_agent = {
            "id": "agent1",
            "hostname": "test.example.com",
            "platform": "Linux",
            "last_seen": "2023-01-01T12:00:00Z",
        }
        mock_connection_manager.get_agent_by_hostname.return_value = mock_agent

        response = client.get("/api/fleet/agent/test.example.com", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["hostname"] == "test.example.com"
        assert data["platform"] == "Linux"

        # Verify connection manager was called correctly
        mock_connection_manager.get_agent_by_hostname.assert_called_once_with(
            "test.example.com"
        )

    @patch("backend.api.fleet.connection_manager")
    def test_get_agent_not_found(self, mock_connection_manager, client, auth_headers):
        """Test getting non-existent agent."""
        mock_connection_manager.get_agent_by_hostname.return_value = None

        response = client.get(
            "/api/fleet/agent/nonexistent.example.com", headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]

    def test_get_agent_unauthorized(self, client):
        """Test getting agent without authentication."""
        response = client.get("/api/fleet/agent/test.example.com")
        assert response.status_code == 403


class TestSendCommand:
    """Test cases for POST /fleet/agent/{hostname}/command endpoint."""

    @patch("backend.api.fleet.queue_ops")
    def test_send_command_success(self, mock_queue_ops, client, auth_headers, session):
        """Test successfully sending command to agent."""
        from backend.persistence.models import Host
        import uuid

        # Create host in database
        host = Host(
            id=uuid.uuid4(),
            fqdn="test.example.com",
            active=True,
            platform="Linux",
        )
        session.add(host)
        session.commit()

        # Mock queue operations
        mock_queue_ops.enqueue_message = Mock()

        command_data = {
            "command_type": "get_system_info",
            "parameters": {},
            "timeout": 300,
        }

        response = client.post(
            "/api/fleet/agent/test.example.com/command",
            json=command_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert "command_id" in data
        # Use exact matching for security - check specific message format
        assert data["message"] == "Command get_system_info sent to test.example.com"

        # Verify enqueue_message was called
        mock_queue_ops.enqueue_message.assert_called_once()

    def test_send_command_host_not_found(self, client, auth_headers):
        """Test sending command to non-existent host."""
        command_data = {
            "command_type": "get_system_info",
            "parameters": {},
            "timeout": 300,
        }

        response = client.post(
            "/api/fleet/agent/offline.example.com/command",
            json=command_data,
            headers=auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "Host not found" in data["detail"]

    def test_send_command_invalid_type(self, client, auth_headers):
        """Test sending command with invalid command type."""
        command_data = {
            "command_type": "invalid_command",
            "parameters": {},
            "timeout": 300,
        }

        response = client.post(
            "/api/fleet/agent/test.example.com/command",
            json=command_data,
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error

    def test_send_command_missing_fields(self, client, auth_headers):
        """Test sending command with missing required fields."""
        # Missing command_type
        response = client.post(
            "/api/fleet/agent/test.example.com/command",
            json={"parameters": {}},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_send_command_unauthorized(self, client):
        """Test sending command without authentication."""
        command_data = {
            "command_type": "get_system_info",
            "parameters": {},
            "timeout": 300,
        }

        response = client.post(
            "/api/fleet/agent/test.example.com/command", json=command_data
        )
        assert response.status_code == 403


class TestShellCommand:
    """Test cases for POST /fleet/agent/{hostname}/shell endpoint."""

    @patch("backend.api.fleet.queue_ops")
    def test_send_shell_command_success(
        self, mock_queue_ops, client, auth_headers, session
    ):
        """Test successfully sending shell command to agent."""
        from backend.persistence.models import Host
        import uuid

        # Create host in database
        host = Host(
            id=uuid.uuid4(),
            fqdn="test.example.com",
            active=True,
            platform="Linux",
        )
        session.add(host)
        session.commit()

        # Mock queue operations
        mock_queue_ops.enqueue_message = Mock()

        shell_data = {"command": "ls -la", "timeout": 60, "working_directory": "/tmp"}

        response = client.post(
            "/api/fleet/agent/test.example.com/shell",
            json=shell_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["command"] == "ls -la"
        # Use exact matching for security - check specific message format
        assert data["message"] == "Shell command sent to test.example.com"

        # Verify enqueue_message was called
        mock_queue_ops.enqueue_message.assert_called_once()

    def test_send_shell_command_host_not_found(self, client, auth_headers):
        """Test sending shell command to non-existent host."""
        shell_data = {"command": "ls -la", "timeout": 60}

        response = client.post(
            "/api/fleet/agent/nonexistent.example.com/shell",
            json=shell_data,
            headers=auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "Host not found" in data["detail"]

    def test_send_shell_command_missing_command(self, client, auth_headers):
        """Test sending shell command without command field."""
        response = client.post(
            "/api/fleet/agent/test.example.com/shell",
            json={"timeout": 60},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_send_shell_command_unauthorized(self, client):
        """Test sending shell command without authentication."""
        shell_data = {"command": "ls -la", "timeout": 60}

        response = client.post(
            "/api/fleet/agent/test.example.com/shell", json=shell_data
        )
        assert response.status_code == 403


class TestPackageManagement:
    """Test cases for package management endpoints."""

    @patch("backend.api.fleet.queue_ops")
    def test_install_package_success(
        self, mock_queue_ops, client, auth_headers, session
    ):
        """Test successfully sending package install command."""
        from backend.persistence.models import Host
        import uuid

        # Create host in database
        host = Host(
            id=uuid.uuid4(),
            fqdn="test.example.com",
            active=True,
            platform="Linux",
        )
        session.add(host)
        session.commit()

        # Mock queue operations
        mock_queue_ops.enqueue_message = Mock()

        package_data = {"package_name": "nginx", "version": "1.18.0", "timeout": 600}

        response = client.post(
            "/api/fleet/agent/test.example.com/install-package",
            json=package_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["package"] == "nginx"
        # Use exact matching for security - check specific message format
        assert (
            data["message"] == "Package installation command sent to test.example.com"
        )

        # Verify enqueue_message was called
        mock_queue_ops.enqueue_message.assert_called_once()

    def test_install_package_missing_name(self, client, auth_headers):
        """Test installing package without package name."""
        response = client.post(
            "/api/fleet/agent/test.example.com/install-package",
            json={"version": "1.0.0"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestServiceManagement:
    """Test cases for service management endpoints."""

    @patch("backend.api.fleet.queue_ops")
    def test_restart_service_success(
        self, mock_queue_ops, client, auth_headers, session
    ):
        """Test successfully sending service restart command."""
        from backend.persistence.models import Host
        import uuid

        # Create host in database
        host = Host(
            id=uuid.uuid4(),
            fqdn="test.example.com",
            active=True,
            platform="Linux",
        )
        session.add(host)
        session.commit()

        # Mock queue operations
        mock_queue_ops.enqueue_message = Mock()

        service_data = {"service_name": "apache2", "timeout": 120}

        response = client.post(
            "/api/fleet/agent/test.example.com/restart-service",
            json=service_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        # Use exact matching for security - check specific message format
        assert data["message"] == "Service restart command sent to test.example.com"

        # Verify enqueue_message was called
        mock_queue_ops.enqueue_message.assert_called_once()

    def test_restart_service_missing_name(self, client, auth_headers):
        """Test restarting service without service name."""
        response = client.post(
            "/api/fleet/agent/test.example.com/restart-service",
            json={"timeout": 120},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestSystemCommands:
    """Test cases for system-level commands."""

    @patch("backend.api.fleet.queue_ops")
    def test_update_system_success(self, mock_queue_ops, client, auth_headers, session):
        """Test successfully sending system update command."""
        from backend.persistence.models import Host
        import uuid

        # Create host in database
        host = Host(
            id=uuid.uuid4(),
            fqdn="test.example.com",
            active=True,
            platform="Linux",
        )
        session.add(host)
        session.commit()

        # Mock queue operations
        mock_queue_ops.enqueue_message = Mock()

        response = client.post(
            "/api/fleet/agent/test.example.com/update-system",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        # Use exact matching for security - check specific message format
        assert data["message"] == "System update command sent to test.example.com"

        # Verify enqueue_message was called
        mock_queue_ops.enqueue_message.assert_called_once()

    @patch("backend.api.fleet.queue_ops")
    def test_reboot_system_success(self, mock_queue_ops, client, auth_headers, session):
        """Test successfully sending system reboot command."""
        from backend.persistence.models import Host
        import uuid

        # Create host in database
        host = Host(
            id=uuid.uuid4(),
            fqdn="test.example.com",
            active=True,
            platform="Linux",
        )
        session.add(host)
        session.commit()

        # Mock queue operations
        mock_queue_ops.enqueue_message = Mock()

        response = client.post(
            "/api/fleet/agent/test.example.com/reboot", json={}, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        # Use exact matching for security - check specific message format
        assert data["message"] == "Reboot command sent to test.example.com"

        # Verify enqueue_message was called
        mock_queue_ops.enqueue_message.assert_called_once()


class TestBroadcastCommand:
    """Test cases for broadcast commands."""

    @patch("backend.api.fleet.connection_manager")
    def test_broadcast_command_success(
        self, mock_connection_manager, client, auth_headers
    ):
        """Test successfully broadcasting command to all agents."""
        mock_connection_manager.broadcast_to_all = AsyncMock(
            return_value=3
        )  # 3 agents received

        broadcast_data = {
            "command_type": "get_system_info",
            "parameters": {},
            "timeout": 300,
        }

        response = client.post(
            "/api/fleet/broadcast/command", json=broadcast_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "broadcast"
        assert data["sent_to"] == 3
        assert "broadcast to 3 agents" in data["message"]

    def test_broadcast_command_missing_message(self, client, auth_headers):
        """Test broadcasting without message."""
        response = client.post(
            "/api/fleet/broadcast/command",
            json={"message_type": "NOTIFICATION"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_broadcast_command_unauthorized(self, client):
        """Test broadcasting without authentication."""
        broadcast_data = {"message": "Test message", "message_type": "NOTIFICATION"}

        response = client.post("/api/fleet/broadcast/command", json=broadcast_data)
        assert response.status_code == 403
