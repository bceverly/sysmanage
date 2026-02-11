"""
Tests for backend/utils/host_validation.py module.
Tests host validation utilities for SysManage server.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.utils.host_validation import validate_host_id


class TestValidateHostId:
    """Tests for validate_host_id function."""

    @pytest.mark.asyncio
    async def test_validate_host_id_empty(self):
        """Test that empty host_id returns True (no validation needed)."""
        mock_db = MagicMock()
        mock_connection = MagicMock()

        result = await validate_host_id(mock_db, mock_connection, "", None)

        assert result is True
        # Should not query database
        mock_db.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_host_id_none(self):
        """Test that None host_id returns True (no validation needed)."""
        mock_db = MagicMock()
        mock_connection = MagicMock()

        result = await validate_host_id(mock_db, mock_connection, None, None)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_host_id_found_by_id(self):
        """Test that host found by ID returns True."""
        mock_host = MagicMock()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_host
        mock_connection = MagicMock()

        result = await validate_host_id(mock_db, mock_connection, "test-host-id", None)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_host_id_found_by_hostname(self):
        """Test that host found by hostname returns True."""
        mock_host = MagicMock()
        mock_db = MagicMock()
        # First query (by ID) returns None, second query (by hostname) returns host
        mock_filter = MagicMock()
        mock_filter.first.side_effect = [None, mock_host]
        mock_db.query.return_value.filter.return_value = mock_filter
        mock_connection = MagicMock()

        result = await validate_host_id(
            mock_db, mock_connection, "wrong-host-id", "correct-hostname"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_host_id_not_found(self):
        """Test that missing host returns False and sends error message."""
        mock_db = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        mock_db.query.return_value.filter.return_value = mock_filter

        mock_connection = MagicMock()
        mock_connection.send_message = AsyncMock()

        result = await validate_host_id(
            mock_db, mock_connection, "missing-host-id", None
        )

        assert result is False
        mock_connection.send_message.assert_called_once()

        # Verify error message structure
        call_args = mock_connection.send_message.call_args[0][0]
        assert call_args["message_type"] == "error"
        assert call_args["error_type"] == "host_not_registered"
        assert "missing-host-id" in call_args["data"]["host_id"]

    @pytest.mark.asyncio
    async def test_validate_host_id_not_found_with_hostname(self):
        """Test that host not found by ID or hostname returns False."""
        mock_db = MagicMock()
        mock_filter = MagicMock()
        # Both queries return None
        mock_filter.first.side_effect = [None, None]
        mock_db.query.return_value.filter.return_value = mock_filter

        mock_connection = MagicMock()
        mock_connection.send_message = AsyncMock()

        result = await validate_host_id(
            mock_db, mock_connection, "missing-host-id", "unknown-hostname"
        )

        assert result is False
        mock_connection.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_host_id_error_message_content(self):
        """Test that error message contains correct host ID."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_connection = MagicMock()
        mock_connection.send_message = AsyncMock()

        host_id = "specific-host-123"
        await validate_host_id(mock_db, mock_connection, host_id, None)

        call_args = mock_connection.send_message.call_args[0][0]
        assert host_id in call_args["message"]
        assert call_args["data"]["host_id"] == host_id
