"""
Tests for backend/auth/auth_bearer.py module.
Tests JWT bearer authentication.
"""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import HTTPException


class TestJWTBearerInit:
    """Tests for JWTBearer initialization."""

    def test_init_default_auto_error(self):
        """Test JWTBearer default auto_error is True."""
        from backend.auth.auth_bearer import JWTBearer

        bearer = JWTBearer()

        assert bearer.auto_error is True

    def test_init_auto_error_false(self):
        """Test JWTBearer with auto_error=False."""
        from backend.auth.auth_bearer import JWTBearer

        bearer = JWTBearer(auto_error=False)

        assert bearer.auto_error is False


class TestVerifyJWT:
    """Tests for JWTBearer.verify_jwt method."""

    @patch("backend.auth.auth_bearer.decode_jwt")
    def test_verify_jwt_valid_token(self, mock_decode):
        """Test verify_jwt with valid token."""
        from backend.auth.auth_bearer import JWTBearer

        mock_decode.return_value = {"user_id": "test@example.com"}
        bearer = JWTBearer()

        result = bearer.verify_jwt("valid_token")

        assert result is True
        mock_decode.assert_called_once_with("valid_token")

    @patch("backend.auth.auth_bearer.decode_jwt")
    def test_verify_jwt_invalid_token(self, mock_decode):
        """Test verify_jwt with invalid token."""
        from backend.auth.auth_bearer import JWTBearer

        mock_decode.return_value = None
        bearer = JWTBearer()

        result = bearer.verify_jwt("invalid_token")

        assert result is False

    @patch("backend.auth.auth_bearer.decode_jwt")
    def test_verify_jwt_value_error(self, mock_decode):
        """Test verify_jwt handles ValueError."""
        from backend.auth.auth_bearer import JWTBearer

        mock_decode.side_effect = ValueError("Invalid token")
        bearer = JWTBearer()

        result = bearer.verify_jwt("bad_token")

        assert result is False

    @patch("backend.auth.auth_bearer.decode_jwt")
    def test_verify_jwt_type_error(self, mock_decode):
        """Test verify_jwt handles TypeError."""
        from backend.auth.auth_bearer import JWTBearer

        mock_decode.side_effect = TypeError("Type error")
        bearer = JWTBearer()

        result = bearer.verify_jwt("bad_token")

        assert result is False

    @patch("backend.auth.auth_bearer.decode_jwt")
    def test_verify_jwt_key_error(self, mock_decode):
        """Test verify_jwt handles KeyError."""
        from backend.auth.auth_bearer import JWTBearer

        mock_decode.side_effect = KeyError("Missing key")
        bearer = JWTBearer()

        result = bearer.verify_jwt("bad_token")

        assert result is False


class TestJWTBearerCall:
    """Tests for JWTBearer.__call__ method."""

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_call_valid_bearer_token(self, mock_decode):
        """Test __call__ with valid bearer token."""
        from backend.auth.auth_bearer import JWTBearer
        from fastapi.security import HTTPAuthorizationCredentials

        mock_decode.return_value = {"user_id": "test@example.com"}

        bearer = JWTBearer()
        mock_request = MagicMock()
        mock_creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid_token"
        )

        with patch.object(
            bearer.__class__.__bases__[0],
            "__call__",
            new_callable=AsyncMock,
            return_value=mock_creds,
        ):
            result = await bearer(mock_request)

        assert result == "valid_token"

    @pytest.mark.asyncio
    async def test_call_invalid_scheme(self):
        """Test __call__ with non-Bearer scheme."""
        from backend.auth.auth_bearer import JWTBearer
        from fastapi.security import HTTPAuthorizationCredentials

        bearer = JWTBearer()
        mock_request = MagicMock()
        mock_creds = HTTPAuthorizationCredentials(
            scheme="Basic", credentials="some_token"
        )

        with patch.object(
            bearer.__class__.__bases__[0],
            "__call__",
            new_callable=AsyncMock,
            return_value=mock_creds,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await bearer(mock_request)

        assert exc_info.value.status_code == 403
        assert "authentication scheme" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_call_expired_token(self, mock_decode):
        """Test __call__ with expired token."""
        from backend.auth.auth_bearer import JWTBearer
        from fastapi.security import HTTPAuthorizationCredentials

        mock_decode.return_value = None  # Expired/invalid token
        bearer = JWTBearer()
        mock_request = MagicMock()
        mock_creds = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="expired_token"
        )

        with patch.object(
            bearer.__class__.__bases__[0],
            "__call__",
            new_callable=AsyncMock,
            return_value=mock_creds,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await bearer(mock_request)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_call_no_credentials(self):
        """Test __call__ with no credentials."""
        from backend.auth.auth_bearer import JWTBearer

        bearer = JWTBearer()
        mock_request = MagicMock()

        with patch.object(
            bearer.__class__.__bases__[0],
            "__call__",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await bearer(mock_request)

        assert exc_info.value.status_code == 403


class TestGetCurrentUser:
    """Tests for get_current_user function."""

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_get_current_user_valid_token(self, mock_decode):
        """Test get_current_user with valid token."""
        from backend.auth.auth_bearer import get_current_user

        mock_decode.return_value = {"user_id": "test@example.com"}

        result = await get_current_user(token="valid_token")

        assert result == "test@example.com"
        mock_decode.assert_called_once_with("valid_token")

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_get_current_user_no_user_id(self, mock_decode):
        """Test get_current_user when payload has no user_id."""
        from backend.auth.auth_bearer import get_current_user

        mock_decode.return_value = {"other_field": "value"}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="valid_token")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_get_current_user_none_payload(self, mock_decode):
        """Test get_current_user when decode returns None."""
        from backend.auth.auth_bearer import get_current_user

        mock_decode.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="invalid_token")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_get_current_user_value_error(self, mock_decode):
        """Test get_current_user handles ValueError."""
        from backend.auth.auth_bearer import get_current_user

        mock_decode.side_effect = ValueError("Decode error")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="bad_token")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_get_current_user_type_error(self, mock_decode):
        """Test get_current_user handles TypeError."""
        from backend.auth.auth_bearer import get_current_user

        mock_decode.side_effect = TypeError("Type error")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="bad_token")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("backend.auth.auth_bearer.decode_jwt")
    async def test_get_current_user_key_error(self, mock_decode):
        """Test get_current_user handles KeyError."""
        from backend.auth.auth_bearer import get_current_user

        mock_decode.side_effect = KeyError("Key error")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="bad_token")

        assert exc_info.value.status_code == 401


class TestJWTBearerIntegration:
    """Integration tests for JWTBearer with FastAPI."""

    def test_bearer_dependency_type(self):
        """Test JWTBearer can be used as a FastAPI dependency."""
        from backend.auth.auth_bearer import JWTBearer

        bearer = JWTBearer()

        # JWTBearer should be callable (used as dependency)
        assert callable(bearer)

    def test_get_current_user_is_coroutine(self):
        """Test get_current_user is a coroutine function."""
        import asyncio

        from backend.auth.auth_bearer import get_current_user

        assert asyncio.iscoroutinefunction(get_current_user)
