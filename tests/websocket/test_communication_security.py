"""
Comprehensive unit tests for WebSocket communication security.
Tests authentication, token validation, message integrity, and rate limiting.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from backend.security.communication_security import (
    MessageEncryption,
    WebSocketSecurityManager,
    message_encryption,
    websocket_security,
)


class TestWebSocketSecurityManager:
    """Test WebSocketSecurityManager class functionality."""

    @pytest.fixture
    def security_manager(self):
        """Create a fresh security manager for each test."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {
                "security": {"jwt_secret": "test-secret-key-12345"}
            }
            return WebSocketSecurityManager()

    def test_initialization(self, security_manager):
        """Test security manager initializes correctly."""
        assert security_manager.active_connections == {}
        assert security_manager.connection_attempts == {}

    def test_generate_connection_token(self, security_manager):
        """Test connection token generation."""
        token = security_manager.generate_connection_token(
            agent_hostname="test-host.example.com",
            client_ip="192.168.1.100",
        )

        assert token is not None
        assert isinstance(token, str)

        # Verify token is base64 encoded
        decoded = base64.b64decode(token.encode())
        token_data = json.loads(decoded)

        assert "payload" in token_data
        assert "signature" in token_data
        assert token_data["payload"]["hostname"] == "test-host.example.com"
        assert token_data["payload"]["client_ip"] == "192.168.1.100"

    def test_generate_connection_token_stores_connection(self, security_manager):
        """Test token generation stores connection info."""
        security_manager.generate_connection_token(
            agent_hostname="test-host.example.com",
            client_ip="192.168.1.100",
        )

        assert len(security_manager.active_connections) == 1
        conn_info = list(security_manager.active_connections.values())[0]
        assert conn_info["hostname"] == "test-host.example.com"
        assert conn_info["client_ip"] == "192.168.1.100"
        assert conn_info["authenticated"] is False

    def test_validate_connection_token_success(self, security_manager):
        """Test successful token validation."""
        token = security_manager.generate_connection_token(
            agent_hostname="test-host.example.com",
            client_ip="192.168.1.100",
        )

        is_valid, connection_id, message = security_manager.validate_connection_token(
            token, "192.168.1.100"
        )

        assert is_valid is True
        assert connection_id is not None
        assert message == "Token valid"

    def test_validate_connection_token_marks_authenticated(self, security_manager):
        """Test token validation marks connection as authenticated."""
        token = security_manager.generate_connection_token(
            agent_hostname="test-host.example.com",
            client_ip="192.168.1.100",
        )

        is_valid, connection_id, _ = security_manager.validate_connection_token(
            token, "192.168.1.100"
        )

        assert is_valid is True
        assert (
            security_manager.active_connections[connection_id]["authenticated"] is True
        )

    def test_validate_connection_token_invalid_signature(self, security_manager):
        """Test token validation fails with invalid signature."""
        # Create a token with wrong signature
        payload = {
            "connection_id": "test-id",
            "hostname": "test-host",
            "client_ip": "192.168.1.100",
            "timestamp": int(time.time()),
            "expires": int(time.time()) + 3600,
        }
        token_data = {"payload": payload, "signature": "invalid-signature"}
        token = base64.b64encode(json.dumps(token_data).encode()).decode()

        is_valid, connection_id, message = security_manager.validate_connection_token(
            token, "192.168.1.100"
        )

        assert is_valid is False
        assert connection_id is None
        assert "signature" in message.lower()

    def test_validate_connection_token_expired(self, security_manager):
        """Test token validation fails with expired token."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {
                "security": {"jwt_secret": "test-secret-key-12345"}
            }
            manager = WebSocketSecurityManager()

            # Create expired token manually
            payload = {
                "connection_id": "test-id",
                "hostname": "test-host",
                "client_ip": "192.168.1.100",
                "timestamp": int(time.time()) - 7200,
                "expires": int(time.time()) - 3600,  # Expired 1 hour ago
            }
            payload_json = json.dumps(payload, sort_keys=True)
            secret_key = "test-secret-key-12345"
            signature = hmac.new(
                secret_key.encode(), payload_json.encode(), hashlib.sha256
            ).hexdigest()

            token_data = {"payload": payload, "signature": signature}
            token = base64.b64encode(json.dumps(token_data).encode()).decode()

            is_valid, connection_id, message = manager.validate_connection_token(
                token, "192.168.1.100"
            )

            assert is_valid is False
            assert connection_id is None
            assert "expired" in message.lower()

    def test_validate_connection_token_malformed(self, security_manager):
        """Test token validation fails with malformed token."""
        is_valid, connection_id, message = security_manager.validate_connection_token(
            "not-valid-base64!@#$", "192.168.1.100"
        )

        assert is_valid is False
        assert connection_id is None
        assert "malformed" in message.lower()

    def test_validate_connection_token_ip_mismatch_allowed(self, security_manager):
        """Test token validation allows IP mismatch (for NAT scenarios)."""
        token = security_manager.generate_connection_token(
            agent_hostname="test-host.example.com",
            client_ip="192.168.1.100",
        )

        # Validate with different IP
        is_valid, connection_id, message = security_manager.validate_connection_token(
            token, "10.0.0.50"
        )

        # Should still be valid (IP mismatch is just logged)
        assert is_valid is True

    def test_validate_message_integrity_success(self, security_manager):
        """Test successful message integrity validation."""
        message = {
            "message_type": "heartbeat",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {},
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is True
        assert error == ""

    def test_validate_message_integrity_missing_message_type(self, security_manager):
        """Test validation fails with missing message_type."""
        message = {
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is False
        assert "message_type" in error

    def test_validate_message_integrity_missing_message_id(self, security_manager):
        """Test validation fails with missing message_id."""
        message = {
            "message_type": "heartbeat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is False
        assert "message_id" in error

    def test_validate_message_integrity_missing_timestamp(self, security_manager):
        """Test validation fails with missing timestamp."""
        message = {
            "message_type": "heartbeat",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is False
        assert "timestamp" in error

    def test_validate_message_integrity_old_timestamp(self, security_manager):
        """Test validation fails with too old timestamp."""
        old_time = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message = {
            "message_type": "heartbeat",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": old_time.isoformat(),
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is False
        assert "old" in error.lower() or "timestamp" in error.lower()

    def test_validate_message_integrity_invalid_timestamp_format(
        self, security_manager
    ):
        """Test validation fails with invalid timestamp format."""
        message = {
            "message_type": "heartbeat",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "not-a-valid-timestamp",
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is False
        assert "timestamp" in error.lower() or "format" in error.lower()

    def test_validate_message_integrity_invalid_message_id_format(
        self, security_manager
    ):
        """Test validation fails with invalid message_id format."""
        message = {
            "message_type": "heartbeat",
            "message_id": "short",  # Too short
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is False
        assert "message_id" in error.lower()

    def test_validate_message_integrity_script_execution_result(self, security_manager):
        """Test validation for script_execution_result uses different requirements."""
        message = {
            "message_type": "script_execution_result",
            "execution_id": "exec-123",
            # No message_id or timestamp required for this type
        }

        is_valid, error = security_manager.validate_message_integrity(
            message, "test-connection"
        )

        assert is_valid is True
        assert error == ""

    def test_validate_message_integrity_updates_activity(self, security_manager):
        """Test that validation updates connection activity."""
        token = security_manager.generate_connection_token(
            agent_hostname="test-host", client_ip="192.168.1.100"
        )
        is_valid, connection_id, _ = security_manager.validate_connection_token(
            token, "192.168.1.100"
        )
        initial_activity = security_manager.active_connections[connection_id][
            "last_activity"
        ]

        time.sleep(0.1)

        message = {
            "message_type": "heartbeat",
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        security_manager.validate_message_integrity(message, connection_id)

        new_activity = security_manager.active_connections[connection_id][
            "last_activity"
        ]
        assert new_activity >= initial_activity

    def test_is_connection_rate_limited_no_attempts(self, security_manager):
        """Test rate limiting with no previous attempts."""
        is_limited = security_manager.is_connection_rate_limited("192.168.1.100")

        assert is_limited is False

    def test_is_connection_rate_limited_under_limit(self, security_manager):
        """Test rate limiting with attempts under limit."""
        for _ in range(5):
            security_manager.record_connection_attempt("192.168.1.100")

        is_limited = security_manager.is_connection_rate_limited("192.168.1.100")

        assert is_limited is False

    def test_is_connection_rate_limited_at_limit(self, security_manager):
        """Test rate limiting at the limit."""
        for _ in range(20):
            security_manager.record_connection_attempt("192.168.1.100")

        is_limited = security_manager.is_connection_rate_limited("192.168.1.100")

        assert is_limited is True

    def test_record_connection_attempt(self, security_manager):
        """Test recording connection attempts."""
        security_manager.record_connection_attempt("192.168.1.100")
        security_manager.record_connection_attempt("192.168.1.100")

        assert len(security_manager.connection_attempts["192.168.1.100"]) == 2

    def test_cleanup_stale_connections(self, security_manager):
        """Test cleaning up stale connections."""
        # Add a connection
        security_manager.active_connections["stale-conn"] = {
            "hostname": "stale-host",
            "client_ip": "192.168.1.100",
            "created_at": int(time.time()) - 10000,
            "last_activity": int(time.time()) - 10000,  # Very old
            "authenticated": True,
        }
        security_manager.active_connections["active-conn"] = {
            "hostname": "active-host",
            "client_ip": "192.168.1.101",
            "created_at": int(time.time()),
            "last_activity": int(time.time()),  # Recent
            "authenticated": True,
        }

        security_manager.cleanup_stale_connections()

        assert "stale-conn" not in security_manager.active_connections
        assert "active-conn" in security_manager.active_connections

    def test_get_connection_stats(self, security_manager):
        """Test getting connection statistics."""
        # Add connections
        security_manager.active_connections["active-conn"] = {
            "hostname": "active-host",
            "client_ip": "192.168.1.100",
            "created_at": int(time.time()),
            "last_activity": int(time.time()),
            "authenticated": True,
        }
        security_manager.active_connections["inactive-conn"] = {
            "hostname": "inactive-host",
            "client_ip": "192.168.1.101",
            "created_at": int(time.time()) - 1000,
            "last_activity": int(time.time()) - 1000,  # Inactive
            "authenticated": False,
        }

        stats = security_manager.get_connection_stats()

        assert stats["total_connections"] == 2
        assert stats["active_connections"] == 1
        assert stats["authenticated_connections"] == 1
        assert "connection_attempts_tracked" in stats


class TestMessageEncryption:
    """Test MessageEncryption class functionality."""

    @pytest.fixture
    def encryption(self):
        """Create a fresh encryption manager for each test."""
        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {
                "security": {"jwt_secret": "test-secret-key-12345"}
            }
            return MessageEncryption()

    def test_encrypt_sensitive_data(self, encryption):
        """Test encrypting sensitive data."""
        data = {
            "username": "admin",
            "password": "secret123",
            "config": {"key": "value"},
        }

        encrypted = encryption.encrypt_sensitive_data(data)

        assert encrypted is not None
        assert isinstance(encrypted, str)
        # Should be base64 encoded
        decoded = base64.b64decode(encrypted.encode())
        payload = json.loads(decoded)
        assert "data" in payload
        assert "signature" in payload
        assert "timestamp" in payload

    def test_decrypt_sensitive_data_success(self, encryption):
        """Test successful decryption of sensitive data."""
        original_data = {
            "username": "admin",
            "password": "secret123",
        }

        encrypted = encryption.encrypt_sensitive_data(original_data)
        success, decrypted, message = encryption.decrypt_sensitive_data(encrypted)

        assert success is True
        assert decrypted == original_data
        assert message == "Decryption successful"

    def test_decrypt_sensitive_data_expired(self, encryption):
        """Test decryption fails with expired data."""
        # Create expired payload manually
        data = {"test": "data"}
        data_json = json.dumps(data, sort_keys=True)

        with patch("backend.security.communication_security.get_config") as mock_config:
            mock_config.return_value = {
                "security": {"jwt_secret": "test-secret-key-12345"}
            }
            enc = MessageEncryption()
            secret_key = "test-secret-key-12345"

            signature = hmac.new(
                secret_key.encode(), data_json.encode(), hashlib.sha256
            ).hexdigest()

            payload = {
                "data": data_json,
                "signature": signature,
                "timestamp": int(time.time()) - 7200,  # 2 hours ago
            }
            encrypted = base64.b64encode(json.dumps(payload).encode()).decode()

            success, decrypted, message = enc.decrypt_sensitive_data(encrypted)

            assert success is False
            assert decrypted is None
            assert "expired" in message.lower()

    def test_decrypt_sensitive_data_invalid_signature(self, encryption):
        """Test decryption fails with invalid signature."""
        data_json = json.dumps({"test": "data"}, sort_keys=True)
        payload = {
            "data": data_json,
            "signature": "invalid-signature",
            "timestamp": int(time.time()),
        }
        encrypted = base64.b64encode(json.dumps(payload).encode()).decode()

        success, decrypted, message = encryption.decrypt_sensitive_data(encrypted)

        assert success is False
        assert decrypted is None
        assert "signature" in message.lower()

    def test_decrypt_sensitive_data_malformed(self, encryption):
        """Test decryption fails with malformed data."""
        success, decrypted, message = encryption.decrypt_sensitive_data(
            "not-valid-base64!@#$"
        )

        assert success is False
        assert decrypted is None
        assert "failed" in message.lower()

    def test_encrypt_decrypt_roundtrip(self, encryption):
        """Test encrypt/decrypt roundtrip preserves data."""
        original_data = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "number": 42,
            "string": "test",
        }

        encrypted = encryption.encrypt_sensitive_data(original_data)
        success, decrypted, _ = encryption.decrypt_sensitive_data(encrypted)

        assert success is True
        assert decrypted == original_data


class TestGlobalInstances:
    """Test global security instances."""

    def test_websocket_security_instance_exists(self):
        """Test that global websocket_security instance exists."""
        assert websocket_security is not None
        assert isinstance(websocket_security, WebSocketSecurityManager)

    def test_message_encryption_instance_exists(self):
        """Test that global message_encryption instance exists."""
        assert message_encryption is not None
        assert isinstance(message_encryption, MessageEncryption)

    def test_websocket_security_has_required_methods(self):
        """Test websocket_security has all required methods."""
        required_methods = [
            "generate_connection_token",
            "validate_connection_token",
            "validate_message_integrity",
            "is_connection_rate_limited",
            "record_connection_attempt",
            "cleanup_stale_connections",
            "get_connection_stats",
        ]

        for method in required_methods:
            assert hasattr(websocket_security, method)
            assert callable(getattr(websocket_security, method))

    def test_message_encryption_has_required_methods(self):
        """Test message_encryption has all required methods."""
        required_methods = [
            "encrypt_sensitive_data",
            "decrypt_sensitive_data",
        ]

        for method in required_methods:
            assert hasattr(message_encryption, method)
            assert callable(getattr(message_encryption, method))
