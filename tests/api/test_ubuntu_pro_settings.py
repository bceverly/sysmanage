"""
Unit tests for Ubuntu Pro settings API endpoints.
Tests the /api/ubuntu-pro/ endpoints with various scenarios.
"""

import pytest
from unittest.mock import patch, Mock
from datetime import datetime, timezone
from backend.persistence import models


class TestUbuntuProSettingsGet:
    """Test cases for the GET /api/ubuntu-pro/ endpoint."""

    def test_get_settings_success_existing(self, client, session, auth_headers):
        """Test successful retrieval of existing Ubuntu Pro settings."""
        # Create existing settings
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1234567890123456789012345",
            organization_name="Test Organization",
            auto_attach_enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test get settings
        response = client.get("/api/ubuntu-pro/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["master_key"] == "C1234567890123456789012345"
        assert data["organization_name"] == "Test Organization"
        assert data["auto_attach_enabled"] is True
        assert "created_at" in data
        assert "updated_at" in data

    def test_get_settings_creates_default_if_not_exists(
        self, client, session, auth_headers
    ):
        """Test that default settings are created if they don't exist."""
        # Ensure no settings exist
        assert session.query(models.UbuntuProSettings).count() == 0

        # Test get settings
        response = client.get("/api/ubuntu-pro/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["master_key"] is None
        assert data["organization_name"] is None
        assert data["auto_attach_enabled"] is False

        # Verify settings were created in database
        assert session.query(models.UbuntuProSettings).count() == 1

    def test_get_settings_unauthorized(self, client, session):
        """Test that unauthorized requests are rejected."""
        response = client.get("/api/ubuntu-pro/")
        assert response.status_code == 403

    def test_get_settings_creates_default_with_proper_timestamps(
        self, client, session, auth_headers
    ):
        """Test that default settings are created with proper timestamps when none exist."""
        response = client.get("/api/ubuntu-pro/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Verify the default settings structure
        assert data["id"] == 1
        assert data["master_key"] is None
        assert data["organization_name"] is None
        assert data["auto_attach_enabled"] is False
        assert "created_at" in data
        assert "updated_at" in data

        # Verify timestamps are present and properly formatted
        from datetime import datetime

        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        assert created_at is not None
        assert updated_at is not None


class TestUbuntuProSettingsUpdate:
    """Test cases for the PUT /api/ubuntu-pro/ endpoint."""

    def test_update_settings_success_existing(self, client, session, auth_headers):
        """Test successful update of existing Ubuntu Pro settings."""
        # Create existing settings
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1111111111111111111111111",
            organization_name="Old Organization",
            auto_attach_enabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test update
        update_data = {
            "master_key": "C2222222222222222222222222",
            "organization_name": "New Organization",
            "auto_attach_enabled": True,
        }

        response = client.put(
            "/api/ubuntu-pro/", headers=auth_headers, json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["master_key"] == "C2222222222222222222222222"
        assert data["organization_name"] == "New Organization"
        assert data["auto_attach_enabled"] is True

        # Verify database was updated
        updated_settings = session.query(models.UbuntuProSettings).first()
        assert updated_settings.master_key == "C2222222222222222222222222"
        assert updated_settings.organization_name == "New Organization"
        assert updated_settings.auto_attach_enabled is True

    def test_update_settings_creates_new_if_not_exists(
        self, client, session, auth_headers
    ):
        """Test that new settings are created if they don't exist."""
        # Ensure no settings exist
        assert session.query(models.UbuntuProSettings).count() == 0

        # Test update
        update_data = {
            "master_key": "C3333333333333333333333333",
            "organization_name": "New Organization",
            "auto_attach_enabled": True,
        }

        response = client.put(
            "/api/ubuntu-pro/", headers=auth_headers, json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["master_key"] == "C3333333333333333333333333"
        assert data["organization_name"] == "New Organization"
        assert data["auto_attach_enabled"] is True

        # Verify settings were created in database
        assert session.query(models.UbuntuProSettings).count() == 1

    def test_update_settings_partial_update(self, client, session, auth_headers):
        """Test partial update of settings."""
        # Create existing settings
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1111111111111111111111111",
            organization_name="Test Organization",
            auto_attach_enabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test partial update (only master key)
        update_data = {"master_key": "C4444444444444444444444444"}

        response = client.put(
            "/api/ubuntu-pro/", headers=auth_headers, json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["master_key"] == "C4444444444444444444444444"
        assert data["organization_name"] == "Test Organization"  # Unchanged
        assert data["auto_attach_enabled"] is False  # Unchanged

    def test_update_settings_clear_master_key(self, client, session, auth_headers):
        """Test clearing the master key by setting it to empty string."""
        # Create existing settings with master key
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1111111111111111111111111",
            organization_name="Test Organization",
            auto_attach_enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test clearing master key
        update_data = {"master_key": ""}

        response = client.put(
            "/api/ubuntu-pro/", headers=auth_headers, json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["master_key"] is None

    def test_update_settings_invalid_master_key(self, client, session, auth_headers):
        """Test validation of invalid master keys."""
        # Test key that doesn't start with 'C'
        update_data = {"master_key": "INVALID123456789012345"}

        response = client.put(
            "/api/ubuntu-pro/", headers=auth_headers, json=update_data
        )
        assert response.status_code == 422
        # FastAPI validation errors have a different structure
        error_detail = response.json()
        assert "detail" in error_detail

        # Test key that's too short
        update_data = {"master_key": "C123"}

        response = client.put(
            "/api/ubuntu-pro/", headers=auth_headers, json=update_data
        )
        assert response.status_code == 422
        error_detail = response.json()
        assert "detail" in error_detail

    def test_update_settings_invalid_organization_name(
        self, client, session, auth_headers
    ):
        """Test validation of organization name length."""
        update_data = {"organization_name": "x" * 256}  # Too long

        response = client.put(
            "/api/ubuntu-pro/", headers=auth_headers, json=update_data
        )
        assert response.status_code == 422
        error_detail = response.json()
        assert "detail" in error_detail

    def test_update_settings_unauthorized(self, client, session):
        """Test that unauthorized requests are rejected."""
        update_data = {"master_key": "C1234567890123456789012345"}

        response = client.put("/api/ubuntu-pro/", json=update_data)
        assert response.status_code == 403


class TestUbuntuProSettingsClearKey:
    """Test cases for the DELETE /api/ubuntu-pro/master-key endpoint."""

    def test_clear_master_key_success(self, client, session, auth_headers):
        """Test successful clearing of master key."""
        # Create settings with master key
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1234567890123456789012345",
            organization_name="Test Organization",
            auto_attach_enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test clear master key
        response = client.delete("/api/ubuntu-pro/master-key", headers=auth_headers)

        assert response.status_code == 200
        assert "Master key cleared successfully" in response.json()["message"]

        # Verify key was cleared in database
        updated_settings = session.query(models.UbuntuProSettings).first()
        assert updated_settings.master_key is None
        assert updated_settings.organization_name == "Test Organization"  # Unchanged

    def test_clear_master_key_no_settings(self, client, session, auth_headers):
        """Test clearing master key when no settings exist."""
        # Ensure no settings exist
        assert session.query(models.UbuntuProSettings).count() == 0

        # Test clear master key
        response = client.delete("/api/ubuntu-pro/master-key", headers=auth_headers)

        assert response.status_code == 200
        assert "No settings found to clear" in response.json()["message"]

    def test_clear_master_key_unauthorized(self, client, session):
        """Test that unauthorized requests are rejected."""
        response = client.delete("/api/ubuntu-pro/master-key")
        assert response.status_code == 403


class TestUbuntuProSettingsKeyStatus:
    """Test cases for the GET /api/ubuntu-pro/master-key/status endpoint."""

    def test_get_key_status_with_key(self, client, session, auth_headers):
        """Test getting key status when master key exists."""
        # Create settings with master key
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1234567890123456789012345",
            organization_name="Test Organization",
            auto_attach_enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test get key status
        response = client.get("/api/ubuntu-pro/master-key/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_master_key"] is True
        assert data["organization_name"] == "Test Organization"
        assert data["auto_attach_enabled"] is True

    def test_get_key_status_without_key(self, client, session, auth_headers):
        """Test getting key status when no master key exists."""
        # Create settings without master key
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key=None,
            organization_name=None,
            auto_attach_enabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test get key status
        response = client.get("/api/ubuntu-pro/master-key/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_master_key"] is False
        assert data["organization_name"] is None
        assert data["auto_attach_enabled"] is False

    def test_get_key_status_no_settings(self, client, session, auth_headers):
        """Test getting key status when no settings exist."""
        # Ensure no settings exist
        assert session.query(models.UbuntuProSettings).count() == 0

        # Test get key status
        response = client.get("/api/ubuntu-pro/master-key/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_master_key"] is False
        assert data["organization_name"] is None
        assert data["auto_attach_enabled"] is False


class TestUbuntuProEnrollment:
    """Test cases for the POST /api/ubuntu-pro/enroll endpoint."""

    def test_enroll_with_master_key_success(self, client, session, auth_headers):
        """Test successful enrollment using master key."""
        # Create Ubuntu Pro settings with master key
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1234567890123456789012345",
            organization_name="Test Organization",
            auto_attach_enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)

        # Create test hosts
        host1 = models.Host(id=1, active=True, fqdn="test1.example.com", status="up")
        host2 = models.Host(id=2, active=True, fqdn="test2.example.com", status="up")
        session.add(host1)
        session.add(host2)
        session.commit()

        # Mock WebSocket connection manager
        with patch(
            "backend.websocket.connection_manager.connection_manager.send_to_host"
        ) as mock_send, patch(
            "backend.websocket.messages.create_command_message"
        ) as mock_create_cmd:
            mock_send.return_value = None  # Simulate successful send
            mock_create_cmd.return_value = {"command": "ubuntu_pro_attach", "data": {}}

            # Test enrollment
            enrollment_data = {
                "host_ids": [1, 2],
                "use_master_key": True,
            }

            response = client.post(
                "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
            )

            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert len(data["results"]) == 2

            # Check results
            for result in data["results"]:
                assert result["success"] is True
                assert "Ubuntu Pro enrollment initiated" in result["message"]
                assert result["hostname"] in ["test1.example.com", "test2.example.com"]

            # Verify WebSocket calls were made
            assert mock_send.call_count == 2

    def test_enroll_with_custom_key_success(self, client, session, auth_headers):
        """Test successful enrollment using custom key."""
        # Create test host
        host = models.Host(id=1, active=True, fqdn="test.example.com", status="up")
        session.add(host)
        session.commit()

        # Mock WebSocket connection manager
        with patch(
            "backend.websocket.connection_manager.connection_manager.send_to_host"
        ) as mock_send, patch(
            "backend.websocket.messages.create_command_message"
        ) as mock_create_cmd:
            mock_send.return_value = None
            mock_create_cmd.return_value = {"command": "ubuntu_pro_attach", "data": {}}

            # Test enrollment with custom key
            enrollment_data = {
                "host_ids": [1],
                "use_master_key": False,
                "custom_key": "C9876543210987654321098765",
            }

            response = client.post(
                "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["results"][0]["success"] is True
            mock_send.assert_called_once()

    def test_enroll_no_master_key_configured(self, client, session, auth_headers):
        """Test enrollment failure when no master key is configured."""
        # Create test host
        host = models.Host(id=1, active=True, fqdn="test.example.com", status="up")
        session.add(host)
        session.commit()

        # Test enrollment without master key configured
        enrollment_data = {
            "host_ids": [1],
            "use_master_key": True,
        }

        response = client.post(
            "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
        )

        assert response.status_code == 400
        assert "No master key configured" in response.json()["detail"]

    def test_enroll_invalid_custom_key(self, client, session, auth_headers):
        """Test enrollment with invalid custom key."""
        # Test with key that doesn't start with 'C'
        enrollment_data = {
            "host_ids": [1],
            "use_master_key": False,
            "custom_key": "INVALID123",
        }

        response = client.post(
            "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
        )

        assert response.status_code == 422  # Validation error

    def test_enroll_missing_custom_key(self, client, session, auth_headers):
        """Test enrollment without custom key when not using master key."""
        enrollment_data = {
            "host_ids": [1],
            "use_master_key": False,
            # Missing custom_key
        }

        response = client.post(
            "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
        )

        assert response.status_code == 422  # Validation error

    def test_enroll_host_not_found(self, client, session, auth_headers):
        """Test enrollment with non-existent host."""
        # Create Ubuntu Pro settings
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1234567890123456789012345",
            organization_name="Test Organization",
            auto_attach_enabled=True,
            created_at=now,
            updated_at=now,
        )
        session.add(settings)
        session.commit()

        # Test enrollment with non-existent host
        enrollment_data = {
            "host_ids": [999],  # Non-existent host ID
            "use_master_key": True,
        }

        response = client.post(
            "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["success"] is False
        assert "Host not found or inactive" in data["results"][0]["error"]

    def test_enroll_websocket_connection_error(self, client, session, auth_headers):
        """Test enrollment when WebSocket connection fails."""
        # Create Ubuntu Pro settings and host
        now = datetime.now(timezone.utc)
        settings = models.UbuntuProSettings(
            id=1,
            master_key="C1234567890123456789012345",
            organization_name="Test Organization",
            auto_attach_enabled=True,
            created_at=now,
            updated_at=now,
        )
        host = models.Host(id=1, active=True, fqdn="test.example.com", status="up")
        session.add(settings)
        session.add(host)
        session.commit()

        # Mock WebSocket connection failure
        with patch(
            "backend.websocket.connection_manager.connection_manager.send_to_host"
        ) as mock_send, patch(
            "backend.websocket.messages.create_command_message"
        ) as mock_create_cmd:
            mock_send.side_effect = ConnectionError("Connection failed")
            mock_create_cmd.return_value = {"command": "ubuntu_pro_attach", "data": {}}

            # Test enrollment
            enrollment_data = {
                "host_ids": [1],
                "use_master_key": True,
            }

            response = client.post(
                "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
            )

            assert response.status_code == 200
            data = response.json()
            assert data["results"][0]["success"] is False
            assert "Failed to send enrollment command" in data["results"][0]["error"]

    def test_enroll_empty_host_ids(self, client, session, auth_headers):
        """Test enrollment with empty host_ids list."""
        enrollment_data = {
            "host_ids": [],  # Empty list
            "use_master_key": True,
        }

        response = client.post(
            "/api/ubuntu-pro/enroll", headers=auth_headers, json=enrollment_data
        )

        assert response.status_code == 422  # Validation error

    def test_enroll_unauthorized(self, client, session):
        """Test that unauthorized requests are rejected."""
        enrollment_data = {
            "host_ids": [1],
            "use_master_key": True,
        }

        response = client.post("/api/ubuntu-pro/enroll", json=enrollment_data)
        assert response.status_code == 403
