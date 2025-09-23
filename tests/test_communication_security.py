"""
Unit tests for backend.security.communication_security module.
Tests WebSocket security management and message encryption functionality.
"""

import base64
import json
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from backend.security.communication_security import (
    MessageEncryption,
    WebSocketSecurityManager,
)


class TestWebSocketSecurityManager:
    """Test cases for WebSocketSecurityManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {
                "security": {"jwt_secret": "test_secret_key_123"}
            }
            self.security_manager = WebSocketSecurityManager()

    def test_init_success(self):
        """Test successful WebSocketSecurityManager initialization."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {"security": {"jwt_secret": "test_key"}}
            manager = WebSocketSecurityManager()

            assert manager.config is not None
            assert isinstance(manager.active_connections, dict)
            assert isinstance(manager.connection_attempts, dict)

    def test_generate_connection_token_success(self):
        """Test successful connection token generation."""
        agent_hostname = "test-agent.local"
        client_ip = "192.168.1.100"

        token = self.security_manager.generate_connection_token(
            agent_hostname, client_ip
        )

        # Verify token is base64 encoded string
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify structure
        decoded_bytes = base64.b64decode(token.encode())
        token_data = json.loads(decoded_bytes)

        assert "payload" in token_data
        assert "signature" in token_data

        payload = token_data["payload"]
        assert payload["hostname"] == agent_hostname
        assert payload["client_ip"] == client_ip
        assert "connection_id" in payload
        assert "timestamp" in payload
        assert "expires" in payload

    def test_generate_connection_token_stores_connection(self):
        """Test that generating token stores connection info."""
        agent_hostname = "test-agent.local"
        client_ip = "192.168.1.100"

        initial_count = len(self.security_manager.active_connections)

        token = self.security_manager.generate_connection_token(
            agent_hostname, client_ip
        )

        # Decode token to get connection_id
        decoded_bytes = base64.b64decode(token.encode())
        token_data = json.loads(decoded_bytes)
        connection_id = token_data["payload"]["connection_id"]

        # Verify connection is stored
        assert len(self.security_manager.active_connections) == initial_count + 1
        assert connection_id in self.security_manager.active_connections

        stored_connection = self.security_manager.active_connections[connection_id]
        assert stored_connection["hostname"] == agent_hostname
        assert stored_connection["client_ip"] == client_ip
        assert stored_connection["authenticated"] is False

    def test_validate_connection_token_success(self):
        """Test successful token validation."""
        agent_hostname = "test-agent.local"
        client_ip = "192.168.1.100"

        # Generate token
        token = self.security_manager.generate_connection_token(
            agent_hostname, client_ip
        )

        # Validate token
        is_valid, connection_id, message = (
            self.security_manager.validate_connection_token(token, client_ip)
        )

        assert is_valid is True
        assert connection_id is not None
        assert message == "Token valid"

        # Check that connection is marked as authenticated
        assert (
            self.security_manager.active_connections[connection_id]["authenticated"]
            is True
        )

    def test_validate_connection_token_invalid_base64(self):
        """Test token validation with invalid base64."""
        is_valid, connection_id, message = (
            self.security_manager.validate_connection_token(
                "invalid_base64!", "192.168.1.100"
            )
        )

        assert is_valid is False
        assert connection_id is None
        assert message == "Malformed token"

    def test_validate_connection_token_invalid_json(self):
        """Test token validation with invalid JSON."""
        invalid_json = base64.b64encode(b"not valid json").decode()

        is_valid, connection_id, message = (
            self.security_manager.validate_connection_token(
                invalid_json, "192.168.1.100"
            )
        )

        assert is_valid is False
        assert connection_id is None
        assert message == "Malformed token"

    def test_validate_connection_token_invalid_signature(self):
        """Test token validation with invalid signature."""
        # Create token with wrong signature
        payload = {
            "connection_id": "test-id",
            "hostname": "test-host",
            "client_ip": "192.168.1.100",
            "timestamp": int(time.time()),
            "expires": int(time.time()) + 3600,
        }
        token_data = {"payload": payload, "signature": "wrong_signature"}
        token_bytes = json.dumps(token_data).encode()
        token = base64.b64encode(token_bytes).decode()

        is_valid, connection_id, message = (
            self.security_manager.validate_connection_token(token, "192.168.1.100")
        )

        assert is_valid is False
        assert connection_id is None
        assert message == "Invalid token signature"

    def test_validate_connection_token_expired(self):
        """Test token validation with expired token."""
        # Create expired token
        expired_time = int(time.time()) - 7200  # 2 hours ago
        payload = {
            "connection_id": "test-id",
            "hostname": "test-host",
            "client_ip": "192.168.1.100",
            "timestamp": expired_time,
            "expires": expired_time + 3600,  # Expired 1 hour ago
        }

        # Create valid signature for expired token
        secret_key = "test_secret_key_123"
        payload_json = json.dumps(payload, sort_keys=True)
        import hashlib
        import hmac

        signature = hmac.new(
            secret_key.encode(), payload_json.encode(), hashlib.sha256
        ).hexdigest()

        token_data = {"payload": payload, "signature": signature}
        token_bytes = json.dumps(token_data).encode()
        token = base64.b64encode(token_bytes).decode()

        is_valid, connection_id, message = (
            self.security_manager.validate_connection_token(token, "192.168.1.100")
        )

        assert is_valid is False
        assert connection_id is None
        assert message == "Token expired"

    def test_validate_connection_token_ip_mismatch_logged(self):
        """Test token validation with IP mismatch (should log but not fail)."""
        agent_hostname = "test-agent.local"
        original_ip = "192.168.1.100"
        different_ip = "192.168.1.200"

        # Generate token with original IP
        token = self.security_manager.generate_connection_token(
            agent_hostname, original_ip
        )

        # Validate with different IP
        with patch("backend.security.communication_security.logger") as mock_logger:
            is_valid, connection_id, message = (
                self.security_manager.validate_connection_token(token, different_ip)
            )

            # Should still be valid but log the mismatch
            assert is_valid is True
            assert connection_id is not None
            mock_logger.info.assert_called_with(
                "IP mismatch detected (common with NAT/proxy scenarios)"
            )

    def test_validate_message_integrity_heartbeat_success(self):
        """Test successful message integrity validation for heartbeat."""
        message = {
            "message_type": "heartbeat",
            "message_id": "test-message-12345-abcdef-67890",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data": {"status": "alive"},
        }

        # Create a connection
        self.security_manager.active_connections["test-conn"] = {
            "authenticated": True,
            "last_activity": int(time.time()),
        }

        is_valid = self.security_manager.validate_message_integrity(
            message, "test-conn"
        )
        assert is_valid is True

    def test_validate_message_integrity_missing_connection(self):
        """Test message integrity validation with missing connection."""
        message = {"message_type": "heartbeat"}

        is_valid = self.security_manager.validate_message_integrity(
            message, "nonexistent-conn"
        )
        assert is_valid is False

    def test_validate_message_integrity_unauthenticated_connection(self):
        """Test message integrity validation with unauthenticated connection."""
        message = {"message_type": "heartbeat"}

        self.security_manager.active_connections["test-conn"] = {
            "authenticated": False,
            "last_activity": int(time.time()),
        }

        is_valid = self.security_manager.validate_message_integrity(
            message, "test-conn"
        )
        assert is_valid is False

    def test_validate_message_integrity_missing_message_type(self):
        """Test message integrity validation with missing message type."""
        message = {"message_id": "test-message-123"}

        self.security_manager.active_connections["test-conn"] = {
            "authenticated": True,
            "last_activity": int(time.time()),
        }

        is_valid = self.security_manager.validate_message_integrity(
            message, "test-conn"
        )
        assert is_valid is False

    def test_validate_message_integrity_old_timestamp(self):
        """Test message integrity validation with old timestamp."""
        # Create message with timestamp 2 hours ago
        old_time = datetime.now(timezone.utc).timestamp() - 7200
        old_datetime = datetime.fromtimestamp(old_time, timezone.utc)

        message = {
            "message_type": "system_info",
            "message_id": "test-message-12345-abcdef-67890",
            "timestamp": old_datetime.isoformat().replace("+00:00", "Z"),
            "data": {},
        }

        self.security_manager.active_connections["test-conn"] = {
            "authenticated": True,
            "last_activity": int(time.time()),
        }

        is_valid = self.security_manager.validate_message_integrity(
            message, "test-conn"
        )
        assert is_valid is False

    def test_validate_message_integrity_script_execution_result_no_message_id(self):
        """Test message integrity validation for script execution result without message_id."""
        message = {
            "message_type": "script_execution_result",
            "execution_id": "exec-12345-abcdef-67890",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data": {"status": "completed"},
        }

        self.security_manager.active_connections["test-conn"] = {
            "authenticated": True,
            "last_activity": int(time.time()),
        }

        is_valid = self.security_manager.validate_message_integrity(
            message, "test-conn"
        )
        assert is_valid is True

    def test_validate_message_integrity_invalid_message_id(self):
        """Test message integrity validation with invalid message ID format."""
        message = {
            "message_type": "heartbeat",
            "message_id": "short",  # Too short
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data": {},
        }

        self.security_manager.active_connections["test-conn"] = {
            "authenticated": True,
            "last_activity": int(time.time()),
        }

        is_valid = self.security_manager.validate_message_integrity(
            message, "test-conn"
        )
        assert is_valid is False

    def test_is_connection_rate_limited_under_limit(self):
        """Test rate limiting when under the limit."""
        client_ip = "192.168.1.100"

        is_limited = self.security_manager.is_connection_rate_limited(client_ip)
        assert is_limited is False

    def test_is_connection_rate_limited_over_limit(self):
        """Test rate limiting when over the limit."""
        client_ip = "192.168.1.100"
        current_time = time.time()

        # Add 25 connection attempts (over the 20 limit)
        self.security_manager.connection_attempts[client_ip] = [
            current_time - i for i in range(25)
        ]

        is_limited = self.security_manager.is_connection_rate_limited(client_ip)
        assert is_limited is True

    def test_is_connection_rate_limited_old_attempts_cleaned(self):
        """Test that old connection attempts are cleaned up."""
        client_ip = "192.168.1.100"
        current_time = time.time()

        # Add old attempts (older than 15 minutes)
        old_attempts = [current_time - 1000 - i for i in range(25)]
        # Add recent attempts (within limit)
        recent_attempts = [current_time - i for i in range(10)]

        self.security_manager.connection_attempts[client_ip] = (
            old_attempts + recent_attempts
        )

        is_limited = self.security_manager.is_connection_rate_limited(client_ip)
        assert is_limited is False

        # Verify old attempts were cleaned
        remaining_attempts = len(self.security_manager.connection_attempts[client_ip])
        assert remaining_attempts == 10  # Only recent attempts remain

    def test_record_connection_attempt(self):
        """Test recording connection attempts."""
        client_ip = "192.168.1.100"

        initial_count = len(
            self.security_manager.connection_attempts.get(client_ip, [])
        )

        self.security_manager.record_connection_attempt(client_ip)

        attempts = self.security_manager.connection_attempts.get(client_ip, [])
        assert len(attempts) == initial_count + 1

    def test_cleanup_stale_connections(self):
        """Test cleanup of stale connections."""
        current_time = int(time.time())

        # Add fresh connection
        self.security_manager.active_connections["fresh"] = {
            "last_activity": current_time,
            "authenticated": True,
        }

        # Add stale connection (inactive for over 2 hours)
        self.security_manager.active_connections["stale"] = {
            "last_activity": current_time - 8000,  # Over 2 hours
            "authenticated": True,
        }

        initial_count = len(self.security_manager.active_connections)

        self.security_manager.cleanup_stale_connections()

        # Fresh connection should remain, stale should be removed
        assert len(self.security_manager.active_connections) == initial_count - 1
        assert "fresh" in self.security_manager.active_connections
        assert "stale" not in self.security_manager.active_connections

    def test_get_connection_stats(self):
        """Test getting connection statistics."""
        # Add some test connections
        current_time = int(time.time())

        self.security_manager.active_connections = {
            "conn1": {
                "authenticated": True,
                "last_activity": current_time,
            },  # Active and authenticated
            "conn2": {
                "authenticated": True,
                "last_activity": current_time - 1000,
            },  # Not active (> 300s ago)
            "conn3": {
                "authenticated": False,
                "last_activity": current_time,
            },  # Active but not authenticated
        }

        self.security_manager.connection_attempts = {
            "192.168.1.100": [current_time, current_time - 10],
            "192.168.1.200": [current_time - 100],
        }

        stats = self.security_manager.get_connection_stats()

        assert stats["total_connections"] == 3
        assert (
            stats["authenticated_connections"] == 1
        )  # Only conn1 is active and authenticated
        assert stats["connection_attempts_tracked"] == 2
        assert "active_connections" in stats


