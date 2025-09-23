"""
Comprehensive unit tests for backend auth modules.
Tests JWT authentication, authorization, and token handling.
"""

import time
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.auth.auth_handler import (
    JWT_ALGORITHM,
    JWT_SECRET,
    decode_jwt,
    sign_jwt,
    sign_refresh_token,
    token_response,
)


class TestAuthHandler:
    """Test cases for auth_handler module."""

    def test_token_response(self):
        """Test token_response creates proper response format."""
        token = "test.jwt.token"
        result = token_response(token)

        assert result == {"Authorization": token}
        assert isinstance(result, dict)

    @patch("backend.auth.auth_handler.time.time")
    @patch("backend.auth.auth_handler.the_config")
    def test_sign_jwt_basic(self, mock_config, mock_time):
        """Test basic JWT token signing."""
        mock_time.return_value = 1000000000  # Fixed timestamp
        mock_config.__getitem__.return_value = {"jwt_auth_timeout": "3600"}

        user_id = "test_user_123"

        with patch("backend.auth.auth_handler.jwt.encode") as mock_encode:
            mock_encode.return_value = "encoded.jwt.token"

            result = sign_jwt(user_id)

            mock_encode.assert_called_once()
            args, kwargs = mock_encode.call_args
            payload, secret = args[:2]
            # Check if algorithm is in args or kwargs
            if len(args) > 2:
                algorithm = args[2]
            else:
                algorithm = kwargs.get("algorithm")

            assert payload["user_id"] == user_id
            assert payload["expires"] == 1000000000 + 3600
            assert result == "encoded.jwt.token"

    @patch("backend.auth.auth_handler.time.time")
    @patch("backend.auth.auth_handler.the_config")
    def test_sign_refresh_token_basic(self, mock_config, mock_time):
        """Test basic JWT refresh token signing."""
        mock_time.return_value = 2000000000  # Fixed timestamp
        mock_config.__getitem__.return_value = {"jwt_refresh_timeout": "86400"}

        user_id = "refresh_user_456"

        with patch("backend.auth.auth_handler.jwt.encode") as mock_encode:
            mock_encode.return_value = "refresh.jwt.token"

            result = sign_refresh_token(user_id)

            mock_encode.assert_called_once()
            args, kwargs = mock_encode.call_args
            payload, secret = args[:2]
            # Check if algorithm is in args or kwargs
            if len(args) > 2:
                algorithm = args[2]
            else:
                algorithm = kwargs.get("algorithm")

            assert payload["user_id"] == user_id
            assert payload["expires"] == 2000000000 + 86400
            assert result == "refresh.jwt.token"

    @patch("backend.auth.auth_handler.time.time")
    def test_decode_jwt_valid_token(self, mock_time):
        """Test decoding a valid, non-expired JWT token."""
        mock_time.return_value = 1000000000  # Current time

        # Mock a valid token payload
        mock_payload = {
            "user_id": "test_user",
            "expires": 1000003600,  # Expires in future
        }

        with patch("backend.auth.auth_handler.jwt.decode") as mock_decode:
            mock_decode.return_value = mock_payload

            result = decode_jwt("valid.jwt.token")

            assert result == mock_payload
            mock_decode.assert_called_once_with(
                "valid.jwt.token", JWT_SECRET, algorithms=[JWT_ALGORITHM]
            )

    @patch("backend.auth.auth_handler.time.time")
    def test_decode_jwt_expired_token(self, mock_time):
        """Test decoding an expired JWT token."""
        mock_time.return_value = 1000003600  # Current time

        # Mock an expired token payload
        mock_payload = {
            "user_id": "test_user",
            "expires": 1000000000,  # Expired in past
        }

        with patch("backend.auth.auth_handler.jwt.decode") as mock_decode:
            mock_decode.return_value = mock_payload

            result = decode_jwt("expired.jwt.token")

            assert result is None

    def test_decode_jwt_invalid_token_error(self):
        """Test decoding with JWT InvalidTokenError."""
        with patch("backend.auth.auth_handler.jwt.decode") as mock_decode:
            from jwt.exceptions import InvalidTokenError

            mock_decode.side_effect = InvalidTokenError("Invalid token")

            result = decode_jwt("invalid.jwt.token")

            assert result == {}

    def test_decode_jwt_decode_error(self):
        """Test decoding with JWT DecodeError."""
        with patch("backend.auth.auth_handler.jwt.decode") as mock_decode:
            from jwt.exceptions import DecodeError

            mock_decode.side_effect = DecodeError("Decode error")

            result = decode_jwt("malformed.jwt.token")

            assert result == {}

    def test_decode_jwt_value_error(self):
        """Test decoding with ValueError."""
        with patch("backend.auth.auth_handler.jwt.decode") as mock_decode:
            mock_decode.side_effect = ValueError("Value error")

            result = decode_jwt("problematic.jwt.token")

            assert result is None

    def test_decode_jwt_type_error(self):
        """Test decoding with TypeError."""
        with patch("backend.auth.auth_handler.jwt.decode") as mock_decode:
            mock_decode.side_effect = TypeError("Type error")

            result = decode_jwt("type-error.jwt.token")

            assert result is None

    def test_decode_jwt_key_error(self):
        """Test decoding with KeyError."""
        with patch("backend.auth.auth_handler.jwt.decode") as mock_decode:
            mock_decode.side_effect = KeyError("Key error")

            result = decode_jwt("key-error.jwt.token")

            assert result is None


