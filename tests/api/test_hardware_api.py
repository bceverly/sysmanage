"""
Tests for hardware inventory API endpoints.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.persistence import models

# Test fixtures are automatically imported from conftest.py


class TestHardwareEndpoints:
    """Test class for hardware inventory endpoints."""

    def test_update_host_hardware_success(self, client: TestClient, auth_headers):
        """Test successful hardware update."""

        # Add a host
        host_data = {
            "active": True,
            "fqdn": "test-hardware.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
        }

        response = client.post("/api/host", json=host_data, headers=auth_headers)
        assert response.status_code == 200
        host = response.json()
        host_id = host["id"]

        # Test hardware update
        hardware_data = {
            "cpu_vendor": "Intel",
            "cpu_model": "Intel Core i7-9700K",
            "cpu_cores": 8,
            "cpu_threads": 8,
            "cpu_frequency_mhz": 3600,
            "memory_total_mb": 16384,
            "storage_details": json.dumps(
                [{"name": "/dev/sda1", "size": "500GB", "type": "SSD"}]
            ),
            "network_details": json.dumps(
                [
                    {
                        "name": "eth0",
                        "type": "ethernet",
                        "mac_address": "00:11:22:33:44:55",
                    }
                ]
            ),
            "hardware_details": json.dumps(
                {"platform": "Linux", "collection_timestamp": "2025-08-29T12:00:00Z"}
            ),
        }

        response = client.post(
            f"/api/host/{host_id}/update-hardware",
            json=hardware_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["result"] is True
        assert "successfully" in response.json()["message"]

        # Hardware update was successful - the endpoint returned success
        # Note: Hardware fields may not be included in the host GET response
        # unless the Host model is updated to include them in the JSON serialization

    def test_update_host_hardware_not_found(self, client: TestClient, auth_headers):
        """Test hardware update for non-existent host."""

        hardware_data = {"cpu_vendor": "Intel", "cpu_model": "Intel Core i7-9700K"}

        response = client.post(
            "/api/host/99999/update-hardware", json=hardware_data, headers=auth_headers
        )

        assert response.status_code == 404
        assert "Host not found" in response.json()["detail"]

    @patch("backend.websocket.connection_manager.connection_manager.send_to_host")
    def test_request_hardware_update_success(
        self, mock_send, client: TestClient, auth_headers
    ):
        """Test requesting hardware update from agent."""
        # Mock successful WebSocket send
        mock_send.return_value = True

        # Create and approve a test host
        host_data = {
            "active": True,
            "fqdn": "test-hardware-request.example.com",
            "ipv4": "192.168.1.101",
            "ipv6": "::1",
        }

        response = client.post("/api/host", json=host_data, headers=auth_headers)
        assert response.status_code == 200
        host_id = response.json()["id"]

        # Request hardware update
        response = client.post(
            f"/api/host/{host_id}/request-hardware-update", headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json()["result"] is True
        assert "requested" in response.json()["message"]

        # Verify WebSocket send was called
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == host_id  # host_id
        assert args[1]["data"]["command_type"] == "update_hardware"

    @patch("backend.websocket.connection_manager.connection_manager.send_to_host")
    def test_request_hardware_update_bulk_success(
        self, mock_send, client: TestClient, auth_headers
    ):
        """Test bulk hardware update request."""
        # Mock successful WebSocket send
        mock_send.return_value = True

        # Create two test hosts
        host_ids = []
        for i in range(2):
            host_data = {
                "active": True,
                "fqdn": f"test-bulk-{i}.example.com",
                "ipv4": f"192.168.1.{110 + i}",
                "ipv6": "::1",
            }

            response = client.post("/api/host", json=host_data, headers=auth_headers)
            assert response.status_code == 200
            host_ids.append(response.json()["id"])

        # Request bulk hardware update
        response = client.post(
            "/api/hosts/request-hardware-update", json=host_ids, headers=auth_headers
        )

        assert response.status_code == 200
        results = response.json()["results"]

        assert len(results) == 2
        for result in results:
            assert result["success"] is True
            assert "requested" in result["message"]

        # Verify WebSocket send was called twice
        assert mock_send.call_count == 2

    @patch("backend.websocket.connection_manager.connection_manager.send_to_host")
    def test_request_hardware_update_agent_offline(
        self, mock_send, client: TestClient, auth_headers
    ):
        """Test hardware update request when agent is offline."""
        # Mock failed WebSocket send (agent offline)
        mock_send.return_value = False

        # Create a test host
        host_data = {
            "active": True,
            "fqdn": "test-offline.example.com",
            "ipv4": "192.168.1.102",
            "ipv6": "::1",
        }

        response = client.post("/api/host", json=host_data, headers=auth_headers)
        assert response.status_code == 200
        host_id = response.json()["id"]

        # Request hardware update
        response = client.post(
            f"/api/host/{host_id}/request-hardware-update", headers=auth_headers
        )

        assert response.status_code == 503
        assert "not connected" in response.json()["detail"]