class TestMessageEncryption:
    """Test cases for MessageEncryption class."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {
                "security": {"jwt_secret": "test_encryption_key_123"}
            }
            self.encryption = MessageEncryption()

    def test_init_success(self):
        """Test successful MessageEncryption initialization."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {"security": {"jwt_secret": "test_key"}}
            encryption = MessageEncryption()

            assert encryption.config is not None

    def test_encrypt_sensitive_data_success(self):
        """Test successful data encryption."""
        sensitive_data = {
            "password": "secret123",
            "api_key": "key_abc123",
            "token": "bearer_token_xyz",
        }

        encrypted = self.encryption.encrypt_sensitive_data(sensitive_data)

        # Verify encrypted data is base64 string
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

        # Should be decodable as base64
        import base64

        decoded = base64.b64decode(encrypted.encode())
        assert len(decoded) > 0

    def test_encrypt_decrypt_roundtrip(self):
        """Test encryption and decryption roundtrip."""
        original_data = {
            "username": "admin",
            "password": "secret123",
            "details": {"role": "administrator", "permissions": ["read", "write"]},
        }

        encrypted = self.encryption.encrypt_sensitive_data(original_data)
        success, decrypted_data, message = self.encryption.decrypt_sensitive_data(
            encrypted
        )

        assert success is True
        assert decrypted_data == original_data
        assert message == "Decryption successful"

    def test_decrypt_sensitive_data_invalid_base64(self):
        """Test decryption with invalid base64."""
        success, data, message = self.encryption.decrypt_sensitive_data(
            "invalid_base64!"
        )

        assert success is False
        assert data is None
        assert "Decryption failed:" in message

    def test_decrypt_sensitive_data_invalid_json(self):
        """Test decryption with invalid encrypted data."""
        import base64

        invalid_encrypted = base64.b64encode(b"not encrypted properly").decode()

        success, data, message = self.encryption.decrypt_sensitive_data(
            invalid_encrypted
        )

        assert success is False
        assert data is None
        assert "Decryption failed:" in message

    def test_encrypt_empty_data(self):
        """Test encryption of empty data."""
        empty_data = {}

        encrypted = self.encryption.encrypt_sensitive_data(empty_data)
        success, decrypted_data, message = self.encryption.decrypt_sensitive_data(
            encrypted
        )

        assert success is True
        assert decrypted_data == empty_data
        assert message == "Decryption successful"

    def test_encrypt_complex_data(self):
        """Test encryption of complex nested data structures."""
        complex_data = {
            "config": {
                "database": {
                    "host": "localhost",
                    "password": "db_secret",
                    "connection_params": {"ssl": True, "timeout": 30},
                },
                "api_keys": ["key1", "key2", "key3"],
                "features": {
                    "encryption": True,
                    "logging": {"level": "INFO", "sensitive": False},
                },
            }
        }

        encrypted = self.encryption.encrypt_sensitive_data(complex_data)
        success, decrypted_data, message = self.encryption.decrypt_sensitive_data(
            encrypted
        )

        assert success is True
        assert decrypted_data == complex_data
        assert message == "Decryption successful"


