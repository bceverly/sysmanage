"""
Tests for backend/auth/auth_handler.py module.
Tests JWT token signing and verification.
"""

import time
from unittest.mock import patch

import pytest


class TestTokenResponse:
    """Tests for token_response function."""

    def test_token_response_creates_dict(self):
        """Test token_response creates proper dictionary."""
        from backend.auth.auth_handler import token_response

        result = token_response("test_token_123")

        assert result == {"Authorization": "test_token_123"}

    def test_token_response_empty_token(self):
        """Test token_response with empty token."""
        from backend.auth.auth_handler import token_response

        result = token_response("")

        assert result == {"Authorization": ""}


class TestSignJWT:
    """Tests for sign_jwt function."""

    def test_sign_jwt_returns_token(self):
        """Test sign_jwt returns a JWT token string."""
        from backend.auth.auth_handler import sign_jwt

        token = sign_jwt("test@example.com")

        assert isinstance(token, str)
        # JWT tokens have 3 parts separated by dots
        assert token.count(".") == 2

    def test_sign_jwt_contains_user_id(self):
        """Test signed JWT contains user_id."""
        import jwt

        from backend.auth.auth_handler import JWT_ALGORITHM, JWT_SECRET, sign_jwt

        token = sign_jwt("user@test.com")
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        assert decoded["user_id"] == "user@test.com"

    def test_sign_jwt_contains_expires(self):
        """Test signed JWT contains expiry time."""
        import jwt

        from backend.auth.auth_handler import JWT_ALGORITHM, JWT_SECRET, sign_jwt

        before = time.time()
        token = sign_jwt("test@example.com")
        after = time.time()

        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Expiry should be in the future
        assert decoded["expires"] >= before
        assert decoded["expires"] >= after

    def test_sign_jwt_different_users_different_tokens(self):
        """Test different users get different tokens."""
        from backend.auth.auth_handler import sign_jwt

        token1 = sign_jwt("user1@example.com")
        token2 = sign_jwt("user2@example.com")

        assert token1 != token2


class TestSignRefreshToken:
    """Tests for sign_refresh_token function."""

    def test_sign_refresh_token_returns_token(self):
        """Test sign_refresh_token returns a JWT token string."""
        from backend.auth.auth_handler import sign_refresh_token

        token = sign_refresh_token("test@example.com")

        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_sign_refresh_token_contains_user_id(self):
        """Test signed refresh token contains user_id."""
        import jwt

        from backend.auth.auth_handler import (
            JWT_ALGORITHM,
            JWT_SECRET,
            sign_refresh_token,
        )

        token = sign_refresh_token("user@test.com")
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        assert decoded["user_id"] == "user@test.com"

    def test_sign_refresh_token_contains_expires(self):
        """Test signed refresh token contains expiry time."""
        import jwt

        from backend.auth.auth_handler import (
            JWT_ALGORITHM,
            JWT_SECRET,
            sign_refresh_token,
        )

        before = time.time()
        token = sign_refresh_token("test@example.com")

        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Expiry should be in the future
        assert decoded["expires"] >= before


class TestDecodeJWT:
    """Tests for decode_jwt function."""

    def test_decode_jwt_valid_token(self):
        """Test decode_jwt with valid token."""
        from backend.auth.auth_handler import decode_jwt, sign_jwt

        token = sign_jwt("test@example.com")
        decoded = decode_jwt(token)

        assert decoded is not None
        assert decoded["user_id"] == "test@example.com"

    def test_decode_jwt_expired_token(self):
        """Test decode_jwt with expired token."""
        import jwt

        from backend.auth.auth_handler import (
            JWT_ALGORITHM,
            JWT_SECRET,
            decode_jwt,
        )

        # Create an expired token
        payload = {
            "user_id": "test@example.com",
            "expires": time.time() - 3600,  # Expired 1 hour ago
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = decode_jwt(expired_token)

        assert result is None

    def test_decode_jwt_invalid_token(self):
        """Test decode_jwt with invalid token."""
        from backend.auth.auth_handler import decode_jwt

        result = decode_jwt("not.a.valid.jwt.token")

        # Returns empty dict for InvalidTokenError
        assert result == {}

    def test_decode_jwt_malformed_token(self):
        """Test decode_jwt with malformed token."""
        from backend.auth.auth_handler import decode_jwt

        result = decode_jwt("completely_invalid")

        # Returns empty dict for DecodeError
        assert result == {}

    def test_decode_jwt_wrong_secret(self):
        """Test decode_jwt with token signed by different secret."""
        import jwt

        from backend.auth.auth_handler import JWT_ALGORITHM, decode_jwt

        # Create a token with a different secret
        payload = {
            "user_id": "test@example.com",
            "expires": time.time() + 3600,
        }
        wrong_secret_token = jwt.encode(
            payload,
            "wrong_secret_key_for_testing_purposes_32b",
            algorithm=JWT_ALGORITHM,
        )

        result = decode_jwt(wrong_secret_token)

        # Returns empty dict for invalid signature
        assert result == {}

    def test_decode_jwt_missing_expires(self):
        """Test decode_jwt with token missing expires field."""
        import jwt

        from backend.auth.auth_handler import (
            JWT_ALGORITHM,
            JWT_SECRET,
            decode_jwt,
        )

        # Create a token without expires field
        payload = {"user_id": "test@example.com"}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = decode_jwt(token)

        # Returns None for KeyError
        assert result is None


class TestJWTConfiguration:
    """Tests for JWT configuration."""

    def test_jwt_secret_exists(self):
        """Test JWT_SECRET is configured."""
        from backend.auth.auth_handler import JWT_SECRET

        assert JWT_SECRET is not None
        assert len(JWT_SECRET) > 0

    def test_jwt_algorithm_exists(self):
        """Test JWT_ALGORITHM is configured."""
        from backend.auth.auth_handler import JWT_ALGORITHM

        assert JWT_ALGORITHM is not None
        # Common algorithms
        assert JWT_ALGORITHM in ["HS256", "HS384", "HS512", "RS256", "RS512"]


class TestRoundTrip:
    """Round-trip tests for sign and decode."""

    def test_sign_and_decode_jwt_roundtrip(self):
        """Test sign_jwt and decode_jwt work together."""
        from backend.auth.auth_handler import decode_jwt, sign_jwt

        user_id = "roundtrip@example.com"
        token = sign_jwt(user_id)
        decoded = decode_jwt(token)

        assert decoded is not None
        assert decoded["user_id"] == user_id
        assert "expires" in decoded

    def test_sign_and_decode_refresh_roundtrip(self):
        """Test sign_refresh_token and decode_jwt work together."""
        from backend.auth.auth_handler import decode_jwt, sign_refresh_token

        user_id = "refresh@example.com"
        token = sign_refresh_token(user_id)
        decoded = decode_jwt(token)

        assert decoded is not None
        assert decoded["user_id"] == user_id
        assert "expires" in decoded

    def test_multiple_tokens_decode_independently(self):
        """Test multiple tokens can be decoded independently."""
        from backend.auth.auth_handler import decode_jwt, sign_jwt

        token1 = sign_jwt("user1@example.com")
        token2 = sign_jwt("user2@example.com")

        decoded1 = decode_jwt(token1)
        decoded2 = decode_jwt(token2)

        assert decoded1["user_id"] == "user1@example.com"
        assert decoded2["user_id"] == "user2@example.com"
