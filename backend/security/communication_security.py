"""
Communication security validation for agent-server WebSocket connections.
Implements authentication, message integrity, and secure communication protocols.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from backend.config.config import get_config
from backend.i18n import _

logger = logging.getLogger(__name__)


class WebSocketSecurityManager:
    """Manages security for WebSocket communications between agents and server."""

    def __init__(self):
        self.config = get_config()
        # In-memory store for connection tokens (in production, use Redis)
        self.active_connections: Dict[str, Dict[str, Any]] = {}
        self.connection_attempts: Dict[str, list] = {}
        self._cleanup_expired_connections()

    def generate_connection_token(self, agent_hostname: str, client_ip: str) -> str:
        """
        Generate a secure connection token for WebSocket authentication.

        Args:
            agent_hostname: The hostname of the connecting agent
            client_ip: IP address of the connecting agent

        Returns:
            Base64 encoded connection token
        """
        # Generate unique connection ID
        connection_id = secrets.token_urlsafe(32)
        timestamp = int(time.time())

        # Create token payload
        payload = {
            "connection_id": connection_id,
            "hostname": agent_hostname,
            "client_ip": client_ip,
            "timestamp": timestamp,
            "expires": timestamp + 3600,  # 1 hour expiry
        }

        # Sign the payload
        secret_key = self.config.get("security", {}).get(
            "jwt_secret", "fallback_secret"
        )
        payload_json = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            secret_key.encode(), payload_json.encode(), hashlib.sha256
        ).hexdigest()

        # Create final token
        token_data = {"payload": payload, "signature": signature}

        # Store connection info
        self.active_connections[connection_id] = {
            "hostname": agent_hostname,
            "client_ip": client_ip,
            "created_at": timestamp,
            "last_activity": timestamp,
            "authenticated": False,
        }

        # Encode as base64
        token_bytes = json.dumps(token_data).encode()
        return base64.b64encode(token_bytes).decode()

    def validate_connection_token(
        self, token: str, client_ip: str
    ) -> Tuple[bool, Optional[str], str]:
        """
        Validate a WebSocket connection token.

        Args:
            token: Base64 encoded connection token
            client_ip: Current client IP address

        Returns:
            Tuple of (is_valid, connection_id, error_message)
        """
        try:
            # Decode token
            token_bytes = base64.b64decode(token.encode())
            token_data = json.loads(token_bytes)

            payload = token_data.get("payload", {})
            signature = token_data.get("signature", "")

            # Validate signature
            secret_key = self.config.get("security", {}).get(
                "jwt_secret", "fallback_secret"
            )
            payload_json = json.dumps(payload, sort_keys=True)
            expected_signature = hmac.new(
                secret_key.encode(), payload_json.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning(
                    "Invalid token signature from IP: %s", client_ip
                )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                return False, None, _("Invalid token signature")

            # Check expiration
            current_time = int(time.time())
            if current_time > payload.get("expires", 0):
                logger.info(
                    "Expired token from IP: %s", client_ip
                )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                return False, None, _("Token expired")

            # Check IP consistency (allow some flexibility for NAT/proxy scenarios)
            token_ip = payload.get("client_ip", "")
            if token_ip != client_ip:
                logger.info("IP mismatch detected (common with NAT/proxy scenarios)")
                # Don't fail here, just log for monitoring

            connection_id = payload.get("connection_id", "")
            if connection_id in self.active_connections:
                self.active_connections[connection_id]["last_activity"] = current_time
                self.active_connections[connection_id]["authenticated"] = True

            # Clean up expired connections periodically
            self._cleanup_expired_connections()

            return True, connection_id, "Token valid"

        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning(
                "Malformed token from IP %s", client_ip
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            return False, None, _("Malformed token")

    def validate_message_integrity(
        self, message: Dict[str, Any], connection_id: str
    ) -> bool:
        """
        Validate the integrity of a WebSocket message.

        Args:
            message: The message dictionary
            connection_id: ID of the connection

        Returns:
            True if message is valid
        """
        # Check required fields - script_execution_result messages have different format
        message_type = message.get("message_type", "")
        if message_type == "script_execution_result":
            # Script execution results only require message_type and execution_id
            required_fields = ["message_type", "execution_id"]
        else:
            # Standard messages require message_type, message_id, and timestamp
            required_fields = ["message_type", "message_id", "timestamp"]

        for field in required_fields:
            if field not in message:
                logger.warning(
                    "Missing required field '%s' in message from connection %s",
                    field,
                    connection_id,
                )
                return False

        # Validate timestamp (should be within last 30 minutes to handle post-approval scenarios)
        # Skip timestamp validation for script execution results
        if message_type != "script_execution_result":
            try:
                msg_timestamp = datetime.fromisoformat(
                    message["timestamp"].replace("Z", "+00:00")
                )
                current_time = datetime.now(timezone.utc)
                time_diff = abs((current_time - msg_timestamp).total_seconds())

                if (
                    time_diff > 1800
                ):  # 30 minutes (increased tolerance for inventory messages after host approval)
                    logger.warning(
                        "Message timestamp too old: %ss from connection %s",
                        time_diff,
                        connection_id,
                    )
                    return False
            except (ValueError, AttributeError):
                logger.warning(
                    "Invalid timestamp format in message from connection %s",
                    connection_id,
                )
                return False

        # Validate message ID format (should be UUID-like)
        # Script execution results use execution_id instead of message_id
        if message_type != "script_execution_result":
            message_id = message.get("message_id", "")
            if len(message_id) < 20 or not message_id.replace("-", "").isalnum():
                logger.warning(
                    "Invalid message ID format from connection %s", connection_id
                )
                return False

        # Update connection activity
        if connection_id in self.active_connections:
            self.active_connections[connection_id]["last_activity"] = int(time.time())

        return True

    def is_connection_rate_limited(self, client_ip: str) -> bool:
        """Check if connection attempts from IP are rate limited."""
        current_time = time.time()

        # Clean old attempts (keep last 15 minutes)
        if client_ip in self.connection_attempts:
            self.connection_attempts[client_ip] = [
                attempt_time
                for attempt_time in self.connection_attempts[client_ip]
                if current_time - attempt_time < 900  # 15 minutes
            ]

        # Check rate limit (max 20 connections per 15 minutes)
        attempts = len(self.connection_attempts.get(client_ip, []))
        if attempts >= 20:
            logger.warning(
                "Rate limiting connection attempts from IP: %s", client_ip
            )  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            return True

        return False

    def record_connection_attempt(self, client_ip: str) -> None:
        """Record a connection attempt for rate limiting."""
        current_time = time.time()

        if client_ip not in self.connection_attempts:
            self.connection_attempts[client_ip] = []

        self.connection_attempts[client_ip].append(current_time)

    def cleanup_stale_connections(self) -> None:
        """Clean up stale connection records."""
        current_time = int(time.time())
        stale_connections = []

        for conn_id, conn_info in self.active_connections.items():
            # Remove connections inactive for more than 2 hours
            if current_time - conn_info["last_activity"] > 7200:
                stale_connections.append(conn_id)

        for conn_id in stale_connections:
            del self.active_connections[conn_id]
            logger.info("Cleaned up stale connection: %s", conn_id)

    def _cleanup_expired_connections(self):
        """Remove expired connections from memory."""
        current_time = int(time.time())
        expired_connections = []

        for conn_id, conn_info in self.active_connections.items():
            # Remove connections older than 2 hours
            if current_time - conn_info["created_at"] > 7200:
                expired_connections.append(conn_id)

        for conn_id in expired_connections:
            del self.active_connections[conn_id]

        # Also clean up old connection attempts
        cutoff_time = current_time - 3600  # 1 hour
        for client_ip in list(self.connection_attempts.keys()):
            self.connection_attempts[client_ip] = [
                timestamp
                for timestamp in self.connection_attempts[client_ip]
                if timestamp > cutoff_time
            ]
            if not self.connection_attempts[client_ip]:
                del self.connection_attempts[client_ip]

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about active connections."""
        current_time = int(time.time())
        active_count = 0
        authenticated_count = 0

        for conn_info in self.active_connections.values():
            if (
                current_time - conn_info["last_activity"] < 300
            ):  # Active in last 5 minutes
                active_count += 1
                if conn_info.get("authenticated", False):
                    authenticated_count += 1

        return {
            "total_connections": len(self.active_connections),
            "active_connections": active_count,
            "authenticated_connections": authenticated_count,
            "connection_attempts_tracked": len(self.connection_attempts),
        }


