"""
Unit tests for configuration management API endpoints.
Tests config push, logging config, WebSocket config, and server config endpoints.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_websocket_dependencies():
    """Mock WebSocket and encryption dependencies for all tests."""
    with patch(
        "backend.websocket.connection_manager.connection_manager"
    ) as mock_conn_mgr, patch(
        "backend.security.communication_security.message_encryption"
    ) as mock_encryption:

        # Mock connection manager methods
        mock_conn_mgr.send_to_hostname = AsyncMock(return_value=True)
        mock_conn_mgr.broadcast_to_platform = AsyncMock(return_value=2)
        mock_conn_mgr.get_active_agents.return_value = [
            {"hostname": "agent1.example.com"},
            {"hostname": "agent2.example.com"},
        ]

        # Mock message encryption
        mock_encryption.encrypt_sensitive_data.return_value = "encrypted_config_data"

        yield {"connection_manager": mock_conn_mgr, "encryption": mock_encryption}


class TestConfigPush:
    """Test cases for POST /config/push endpoint."""

    @patch("backend.api.config_management.config_push_manager")
    def test_push_config_to_specific_host(
        self, mock_config_manager, client, auth_headers
    ):
        """Test pushing config to a specific hostname."""
        # Mock successful config push with AsyncMock
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=True)

        config_data = {
            "config_data": {
                "logging": {"level": "DEBUG"},
                "websocket": {"ping_interval": 60},
            },
            "target_hostname": "target.example.com",
            "push_to_all": False,
        }

        response = client.post(
            "/api/config/push", json=config_data, headers=auth_headers
        )

        # Check response status

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed successfully" in data["message"]
        assert data["target"] == "target.example.com"

        # Verify config push was called
        mock_config_manager.push_config_to_agent.assert_called_once_with(
            "target.example.com", config_data["config_data"]
        )

    @patch("backend.api.config_management.config_push_manager")
    def test_push_config_to_all_agents(self, mock_config_manager, client, auth_headers):
        """Test pushing config to all connected agents."""
        # Mock successful push to all agents with AsyncMock
        mock_results = {
            "agent1.example.com": True,
            "agent2.example.com": True,
            "agent3.example.com": True,
        }
        mock_config_manager.push_config_to_all_agents = AsyncMock(
            return_value=mock_results
        )

        config_data = {
            "config_data": {"server": {"hostname": "new-server.example.com"}},
            "push_to_all": True,
        }

        response = client.post(
            "/api/config/push", json=config_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed to all agents" in data["message"]
        assert data["total_agents"] == 3
        assert data["successful"] == 3

        # Verify push to all was called
        mock_config_manager.push_config_to_all_agents.assert_called_once_with(
            config_data["config_data"]
        )

    @patch("backend.api.config_management.config_push_manager")
    def test_push_config_by_platform(self, mock_config_manager, client, auth_headers):
        """Test pushing config to agents by platform."""
        # Mock platform-specific config push with AsyncMock
        mock_config_manager.push_config_by_platform = AsyncMock(return_value=2)

        config_data = {
            "config_data": {"client": {"registration_retry_interval": 60}},
            "target_platform": "Linux",
            "push_to_all": False,
        }

        response = client.post(
            "/api/config/push", json=config_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed to platform agents" in data["message"]
        assert data["platform"] == "Linux"
        assert data["successful_sends"] == 2

        # Verify platform push was called
        mock_config_manager.push_config_by_platform.assert_called_once_with(
            "Linux", config_data["config_data"]
        )

    def test_push_config_invalid_request(self, client, auth_headers):
        """Test pushing config with invalid request data."""
        # No targets specified
        config_data = {"config_data": {"test": "value"}, "push_to_all": False}

        response = client.post(
            "/api/config/push", json=config_data, headers=auth_headers
        )

        # Check response status - should be error code

        assert response.status_code == 500  # API wraps validation errors in 500s
        data = response.json()
        assert "target" in data["detail"].lower()

    def test_push_config_missing_data(self, client, auth_headers):
        """Test pushing config with missing config data."""
        config_data = {"target_hostname": "test.example.com", "push_to_all": False}

        response = client.post(
            "/api/config/push", json=config_data, headers=auth_headers
        )
        assert response.status_code == 422  # Validation error

    def test_push_config_unauthorized(self, client):
        """Test pushing config without authentication."""
        config_data = {"config_data": {"test": "value"}, "push_to_all": True}

        response = client.post("/api/config/push", json=config_data)
        assert response.status_code == 403


class TestLoggingConfig:
    """Test cases for POST /config/logging endpoint."""

    @patch("backend.api.config_management.config_push_manager")
    def test_update_logging_config_specific_host(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating logging config for specific hostname."""
        # Mock the create_logging_config method to return proper data
        mock_config_manager.create_logging_config.return_value = {
            "logging": {"level": "DEBUG", "log_file": "/var/log/sysmanage-debug.log"}
        }
        # Mock the config push to return success with AsyncMock
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=True)

        logging_data = {
            "log_level": "DEBUG",
            "log_file": "/var/log/sysmanage-debug.log",
            "target_hostname": "test.example.com",
            "push_to_all": False,
        }

        response = client.post(
            "/api/config/logging", json=logging_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed successfully" in data["message"]
        assert data["target"] == "test.example.com"

        # Verify logging config was created and pushed
        mock_config_manager.create_logging_config.assert_called_once_with(
            log_level="DEBUG", log_file="/var/log/sysmanage-debug.log"
        )
        mock_config_manager.push_config_to_agent.assert_called_once()

    @patch("backend.api.config_management.config_push_manager")
    def test_update_logging_config_all_agents(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating logging config for all agents."""
        # Mock logging config creation and push to all
        mock_config_manager.create_logging_config.return_value = {
            "logging": {"level": "ERROR", "file": "/var/log/sysmanage-error.log"}
        }
        mock_results = {
            "agent1.example.com": True,
            "agent2.example.com": True,
            "agent3.example.com": True,
            "agent4.example.com": True,
            "agent5.example.com": True,
        }
        mock_config_manager.push_config_to_all_agents = AsyncMock(
            return_value=mock_results
        )

        logging_data = {
            "log_level": "ERROR",
            "log_file": "/var/log/sysmanage-error.log",
            "push_to_all": True,
        }

        response = client.post(
            "/api/config/logging", json=logging_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed to all agents" in data["message"]
        assert data["total_agents"] == 5
        assert data["successful"] == 5

        # Verify logging config creation and push to all
        mock_config_manager.create_logging_config.assert_called_once_with(
            log_level="ERROR", log_file="/var/log/sysmanage-error.log"
        )
        mock_config_manager.push_config_to_all_agents.assert_called_once()

    @patch("backend.api.config_management.config_push_manager")
    def test_update_logging_config_invalid_level(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating logging config with invalid log level."""
        # Mock logging config creation and push even for invalid level test
        mock_config_manager.create_logging_config.return_value = {
            "logging": {"level": "INVALID_LEVEL"}
        }
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=False)

        logging_data = {
            "log_level": "INVALID_LEVEL",
            "target_hostname": "test.example.com",
        }

        response = client.post(
            "/api/config/logging", json=logging_data, headers=auth_headers
        )
        # API wraps validation errors in 500s
        assert response.status_code == 500

    @patch("backend.api.config_management.config_push_manager")
    def test_update_logging_config_no_target(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating logging config without specifying target."""
        # Mock config creation for no target test
        mock_config_manager.create_logging_config.return_value = {
            "logging": {"level": "INFO"}
        }

        logging_data = {"log_level": "INFO", "push_to_all": False}

        response = client.post(
            "/api/config/logging", json=logging_data, headers=auth_headers
        )

        assert response.status_code == 500  # API wraps validation errors in 500s
        data = response.json()
        assert "target" in data["detail"].lower()

    def test_update_logging_config_unauthorized(self, client):
        """Test updating logging config without authentication."""
        logging_data = {"log_level": "DEBUG", "push_to_all": True}

        response = client.post("/api/config/logging", json=logging_data)
        assert response.status_code == 403


class TestWebSocketConfig:
    """Test cases for POST /config/websocket endpoint."""

    @patch("backend.api.config_management.config_push_manager")
    def test_update_websocket_config_success(
        self, mock_config_manager, client, auth_headers
    ):
        """Test successful WebSocket config update."""
        # Mock WebSocket config creation and push
        mock_config_manager.create_websocket_config.return_value = {
            "websocket": {
                "ping_interval": 45,
                "reconnect_interval": 10,
                "auto_reconnect": True,
            }
        }
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=True)

        ws_config_data = {
            "ping_interval": 45,
            "reconnect_interval": 10,
            "target_hostname": "test.example.com",
            "push_to_all": False,
        }

        response = client.post(
            "/api/config/websocket", json=ws_config_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed successfully" in data["message"]
        assert data["target"] == "test.example.com"

        # Verify WebSocket config creation and push
        mock_config_manager.create_websocket_config.assert_called_once_with(
            ping_interval=45, reconnect_interval=10
        )
        mock_config_manager.push_config_to_agent.assert_called_once()

    @patch("backend.api.config_management.config_push_manager")
    def test_update_websocket_config_all_agents(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating WebSocket config for all agents."""
        # Mock WebSocket config creation and push to all
        mock_config_manager.create_websocket_config.return_value = {
            "websocket": {
                "ping_interval": 120,
                "reconnect_interval": 15,
                "auto_reconnect": True,
            }
        }
        mock_results = {
            "agent1.example.com": True,
            "agent2.example.com": True,
            "agent3.example.com": True,
        }
        mock_config_manager.push_config_to_all_agents = AsyncMock(
            return_value=mock_results
        )

        ws_config_data = {
            "ping_interval": 120,
            "reconnect_interval": 15,
            "push_to_all": True,
        }

        response = client.post(
            "/api/config/websocket", json=ws_config_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed to all agents" in data["message"]
        assert data["total_agents"] == 3
        assert data["successful"] == 3

    @patch("backend.api.config_management.config_push_manager")
    def test_update_websocket_config_invalid_intervals(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating WebSocket config with invalid intervals."""
        # Mock config creation and push for invalid intervals test
        mock_config_manager.create_websocket_config.return_value = {
            "websocket": {"ping_interval": -1, "reconnect_interval": 5}
        }
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=False)

        ws_config_data = {
            "ping_interval": -1,  # Invalid negative interval
            "reconnect_interval": 5,
            "target_hostname": "test.example.com",
        }

        response = client.post(
            "/api/config/websocket", json=ws_config_data, headers=auth_headers
        )
        assert response.status_code == 500  # API wraps validation errors in 500s

    def test_update_websocket_config_unauthorized(self, client):
        """Test updating WebSocket config without authentication."""
        ws_config_data = {"ping_interval": 30, "push_to_all": True}

        response = client.post("/api/config/websocket", json=ws_config_data)
        assert response.status_code == 403


class TestServerConfig:
    """Test cases for POST /config/server endpoint."""

    @patch("backend.api.config_management.config_push_manager")
    def test_update_server_config_success(
        self, mock_config_manager, client, auth_headers
    ):
        """Test successful server config update."""
        # Mock server config creation and push
        mock_config_manager.create_server_config.return_value = {
            "server": {
                "hostname": "new-server.example.com",
                "port": 8443,
                "use_https": True,
                "api_path": "/api",
            }
        }
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=True)

        server_config_data = {
            "hostname": "new-server.example.com",
            "port": 8443,
            "use_https": True,
            "target_hostname": "agent.example.com",
        }

        response = client.post(
            "/api/config/server", json=server_config_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed successfully" in data["message"]
        assert data["target"] == "agent.example.com"

        # Verify server config creation and push
        mock_config_manager.create_server_config.assert_called_once_with(
            hostname="new-server.example.com", port=8443, use_https=True
        )
        mock_config_manager.push_config_to_agent.assert_called_once()

    @patch("backend.api.config_management.config_push_manager")
    def test_update_server_config_all_agents(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating server config for all agents."""
        # Mock server config creation and push to all
        mock_config_manager.create_server_config.return_value = {
            "server": {
                "hostname": "updated-server.example.com",
                "port": 9000,
                "use_https": False,
                "api_path": "/api",
            }
        }
        mock_results = {
            "agent1.example.com": True,
            "agent2.example.com": True,
            "agent3.example.com": True,
            "agent4.example.com": True,
        }
        mock_config_manager.push_config_to_all_agents = AsyncMock(
            return_value=mock_results
        )

        server_config_data = {
            "hostname": "updated-server.example.com",
            "port": 9000,
            "use_https": False,
            "push_to_all": True,
        }

        response = client.post(
            "/api/config/server", json=server_config_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration pushed to all agents" in data["message"]
        assert data["total_agents"] == 4
        assert data["successful"] == 4

    @patch("backend.api.config_management.config_push_manager")
    def test_update_server_config_invalid_port(
        self, mock_config_manager, client, auth_headers
    ):
        """Test updating server config with invalid port."""
        # Mock config creation and push for invalid port test
        mock_config_manager.create_server_config.return_value = {
            "server": {"hostname": "test.example.com", "port": 99999}
        }
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=False)

        server_config_data = {
            "hostname": "test.example.com",
            "port": 99999,  # Invalid port number
            "target_hostname": "agent.example.com",
        }

        response = client.post(
            "/api/config/server", json=server_config_data, headers=auth_headers
        )
        assert response.status_code == 500  # API wraps validation errors in 500s

    def test_update_server_config_unauthorized(self, client):
        """Test updating server config without authentication."""
        server_config_data = {
            "hostname": "test.example.com",
            "push_to_all": True,
        }

        response = client.post("/api/config/server", json=server_config_data)
        assert response.status_code == 403


class TestConfigPending:
    """Test cases for GET /config/pending endpoint."""

    @patch("backend.api.config_management.config_push_manager")
    def test_get_pending_configs_success(
        self, mock_config_manager, client, auth_headers
    ):
        """Test getting list of pending configurations."""
        # Mock pending configs
        mock_pending = [
            {
                "hostname": "agent1.example.com",
                "config_type": "logging",
                "created_at": "2023-01-01T12:00:00Z",
                "version": "1.0.1",
            },
            {
                "hostname": "agent2.example.com",
                "config_type": "websocket",
                "created_at": "2023-01-01T12:05:00Z",
                "version": "1.0.2",
            },
        ]
        mock_config_manager.get_pending_configs.return_value = mock_pending

        response = client.get("/api/config/pending", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "pending_configs" in data
        assert len(data["pending_configs"]) == 2
        assert data["total_pending"] == 2

        # Verify config manager was called
        mock_config_manager.get_pending_configs.assert_called_once()

    @patch("backend.api.config_management.config_push_manager")
    def test_get_pending_configs_empty(self, mock_config_manager, client, auth_headers):
        """Test getting pending configs when none exist."""
        mock_config_manager.get_pending_configs.return_value = []

        response = client.get("/api/config/pending", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["pending_configs"] == []
        assert data["total_pending"] == 0

    # Note: The API doesn't currently support hostname filtering for pending configs
    # @patch("backend.api.config_management.config_push_manager")
    # def test_get_pending_configs_with_hostname_filter(
    #     self, mock_config_manager, client, auth_headers
    # ):
    #     """Test getting pending configs filtered by hostname."""
    #     # This functionality is not currently implemented in the API
    #     pass

    def test_get_pending_configs_unauthorized(self, client):
        """Test getting pending configs without authentication."""
        response = client.get("/api/config/pending")
        assert response.status_code == 403


class TestConfigAcknowledge:
    """Test cases for POST /config/acknowledge endpoint."""

    @patch("backend.api.config_management.config_push_manager")
    def test_acknowledge_config_success(
        self, mock_config_manager, client, auth_headers
    ):
        """Test successful config acknowledgment."""
        # The acknowledge endpoint uses query parameters, not JSON body
        hostname = "agent.example.com"
        version = 1
        success = True

        response = client.post(
            f"/api/config/acknowledge?hostname={hostname}&version={version}&success={success}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration acknowledgment processed" in data["message"]
        assert data["hostname"] == hostname
        assert data["version"] == version
        assert data["success"] == success

        # Verify handle_config_acknowledgment was called
        mock_config_manager.handle_config_acknowledgment.assert_called_once_with(
            hostname, version, success, None
        )

    @patch("backend.api.config_management.config_push_manager")
    def test_acknowledge_config_not_found(
        self, mock_config_manager, client, auth_headers
    ):
        """Test acknowledging non-existent config."""
        # The acknowledge endpoint doesn't return 404 for non-existent configs
        # It just processes the acknowledgment and logs warnings
        hostname = "nonexistent.example.com"
        version = 1
        success = False

        response = client.post(
            f"/api/config/acknowledge?hostname={hostname}&version={version}&success={success}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Configuration acknowledgment processed" in data["message"]
        assert data["hostname"] == hostname

    def test_acknowledge_config_missing_fields(self, client, auth_headers):
        """Test acknowledging config with missing required fields."""
        # Missing version parameter
        response = client.post(
            "/api/config/acknowledge?hostname=agent.example.com&success=true",
            headers=auth_headers,
        )
        assert response.status_code == 422

        # Missing hostname parameter
        response = client.post(
            "/api/config/acknowledge?version=1&success=true",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_acknowledge_config_unauthorized(self, client):
        """Test acknowledging config without authentication."""
        response = client.post(
            "/api/config/acknowledge?hostname=agent.example.com&version=1&success=true"
        )
        assert response.status_code == 403


class TestConfigManagementIntegration:
    """Integration tests for config management functionality."""

    @patch("backend.api.config_management.config_push_manager")
    def test_config_push_workflow(self, mock_config_manager, client, auth_headers):
        """Test complete config push workflow."""
        # 1. Push a configuration
        mock_config_manager.push_config_to_agent = AsyncMock(return_value=True)

        config_data = {
            "config_data": {"logging": {"level": "DEBUG"}},
            "target_hostname": "test.example.com",
        }

        push_response = client.post(
            "/api/config/push", json=config_data, headers=auth_headers
        )
        assert push_response.status_code == 200

        # 2. Check pending configurations
        mock_config_manager.get_pending_configs.return_value = [
            {
                "hostname": "test.example.com",
                "config_type": "logging",
                "version": "1.0.1",
            }
        ]

        pending_response = client.get("/api/config/pending", headers=auth_headers)
        assert pending_response.status_code == 200
        pending_data = pending_response.json()
        assert len(pending_data["pending_configs"]) == 1

        # 3. Acknowledge the configuration
        hostname = "test.example.com"
        version = 1
        success = True

        ack_response = client.post(
            f"/api/config/acknowledge?hostname={hostname}&version={version}&success={success}",
            headers=auth_headers,
        )
        assert ack_response.status_code == 200

        # Verify all operations were called
        mock_config_manager.push_config_to_agent.assert_called_once()
        mock_config_manager.get_pending_configs.assert_called_once()
        mock_config_manager.handle_config_acknowledgment.assert_called_once()
