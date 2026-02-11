"""
Tests for backend/api/auth.py module.
Tests authentication API endpoints.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestUserLogin:
    """Tests for UserLogin model."""

    def test_user_login_structure(self):
        """Test UserLogin model structure."""
        from backend.api.auth import UserLogin

        login = UserLogin(userid="user@example.com", password="password123")

        assert login.userid == "user@example.com"
        assert login.password == "password123"

    def test_user_login_email_validation(self):
        """Test UserLogin validates email format."""
        from backend.api.auth import UserLogin
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserLogin(userid="not-an-email", password="password123")


class TestIsSecureCookieEnabled:
    """Tests for _is_secure_cookie_enabled function."""

    def test_secure_when_cert_file_present(self):
        """Test returns True when cert file is configured."""
        from backend.api.auth import _is_secure_cookie_enabled

        the_config = {"api": {"certFile": "/path/to/cert.pem"}}
        assert _is_secure_cookie_enabled(the_config) is True

    def test_not_secure_when_cert_file_empty(self):
        """Test returns False when cert file is empty."""
        from backend.api.auth import _is_secure_cookie_enabled

        the_config = {"api": {"certFile": ""}}
        assert _is_secure_cookie_enabled(the_config) is False

    def test_not_secure_when_cert_file_missing(self):
        """Test returns False when cert file is not configured."""
        from backend.api.auth import _is_secure_cookie_enabled

        the_config = {"api": {}}
        assert _is_secure_cookie_enabled(the_config) is False

    def test_not_secure_when_api_missing(self):
        """Test returns False when api section is missing."""
        from backend.api.auth import _is_secure_cookie_enabled

        the_config = {}
        assert _is_secure_cookie_enabled(the_config) is False


class TestSetRefreshCookie:
    """Tests for _set_refresh_cookie function."""

    def test_sets_cookie_secure(self):
        """Test sets cookie with secure flag."""
        from backend.api.auth import _set_refresh_cookie

        mock_response = MagicMock()
        _set_refresh_cookie(mock_response, "token123", 3600, True)

        mock_response.set_cookie.assert_called_once()
        call_kwargs = mock_response.set_cookie.call_args.kwargs
        assert call_kwargs["key"] == "refresh_token"
        assert call_kwargs["value"] == "token123"
        assert call_kwargs["secure"] is True
        assert call_kwargs["samesite"] == "strict"

    def test_sets_cookie_insecure(self):
        """Test sets cookie without secure flag."""
        from backend.api.auth import _set_refresh_cookie

        mock_response = MagicMock()
        _set_refresh_cookie(mock_response, "token456", 7200, False)

        mock_response.set_cookie.assert_called_once()
        call_kwargs = mock_response.set_cookie.call_args.kwargs
        assert call_kwargs["secure"] is False
        assert call_kwargs["samesite"] == "lax"


class TestLogLoginAttempt:
    """Tests for _log_login_attempt function."""

    @patch("backend.api.auth.AuditService")
    def test_log_successful_login(self, mock_audit):
        """Test logging successful login."""
        from backend.api.auth import _log_login_attempt

        mock_session = MagicMock()
        _log_login_attempt(
            mock_session,
            user_id="user-123",
            username="test@example.com",
            success=True,
            client_ip="192.168.1.1",
            user_agent="TestBrowser/1.0",
        )

        mock_audit.log.assert_called_once()
        call_kwargs = mock_audit.log.call_args.kwargs
        assert "Successful" in call_kwargs["description"]

    @patch("backend.api.auth.AuditService")
    def test_log_failed_login(self, mock_audit):
        """Test logging failed login."""
        from backend.api.auth import _log_login_attempt

        mock_session = MagicMock()
        _log_login_attempt(
            mock_session,
            user_id=None,
            username="hacker@example.com",
            success=False,
            client_ip="10.0.0.1",
            user_agent="EvilBot/1.0",
            error_msg="Invalid password",
        )

        mock_audit.log.assert_called_once()
        call_kwargs = mock_audit.log.call_args.kwargs
        assert "Failed" in call_kwargs["description"]
        assert call_kwargs["error_message"] == "Invalid password"


class TestRefresh:
    """Tests for refresh endpoint."""

    @patch("backend.api.auth.decode_jwt")
    @patch("backend.api.auth.sign_jwt")
    def test_refresh_with_valid_token(self, mock_sign, mock_decode):
        """Test refresh with valid refresh token."""
        from backend.api.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_decode.return_value = {"user_id": "test@example.com"}
        mock_sign.return_value = "new_jwt_token"

        client = TestClient(app)
        client.cookies.set("refresh_token", "valid_refresh_token")
        response = client.post("/api/refresh")

        assert response.status_code == 200
        assert response.json()["Authorization"] == "new_jwt_token"

    @patch("backend.api.auth.decode_jwt")
    def test_refresh_with_invalid_token(self, mock_decode):
        """Test refresh with invalid refresh token."""
        from backend.api.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_decode.return_value = None

        client = TestClient(app)
        client.cookies.set("refresh_token", "invalid_refresh_token")
        response = client.post("/api/refresh")

        assert response.status_code == 403

    def test_refresh_without_token(self):
        """Test refresh without refresh token."""
        from backend.api.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        client = TestClient(app)
        response = client.post("/api/refresh")

        assert response.status_code == 403


class TestLogin:
    """Tests for login endpoint."""

    @patch("backend.api.auth.login_security")
    @patch("backend.api.auth.config")
    @patch("backend.api.auth.db")
    @patch("backend.api.auth.sessionmaker")
    def test_login_rate_limited(
        self, mock_sessionmaker, mock_db, mock_config, mock_login_security
    ):
        """Test login when rate limited."""
        from backend.api.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_login_security.validate_login_attempt.return_value = (
            False,
            "Too many failed attempts",
        )

        client = TestClient(app)
        response = client.post(
            "/api/login",
            json={"userid": "test@example.com", "password": "password"},
        )

        assert response.status_code == 429

    @patch("backend.api.auth._try_admin_login")
    @patch("backend.api.auth.login_security")
    @patch("backend.api.auth.config")
    @patch("backend.api.auth.db")
    @patch("backend.api.auth.sessionmaker")
    def test_login_admin_success(
        self,
        mock_sessionmaker,
        mock_db,
        mock_config,
        mock_login_security,
        mock_try_admin,
    ):
        """Test successful admin login."""
        from backend.api.auth import router

        app = FastAPI()
        app.include_router(router, prefix="/api")

        mock_login_security.validate_login_attempt.return_value = (True, None)
        mock_config.get_config.return_value = {
            "security": {"jwt_refresh_timeout": "3600"},
            "api": {},
        }
        mock_try_admin.return_value = {"Authorization": "admin_token"}

        client = TestClient(app)
        response = client.post(
            "/api/login",
            json={"userid": "admin@example.com", "password": "admin123"},
        )

        assert response.status_code == 200
        assert "Authorization" in response.json()


class TestTryAdminLogin:
    """Tests for _try_admin_login function."""

    @patch("backend.api.auth.login_security")
    @patch("backend.api.auth._log_login_attempt")
    @patch("backend.api.auth.sign_refresh_token")
    @patch("backend.api.auth.sign_jwt")
    @patch("backend.api.auth._set_refresh_cookie")
    def test_admin_login_success(
        self,
        mock_set_cookie,
        mock_sign,
        mock_sign_refresh,
        mock_log,
        mock_login_security,
    ):
        """Test successful admin login."""
        from backend.api.auth import UserLogin, _try_admin_login

        login_data = UserLogin(userid="admin@example.com", password="secret123")
        the_config = {
            "security": {
                "admin_userid": "admin@example.com",
                "admin_password": "secret123",
            }
        }
        mock_sign.return_value = "jwt_token"
        mock_sign_refresh.return_value = "refresh_token"

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session_class = MagicMock(return_value=mock_session)

        mock_response = MagicMock()

        result = _try_admin_login(
            login_data,
            the_config,
            mock_session_class,
            "192.168.1.1",
            "Browser",
            mock_response,
            3600,
            True,
        )

        assert result is not None
        assert result["Authorization"] == "jwt_token"

    def test_admin_login_no_admin_configured(self):
        """Test admin login when no admin is configured."""
        from backend.api.auth import UserLogin, _try_admin_login

        login_data = UserLogin(userid="user@example.com", password="password")
        the_config = {"security": {}}
        mock_session_class = MagicMock()
        mock_response = MagicMock()

        result = _try_admin_login(
            login_data,
            the_config,
            mock_session_class,
            "192.168.1.1",
            "Browser",
            mock_response,
            3600,
            True,
        )

        assert result is None

    @patch("backend.api.auth.login_security")
    @patch("backend.api.auth._log_login_attempt")
    def test_admin_login_wrong_password(self, mock_log, mock_login_security):
        """Test admin login with wrong password."""
        from backend.api.auth import UserLogin, _try_admin_login

        login_data = UserLogin(userid="admin@example.com", password="wrong_password")
        the_config = {
            "security": {
                "admin_userid": "admin@example.com",
                "admin_password": "correct",
            }
        }

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)
        mock_session_class = MagicMock(return_value=mock_session)

        mock_response = MagicMock()

        result = _try_admin_login(
            login_data,
            the_config,
            mock_session_class,
            "192.168.1.1",
            "Browser",
            mock_response,
            3600,
            True,
        )

        assert result is None
        mock_login_security.record_failed_login.assert_called_once()


class TestHandleFailedPassword:
    """Tests for _handle_failed_password function."""

    @patch("backend.api.auth.login_security")
    @patch("backend.api.auth._log_login_attempt")
    def test_handle_failed_password_not_locked(self, mock_log, mock_login_security):
        """Test handling failed password without account lock."""
        from backend.api.auth import UserLogin, _handle_failed_password
        from fastapi import HTTPException

        mock_login_security.record_failed_login_for_user.return_value = False

        mock_user = MagicMock()
        mock_user.id = "user-123"
        login_data = UserLogin(userid="test@example.com", password="wrong")
        mock_session = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            _handle_failed_password(
                mock_user, login_data, mock_session, "192.168.1.1", "Browser"
            )

        assert exc_info.value.status_code == 401

    @patch("backend.api.auth.login_security")
    @patch("backend.api.auth._log_login_attempt")
    def test_handle_failed_password_locked(self, mock_log, mock_login_security):
        """Test handling failed password with account lock."""
        from backend.api.auth import UserLogin, _handle_failed_password
        from fastapi import HTTPException

        mock_login_security.record_failed_login_for_user.return_value = True

        mock_user = MagicMock()
        mock_user.id = "user-123"
        login_data = UserLogin(userid="test@example.com", password="wrong")
        mock_session = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            _handle_failed_password(
                mock_user, login_data, mock_session, "192.168.1.1", "Browser"
            )

        assert exc_info.value.status_code == 423


class TestRouterConfiguration:
    """Tests for router configuration."""

    def test_router_exists(self):
        """Test router exists."""
        from backend.api.auth import router

        assert router is not None