class TestJWTBearer:
    """Test cases for JWTBearer class."""

    def test_jwt_bearer_initialization_default(self):
        """Test JWTBearer initialization with default auto_error."""
        bearer = JWTBearer()
        assert bearer.auto_error is True

    def test_jwt_bearer_initialization_custom(self):
        """Test JWTBearer initialization with custom auto_error."""
        bearer = JWTBearer(auto_error=False)
        assert bearer.auto_error is False

    @pytest.mark.asyncio
    async def test_call_valid_bearer_token(self):
        """Test __call__ with valid Bearer token."""
        bearer = JWTBearer()
        mock_request = Mock(spec=Request)

        # Mock successful parent call
        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.scheme = "Bearer"
        mock_credentials.credentials = "valid.jwt.token"

        with patch.object(
            bearer.__class__.__bases__[0], "__call__"
        ) as mock_parent_call:
            mock_parent_call.return_value = mock_credentials

            with patch.object(bearer, "verify_jwt") as mock_verify:
                mock_verify.return_value = True

                result = await bearer(mock_request)

                assert result == "valid.jwt.token"
                mock_verify.assert_called_once_with("valid.jwt.token")

    @pytest.mark.asyncio
    async def test_call_invalid_scheme(self):
        """Test __call__ with invalid authentication scheme."""
        bearer = JWTBearer()
        mock_request = Mock(spec=Request)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.scheme = "Basic"  # Not Bearer
        mock_credentials.credentials = "some.token"

        with patch.object(
            bearer.__class__.__bases__[0], "__call__"
        ) as mock_parent_call:
            mock_parent_call.return_value = mock_credentials

            with pytest.raises(HTTPException) as exc_info:
                await bearer(mock_request)

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_call_invalid_jwt_token(self):
        """Test __call__ with invalid JWT token."""
        bearer = JWTBearer()
        mock_request = Mock(spec=Request)

        mock_credentials = Mock(spec=HTTPAuthorizationCredentials)
        mock_credentials.scheme = "Bearer"
        mock_credentials.credentials = "invalid.jwt.token"

        with patch.object(
            bearer.__class__.__bases__[0], "__call__"
        ) as mock_parent_call:
            mock_parent_call.return_value = mock_credentials

            with patch.object(bearer, "verify_jwt") as mock_verify:
                mock_verify.return_value = False

                with pytest.raises(HTTPException) as exc_info:
                    await bearer(mock_request)

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_call_no_credentials(self):
        """Test __call__ when no credentials are provided."""
        bearer = JWTBearer()
        mock_request = Mock(spec=Request)

        with patch.object(
            bearer.__class__.__bases__[0], "__call__"
        ) as mock_parent_call:
            mock_parent_call.return_value = None  # No credentials

            with pytest.raises(HTTPException) as exc_info:
                await bearer(mock_request)

            assert exc_info.value.status_code == 403

    def test_verify_jwt_valid_token(self):
        """Test verify_jwt with valid token."""
        bearer = JWTBearer()

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.return_value = {"user_id": "test_user", "expires": 123456789}

            result = bearer.verify_jwt("valid.jwt.token")

            assert result is True
            mock_decode.assert_called_once_with("valid.jwt.token")

    def test_verify_jwt_invalid_token_payload_none(self):
        """Test verify_jwt when decode_jwt returns None."""
        bearer = JWTBearer()

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.return_value = None

            result = bearer.verify_jwt("expired.jwt.token")

            assert result is False

    def test_verify_jwt_decode_value_error(self):
        """Test verify_jwt when decode_jwt raises ValueError."""
        bearer = JWTBearer()

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.side_effect = ValueError("Decode error")

            result = bearer.verify_jwt("problematic.jwt.token")

            assert result is False

    def test_verify_jwt_decode_type_error(self):
        """Test verify_jwt when decode_jwt raises TypeError."""
        bearer = JWTBearer()

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.side_effect = TypeError("Type error")

            result = bearer.verify_jwt("type-problematic.jwt.token")

            assert result is False

    def test_verify_jwt_decode_key_error(self):
        """Test verify_jwt when decode_jwt raises KeyError."""
        bearer = JWTBearer()

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.side_effect = KeyError("Key error")

            result = bearer.verify_jwt("key-problematic.jwt.token")

            assert result is False


class TestGetCurrentUser:
    """Test cases for get_current_user function."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self):
        """Test get_current_user with valid token."""
        token = "valid.jwt.token"

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.return_value = {
                "user_id": "test_user_123",
                "expires": 123456789,
            }

            result = await get_current_user(token)

            assert result == "test_user_123"
            mock_decode.assert_called_once_with(token)

    @pytest.mark.asyncio
    async def test_get_current_user_no_payload(self):
        """Test get_current_user when decode_jwt returns None."""
        token = "invalid.jwt.token"

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_no_user_id(self):
        """Test get_current_user when payload missing user_id."""
        token = "incomplete.jwt.token"

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.return_value = {"expires": 123456789}  # Missing user_id

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_decode_value_error(self):
        """Test get_current_user when decode_jwt raises ValueError."""
        token = "problematic.jwt.token"

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.side_effect = ValueError("Decode error")

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_decode_type_error(self):
        """Test get_current_user when decode_jwt raises TypeError."""
        token = "type-problematic.jwt.token"

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.side_effect = TypeError("Type error")

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_decode_key_error(self):
        """Test get_current_user when decode_jwt raises KeyError."""
        token = "key-problematic.jwt.token"

        with patch("backend.auth.auth_bearer.decode_jwt") as mock_decode:
            mock_decode.side_effect = KeyError("Key error")

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token)

            assert exc_info.value.status_code == 401
