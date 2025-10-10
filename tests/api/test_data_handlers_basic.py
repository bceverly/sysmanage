"""
Fixed basic tests for data handlers focusing on core functionality.
Tests basic operations with correct function signatures and behavior.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from backend.api.handlers import (
    is_new_os_version_combination,
    handle_os_version_update,
    handle_reboot_status_update,
)
from backend.api.handlers.user_access_handlers import (
    _create_user_account_with_security_id,
    _create_user_group_with_security_id,
)


class TestOSVersionCombination:
    """Test OS version combination checking."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        query_mock = Mock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        return db

    @pytest.mark.asyncio
    async def test_is_new_os_version_combination_true(self, mock_db):
        """Test when OS combination is new."""
        # Mock no existing packages found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await is_new_os_version_combination(mock_db, "Ubuntu", "22.04")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_new_os_version_combination_false(self, mock_db):
        """Test when OS combination exists."""
        # Mock existing package found
        mock_package = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_package

        result = await is_new_os_version_combination(mock_db, "Ubuntu", "22.04")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_new_os_version_combination_empty_inputs(self, mock_db):
        """Test with empty inputs."""
        result = await is_new_os_version_combination(mock_db, "", "")
        assert result is False

        result = await is_new_os_version_combination(mock_db, None, None)
        assert result is False


class TestBasicDataHandlers:
    """Test basic data handler functionality."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.query.return_value = Mock()
        db.commit = Mock()
        db.add = Mock()
        return db

    @pytest.fixture
    def mock_connection(self):
        connection = Mock()
        connection.host_id = "test-host-123"
        connection.hostname = "test-host.example.com"
        return connection

    @pytest.mark.asyncio
    async def test_handle_os_version_update_with_host_id(
        self, mock_db, mock_connection
    ):
        """Test OS version update with valid host_id."""
        message_data = {"platform": "Linux", "platform_release": "22.04"}

        # Mock host found
        mock_host = Mock()
        mock_host.id = "test-host-123"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch(
            "backend.utils.host_validation.validate_host_id"
        ) as mock_validate, patch(
            "backend.api.handlers.is_new_os_version_combination"
        ) as mock_is_new, patch(
            "backend.api.handlers.handle_ubuntu_pro_update"
        ) as mock_ubuntu_pro:

            mock_validate.return_value = True
            mock_is_new.return_value = False
            mock_ubuntu_pro.return_value = None

            result = await handle_os_version_update(
                mock_db, mock_connection, message_data
            )

            # Verify host attributes were set
            assert mock_host.platform == "Linux"
            assert mock_host.platform_release == "22.04"
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_reboot_status_basic(self, mock_db, mock_connection):
        """Test basic reboot status handling."""
        message_data = {
            "hostname": "test-host.example.com",
            "reboot_required": True,
            "packages_requiring_reboot": ["kernel-image", "systemd"],
        }

        # Mock host found with proper setup
        mock_host = Mock()
        mock_host.id = "test-host-123"
        mock_host.reboot_required = None  # Initial value
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host

        with patch("backend.utils.host_validation.validate_host_id") as mock_validate:
            mock_validate.return_value = True

            result = await handle_reboot_status_update(
                mock_db, mock_connection, message_data
            )

            # Verify reboot status was updated
            assert mock_host.reboot_required == True
            mock_db.commit.assert_called_once()
            assert result["message_type"] == "reboot_status_updated"

    def test_create_user_account_with_security_id(self):
        """Test user account creation with security ID."""
        mock_connection = Mock()
        user_data = {"username": "testuser", "uid": 1001}
        now = datetime.now(timezone.utc)

        result = _create_user_account_with_security_id(mock_connection, user_data, now)

        # Should return user account object
        assert result is not None
        assert hasattr(result, "username")
        assert result.username == "testuser"
        assert result.uid == 1001

    def test_create_user_group_with_security_id(self):
        """Test user group creation with security ID."""
        mock_connection = Mock()
        group_data = {"group_name": "testgroup", "gid": 1001}
        now = datetime.now(timezone.utc)

        result = _create_user_group_with_security_id(mock_connection, group_data, now)

        # Should return user group object
        assert result is not None
        assert hasattr(result, "group_name")
        assert result.group_name == "testgroup"
        assert result.gid == 1001


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.rollback = Mock()
        return db

    @pytest.fixture
    def mock_connection(self):
        connection = Mock()
        return connection

    @pytest.mark.asyncio
    async def test_handle_os_version_update_no_host_identification(
        self, mock_db, mock_connection
    ):
        """Test OS version update with no host identification."""
        message_data = {"platform": "Linux"}

        # Remove all host identification attributes
        for attr in ["hostname", "ipv4", "websocket", "host_id"]:
            if hasattr(mock_connection, attr):
                delattr(mock_connection, attr)

        result = await handle_os_version_update(mock_db, mock_connection, message_data)

        # Should return error
        assert result["message_type"] == "error"
        assert "error" in result