class MessageEncryption:
    """Handles message encryption for sensitive communications."""

    def __init__(self):
        self.config = get_config()

    def encrypt_sensitive_data(self, data: Dict[str, Any]) -> str:
        """
        Encrypt sensitive data in messages (like configuration updates).

        Args:
            data: Dictionary containing sensitive data

        Returns:
            Encrypted data as base64 string
        """
        # In production, use proper AES encryption
        # For now, using simple base64 encoding with HMAC for demonstration
        secret_key = self.config.get("security", {}).get(
            "jwt_secret", "fallback_secret"
        )

        # Convert data to JSON
        data_json = json.dumps(data, sort_keys=True)

        # Create HMAC for integrity
        signature = hmac.new(
            secret_key.encode(), data_json.encode(), hashlib.sha256
        ).hexdigest()

        # Combine data and signature
        encrypted_payload = {
            "data": data_json,
            "signature": signature,
            "timestamp": int(time.time()),
        }

        # Encode as base64
        encrypted_bytes = json.dumps(encrypted_payload).encode()
        return base64.b64encode(encrypted_bytes).decode()

    def decrypt_sensitive_data(
        self, encrypted_data: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Decrypt sensitive data from messages.

        Args:
            encrypted_data: Base64 encoded encrypted data

        Returns:
            Tuple of (success, decrypted_data, error_message)
        """
        try:
            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_data.encode())
            encrypted_payload = json.loads(encrypted_bytes)

            data_json = encrypted_payload.get("data", "")
            signature = encrypted_payload.get("signature", "")
            timestamp = encrypted_payload.get("timestamp", 0)

            # Check age (max 1 hour)
            current_time = int(time.time())
            if current_time - timestamp > 3600:
                return False, None, _("Encrypted data expired")

            # Verify signature
            secret_key = self.config.get("security", {}).get(
                "jwt_secret", "fallback_secret"
            )
            expected_signature = hmac.new(
                secret_key.encode(), data_json.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                return False, None, _("Invalid signature")

            # Parse decrypted data
            data = json.loads(data_json)
            return True, data, "Decryption successful"

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return False, None, _("Decryption failed: %s") % str(e)


# Global instances
websocket_security = WebSocketSecurityManager()
message_encryption = MessageEncryption()
