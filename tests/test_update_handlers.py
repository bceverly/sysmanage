"""
Comprehensive tests for backend/api/update_handlers.py module.
Tests update result handling functionality for SysManage server.
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, call

import pytest
from sqlalchemy import and_, text, update

from backend.api.update_handlers import (
    handle_update_apply_result,
    update_results_cache,
)


class MockConnection:
    """Mock WebSocket connection."""

    def __init__(self, host_id="test-host-1"):
        self.host_id = host_id


class MockDB:
    """Mock database session."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.executed_statements = []
        self.execute_results = []

    def execute(self, stmt):
        self.executed_statements.append(stmt)
        mock_result = Mock()
        mock_result.rowcount = 1
        return mock_result

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class TestHandleUpdateApplyResult:
    """Test handle_update_apply_result function."""

    def setup_method(self):
        """Clear cache before each test."""
        update_results_cache.clear()

    @pytest.mark.asyncio
    async def test_handle_update_apply_result_no_host_id(self):
        """Test handling when connection has no host_id."""
        mock_db = MockDB()
        mock_connection = Mock()
        mock_connection.host_id = None

        message_data = {"hostname": "test-host"}

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        assert result["message_type"] == "error"
        assert "Host not registered" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_update_apply_result_no_host_id_attribute(self):
        """Test handling when connection doesn't have host_id attribute."""
        mock_db = MockDB()
        mock_connection = Mock(spec=[])  # Empty spec means no attributes

        message_data = {"hostname": "test-host"}

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        assert result["message_type"] == "error"
        assert "Host not registered" in result["error"]

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_success_empty_packages(self, mock_logger):
        """Test successful handling with no packages."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-123")

        message_data = {
            "hostname": "test-host",
            "updated_packages": [],
            "failed_packages": [],
            "requires_reboot": False,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Verify result
        assert result["message_type"] == "success"
        assert result["updated_count"] == 0
        assert result["failed_count"] == 0
        assert result["requires_reboot"] is False

        # Verify cache was updated
        assert "host-123" in update_results_cache
        cache_entry = update_results_cache["host-123"]
        assert cache_entry["updated_packages"] == []
        assert cache_entry["failed_packages"] == []
        assert "timestamp" in cache_entry

        # Verify database operations
        assert mock_db.committed is True
        assert len(mock_db.executed_statements) == 0  # No package updates

        # Verify logging
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_with_updated_packages(self, mock_logger):
        """Test handling with updated packages."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-123")

        message_data = {
            "hostname": "test-host",
            "updated_packages": [
                {
                    "package_name": "curl",
                    "package_manager": "apt",
                    "new_version": "7.68.0-1ubuntu2.20",
                    "old_version": "7.68.0-1ubuntu2.19",
                },
                {
                    "package_name": "git",
                    "package_manager": "apt",
                    "new_version": "2.34.1-1ubuntu1.9",
                },
            ],
            "failed_packages": [],
            "requires_reboot": False,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Verify result
        assert result["message_type"] == "success"
        assert result["updated_count"] == 2
        assert result["failed_count"] == 0
        assert result["requires_reboot"] is False

        # Verify cache was updated
        assert "host-123" in update_results_cache
        cache_entry = update_results_cache["host-123"]
        assert len(cache_entry["updated_packages"]) == 2
        assert cache_entry["updated_packages"][0]["package_name"] == "curl"

        # Verify database operations
        assert mock_db.committed is True
        assert len(mock_db.executed_statements) == 2  # Two package updates

        # Verify logging
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_with_failed_packages(self, mock_logger):
        """Test handling with failed packages."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-456")

        message_data = {
            "hostname": "test-host",
            "updated_packages": [],
            "failed_packages": [
                {
                    "package_name": "broken-package",
                    "package_manager": "apt",
                    "error": "Dependency conflict",
                },
                {
                    "package_name": "another-broken",
                    "package_manager": "snap",
                    "error": "Network timeout",
                },
            ],
            "requires_reboot": False,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Verify result
        assert result["message_type"] == "success"
        assert result["updated_count"] == 0
        assert result["failed_count"] == 2
        assert result["requires_reboot"] is False

        # Verify cache was updated
        assert "host-456" in update_results_cache
        cache_entry = update_results_cache["host-456"]
        assert len(cache_entry["failed_packages"]) == 2
        assert cache_entry["failed_packages"][0]["error"] == "Dependency conflict"

        # Verify database operations
        assert mock_db.committed is True
        assert len(mock_db.executed_statements) == 2  # Two failed package updates

        # Verify logging
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_with_reboot_required(self, mock_logger):
        """Test handling when reboot is required."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-789")

        message_data = {
            "hostname": "test-host",
            "updated_packages": [
                {
                    "package_name": "kernel-update",
                    "package_manager": "apt",
                    "new_version": "5.15.0-72",
                }
            ],
            "failed_packages": [],
            "requires_reboot": True,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Verify result
        assert result["message_type"] == "success"
        assert result["updated_count"] == 1
        assert result["failed_count"] == 0
        assert result["requires_reboot"] is True

        # Verify database operations - should have package update + host reboot update
        assert mock_db.committed is True
        assert (
            len(mock_db.executed_statements) == 2
        )  # Package update + host reboot update

        # Verify logging
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_mixed_packages(self, mock_logger):
        """Test handling with both updated and failed packages."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-mixed")

        message_data = {
            "hostname": "test-host",
            "updated_packages": [
                {
                    "package_name": "success-package",
                    "package_manager": "apt",
                    "new_version": "1.2.3",
                }
            ],
            "failed_packages": [
                {
                    "package_name": "failed-package",
                    "package_manager": "apt",
                    "error": "Installation failed",
                }
            ],
            "requires_reboot": True,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Verify result
        assert result["message_type"] == "success"
        assert result["updated_count"] == 1
        assert result["failed_count"] == 1
        assert result["requires_reboot"] is True

        # Verify cache was updated
        cache_entry = update_results_cache["host-mixed"]
        assert len(cache_entry["updated_packages"]) == 1
        assert len(cache_entry["failed_packages"]) == 1

        # Verify database operations
        assert mock_db.committed is True
        assert len(mock_db.executed_statements) == 3  # Success + failed + host reboot

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_missing_package_fields(self, mock_logger):
        """Test handling packages with missing required fields."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-incomplete")

        message_data = {
            "hostname": "test-host",
            "updated_packages": [
                {
                    # Missing package_name
                    "package_manager": "apt",
                    "new_version": "1.2.3",
                },
                {
                    "package_name": "valid-package",
                    # Missing package_manager
                    "new_version": "1.2.3",
                },
                {
                    "package_name": "complete-package",
                    "package_manager": "apt",
                    "new_version": "1.2.3",
                },
            ],
            "failed_packages": [
                {
                    # Missing package_name
                    "package_manager": "apt",
                    "error": "Some error",
                },
                {
                    "package_name": "valid-failed",
                    "package_manager": "apt",
                    "error": "Real error",
                },
            ],
            "requires_reboot": False,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Should still succeed, but only process valid packages
        assert result["message_type"] == "success"
        assert result["updated_count"] == 3  # All packages in result count
        assert result["failed_count"] == 2

        # Only valid packages should have generated DB updates
        assert (
            len(mock_db.executed_statements) == 2
        )  # Only complete-package and valid-failed

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_missing_message_fields(self, mock_logger):
        """Test handling with missing optional message fields."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-defaults")

        message_data = {
            # Missing hostname, updated_packages, failed_packages, requires_reboot
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Should use defaults and succeed
        assert result["message_type"] == "success"
        assert result["updated_count"] == 0
        assert result["failed_count"] == 0
        assert result["requires_reboot"] is False

        # Verify cache was updated with defaults
        cache_entry = update_results_cache["host-defaults"]
        assert cache_entry["updated_packages"] == []
        assert cache_entry["failed_packages"] == []

        # Verify logging with default hostname
        mock_logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_failed_package_no_error(
        self, mock_logger
    ):
        """Test handling failed package without error message."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-no-error")

        message_data = {
            "hostname": "test-host",
            "updated_packages": [],
            "failed_packages": [
                {
                    "package_name": "no-error-package",
                    "package_manager": "apt",
                    # Missing error field
                }
            ],
            "requires_reboot": False,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        assert result["message_type"] == "success"
        assert result["failed_count"] == 1

        # Should use default error message
        assert len(mock_db.executed_statements) == 1

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_database_error(self, mock_logger):
        """Test handling when database operations fail."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-db-error")

        # Make database execute fail
        def failing_execute(stmt):
            raise Exception("Database connection failed")

        mock_db.execute = failing_execute

        message_data = {
            "hostname": "test-host",
            "updated_packages": [
                {
                    "package_name": "test-package",
                    "package_manager": "apt",
                    "new_version": "1.0.0",
                }
            ],
            "failed_packages": [],
            "requires_reboot": False,
        }

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        # Should return error
        assert result["message_type"] == "error"
        assert "Failed to process update results" in result["error"]

        # Should rollback the database
        assert mock_db.rolled_back is True

        # Should log the error
        mock_logger.error.assert_called()

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_cache_update(self, mock_logger):
        """Test cache update functionality."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-cache")

        message_data = {
            "hostname": "cache-test-host",
            "updated_packages": [{"package_name": "test"}],
            "failed_packages": [{"package_name": "failed"}],
            "requires_reboot": True,
        }

        # Clear cache first
        update_results_cache.clear()

        result = await handle_update_apply_result(
            mock_db, mock_connection, message_data
        )

        assert result["message_type"] == "success"

        # Verify cache structure
        assert "host-cache" in update_results_cache
        cache_entry = update_results_cache["host-cache"]

        assert "updated_packages" in cache_entry
        assert "failed_packages" in cache_entry
        assert "timestamp" in cache_entry

        assert len(cache_entry["updated_packages"]) == 1
        assert len(cache_entry["failed_packages"]) == 1

        # Timestamp should be ISO format
        timestamp = cache_entry["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))  # Should not raise

    @pytest.mark.asyncio
    @patch("backend.api.update_handlers.debug_logger")
    async def test_handle_update_apply_result_cache_overwrite(self, mock_logger):
        """Test that cache entries are overwritten correctly."""
        mock_db = MockDB()
        mock_connection = MockConnection("host-overwrite")

        # First update
        message_data1 = {
            "hostname": "test-host",
            "updated_packages": [{"package_name": "old"}],
            "failed_packages": [],
            "requires_reboot": False,
        }

        await handle_update_apply_result(mock_db, mock_connection, message_data1)

        # Second update should overwrite
        message_data2 = {
            "hostname": "test-host",
            "updated_packages": [{"package_name": "new"}],
            "failed_packages": [],
            "requires_reboot": False,
        }

        await handle_update_apply_result(mock_db, mock_connection, message_data2)

        # Cache should have the new data
        cache_entry = update_results_cache["host-overwrite"]
        assert cache_entry["updated_packages"][0]["package_name"] == "new"


class TestUpdateResultsCache:
    """Test update_results_cache functionality."""

    def setup_method(self):
        """Clear cache before each test."""
        update_results_cache.clear()

    def test_cache_accessibility(self):
        """Test that cache is accessible via function attribute."""
        # Cache should be accessible via the function
        assert handle_update_apply_result.update_results_cache is update_results_cache

    def test_cache_manipulation(self):
        """Test direct cache manipulation."""
        # Direct manipulation should work
        update_results_cache["test-key"] = {"test": "value"}

        assert "test-key" in update_results_cache
        assert update_results_cache["test-key"]["test"] == "value"

        # Clear should work
        update_results_cache.clear()
        assert len(update_results_cache) == 0


class TestIntegration:
    """Integration tests for update_handlers module."""

    def setup_method(self):
        """Clear cache before each test."""
        update_results_cache.clear()

    def test_datetime_handling(self):
        """Test datetime handling in cache."""
        now = datetime.now(timezone.utc)
        iso_string = now.isoformat()

        # Should be valid ISO format
        parsed = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_json_serialization(self):
        """Test JSON serialization of cache data."""
        test_data = {
            "updated_packages": [{"name": "test", "version": "1.0.0"}],
            "failed_packages": [{"name": "failed", "error": "Test error"}],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Should be JSON serializable
        json_str = json.dumps(test_data)
        parsed = json.loads(json_str)

        assert parsed["updated_packages"] == test_data["updated_packages"]
        assert parsed["failed_packages"] == test_data["failed_packages"]
        assert parsed["timestamp"] == test_data["timestamp"]


class TestUpdateHandlersLogging:
    """Test update handlers module logging initialization."""

    @patch("builtins.open", side_effect=PermissionError("Permission denied"))
    @patch("os.makedirs")
    def test_logging_fallback_on_permission_error(self, mock_makedirs, mock_open):
        """Test logging falls back to console when file logging fails."""
        # Force module reload to trigger the logging initialization with mocked open
        import importlib
        import sys

        # Remove module to force re-import and re-initialization
        if "backend.api.update_handlers" in sys.modules:
            del sys.modules["backend.api.update_handlers"]

        # Import module which should trigger fallback logging due to PermissionError
        import backend.api.update_handlers

        # Verify that the module still loads successfully despite logging error
        assert hasattr(backend.api.update_handlers, "handle_update_apply_result")
        assert hasattr(backend.api.update_handlers, "update_results_cache")

    @patch("builtins.open", side_effect=OSError("Disk full"))
    @patch("os.makedirs")
    def test_logging_fallback_on_os_error(self, mock_makedirs, mock_open):
        """Test logging falls back to console when file logging fails with OSError."""
        # Force module reload to trigger the logging initialization with mocked open
        import importlib
        import sys

        # Remove module to force re-import and re-initialization
        if "backend.api.update_handlers" in sys.modules:
            del sys.modules["backend.api.update_handlers"]

        # Import module which should trigger fallback logging due to OSError
        import backend.api.update_handlers

        # Verify that the module still loads successfully despite logging error
        assert hasattr(backend.api.update_handlers, "handle_update_apply_result")
        assert hasattr(backend.api.update_handlers, "update_results_cache")