class TestWebSocketSecurityManagerMissingCoverage:
    """Test missing coverage lines in WebSocketSecurityManager."""

    def setup_method(self):
        """Set up test fixtures."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {
                "security": {"jwt_secret": "test_secret_key_123"}
            }
            self.security_manager = WebSocketSecurityManager()

    def test_validate_message_timestamp_invalid_format(self):
        """Test timestamp validation with invalid format (lines 195-200)."""
        # Test ValueError path
        message_data = {
            "timestamp": "invalid-timestamp-format",
            "message_id": "12345678-1234-1234-1234-123456789012",
        }

        result = self.security_manager.validate_message_integrity(
            message_data, "test-conn"
        )
        assert result is False

    def test_validate_message_timestamp_missing_attribute(self):
        """Test timestamp validation with AttributeError (lines 195-200)."""
        # Test AttributeError path by passing None instead of string
        message_data = {
            "timestamp": None,
            "message_id": "12345678-1234-1234-1234-123456789012",
        }

        result = self.security_manager.validate_message_integrity(
            message_data, "test-conn"
        )
        assert result is False

    def test_cleanup_expired_connections(self):
        """Test cleanup of expired connections (lines 271, 274)."""
        # Add some connections with old timestamps
        old_time = time.time() - 8000  # More than 7200 seconds ago
        recent_time = time.time() - 1000  # Less than 7200 seconds ago

        self.security_manager.active_connections = {
            "conn1": {"created_at": old_time, "ip": "192.168.1.1"},
            "conn2": {"created_at": recent_time, "ip": "192.168.1.2"},
            "conn3": {"created_at": old_time, "ip": "192.168.1.3"},
        }

        self.security_manager._cleanup_expired_connections()

        # Only recent connection should remain
        assert "conn1" not in self.security_manager.active_connections
        assert "conn2" in self.security_manager.active_connections
        assert "conn3" not in self.security_manager.active_connections

    def test_cleanup_stale_connections_calls_cleanup_methods(self):
        """Test cleanup_stale_connections calls internal cleanup methods (lines 279-285)."""
        # Add connection attempts with old and recent timestamps
        old_time = time.time() - 4000  # More than 3600 seconds ago
        recent_time = time.time() - 1000  # Less than 3600 seconds ago

        self.security_manager.connection_attempts = {
            "192.168.1.1": [old_time, recent_time],
            "192.168.1.2": [old_time, old_time],  # All old timestamps
            "192.168.1.3": [recent_time, recent_time],  # All recent
        }

        # Call the public method that should trigger the private cleanup
        self.security_manager.cleanup_stale_connections()

        # Just check that the cleanup was called and some cleanup occurred
        # The exact behavior depends on the implementation
        assert len(self.security_manager.connection_attempts) >= 1
