"""
Unit tests for authentication API endpoints.
Tests /login and /refresh endpoints with various scenarios.
"""

from unittest.mock import Mock, patch

import pytest
from argon2 import PasswordHasher

argon2_hasher = PasswordHasher()

from backend.persistence import models


class TestAuthLogin:
    """Test cases for the /login endpoint."""

    def test_login_success(
        self, client, session, test_user_data, mock_login_security, mock_config
    ):
        """Test successful login with valid credentials."""
        # Create a test user in the database
        hashed_password = argon2_hasher.hash(test_user_data["password"])
        user = models.User(
            userid=test_user_data["userid"],
            hashed_password=hashed_password,
            active=True,
        )
        session.add(user)
        session.commit()

        # Mock successful login validation
        mock_login_security.validate_login_attempt.return_value = (True, "")

        # Test login
        response = client.post(
            "/login",
            json={
                "userid": test_user_data["userid"],
                "password": test_user_data["password"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "Authorization" in data
        assert data["Authorization"] is not None

        # Verify security logging was called
        mock_login_security.record_successful_login.assert_called_once()

    def test_login_invalid_credentials(
        self, client, session, test_user_data, mock_login_security, mock_config
    ):
        """Test login with invalid password."""
        # Create a test user in the database
        hashed_password = argon2_hasher.hash(test_user_data["password"])
        user = models.User(
            userid=test_user_data["userid"],
            hashed_password=hashed_password,
            active=True,
        )
        session.add(user)
        session.commit()

        # Mock successful security validation
        mock_login_security.validate_login_attempt.return_value = (True, "")

        # Test login with wrong password
        response = client.post(
            "/login",
            json={"userid": test_user_data["userid"], "password": "wrong_password"},
        )

        assert response.status_code == 401
        data = response.json()
        assert "Invalid username or password" in data["detail"]

        # Verify failed login was recorded
        mock_login_security.record_failed_login.assert_called_once()

    def test_login_user_not_found(self, client, mock_login_security):
        """Test login with non-existent user."""
        # Mock successful security validation
        mock_login_security.validate_login_attempt.return_value = (True, "")

        response = client.post(
            "/login",
            json={"userid": "nonexistent@example.com", "password": "password123"},
        )

        assert response.status_code == 401
        data = response.json()
        assert "Invalid username or password" in data["detail"]

    def test_login_inactive_user(
        self, client, session, test_user_data, mock_login_security, mock_config
    ):
        """Test login with inactive user account."""
        # Create an inactive test user
        hashed_password = argon2_hasher.hash(test_user_data["password"])
        user = models.User(
            userid=test_user_data["userid"],
            hashed_password=hashed_password,
            active=False,
        )
        session.add(user)
        session.commit()

        # Mock successful security validation
        mock_login_security.validate_login_attempt.return_value = (True, "")

        response = client.post(
            "/login",
            json={
                "userid": test_user_data["userid"],
                "password": test_user_data["password"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "Authorization" in data

    def test_login_rate_limited(self, client, mock_login_security):
        """Test login when rate limited by security system."""
        # Mock rate limiting
        mock_login_security.validate_login_attempt.return_value = (
            False,
            "Too many login attempts",
        )

        response = client.post(
            "/login", json={"userid": "test@example.com", "password": "password123"}
        )

        assert response.status_code == 429
        data = response.json()
        assert "Too many login attempts" in data["detail"]

    def test_login_invalid_email_format(self, client):
        """Test login with invalid email format."""
        response = client.post(
            "/login", json={"userid": "invalid-email", "password": "password123"}
        )

        assert response.status_code == 422  # Validation error

    def test_login_missing_fields(self, client):
        """Test login with missing required fields."""
        # Missing password
        response = client.post("/login", json={"userid": "test@example.com"})
        assert response.status_code == 422

        # Missing userid
        response = client.post("/login", json={"password": "password123"})
        assert response.status_code == 422

        # Empty request
        response = client.post("/login", json={})
        assert response.status_code == 422

    def test_login_locked_account(
        self, client, session, test_user_data, mock_login_security, mock_config
    ):
        """Test login with locked user account."""
        # Create a locked test user
        hashed_password = argon2_hasher.hash(test_user_data["password"])
        user = models.User(
            userid=test_user_data["userid"],
            hashed_password=hashed_password,
            active=True,
            is_locked=True,
        )
        session.add(user)
        session.commit()

        # Mock successful security validation but locked account
        mock_login_security.validate_login_attempt.return_value = (True, "")
        mock_login_security.is_user_account_locked.return_value = (
            True  # Override for this test
        )

        response = client.post(
            "/login",
            json={
                "userid": test_user_data["userid"],
                "password": test_user_data["password"],
            },
        )

        assert response.status_code == 423
        data = response.json()
        assert "Account is locked" in data["detail"]


class TestAuthRefresh:
    """Test cases for the /refresh endpoint."""

    def test_refresh_success(self, client, session, test_user_data, mock_config):
        """Test successful token refresh with valid refresh token."""
        # Create a test user
        hashed_password = argon2_hasher.hash(test_user_data["password"])
        user = models.User(
            userid=test_user_data["userid"],
            hashed_password=hashed_password,
            active=True,
        )
        session.add(user)
        session.commit()

        # Mock a valid refresh token
        with patch("backend.api.auth.decode_jwt") as mock_decode:
            mock_decode.return_value = {
                "user_id": test_user_data["userid"],
            }

            # Set refresh token in cookies
            client.cookies.set("refresh_token", "valid_refresh_token")
            response = client.post("/refresh")

            assert response.status_code == 200
            data = response.json()
            assert "Authorization" in data

    def test_refresh_invalid_token(self, client):
        """Test refresh with invalid token."""
        with patch("backend.api.auth.decode_jwt") as mock_decode:
            mock_decode.return_value = None

            client.cookies.set("refresh_token", "invalid_token")
            response = client.post("/refresh")

            assert response.status_code == 403
            data = response.json()
            assert "Invalid or missing refresh token" in data["detail"]

    def test_refresh_user_not_found(self, client):
        """Test refresh when user no longer exists."""
        with patch("backend.api.auth.decode_jwt") as mock_decode:
            mock_decode.return_value = {"user_id": "nonexistent@example.com"}

            client.cookies.set("refresh_token", "valid_token_but_user_gone")
            response = client.post("/refresh")

            assert response.status_code == 200
            data = response.json()
            assert "Authorization" in data

    def test_refresh_inactive_user(self, client, session, test_user_data, mock_config):
        """Test refresh when user account is inactive."""
        # Create an inactive test user
        hashed_password = argon2_hasher.hash(test_user_data["password"])
        user = models.User(
            userid=test_user_data["userid"],
            hashed_password=hashed_password,
            active=False,
        )
        session.add(user)
        session.commit()

        with patch("backend.api.auth.decode_jwt") as mock_decode:
            mock_decode.return_value = {
                "user_id": test_user_data["userid"],
            }

            client.cookies.set("refresh_token", "valid_token")
            response = client.post("/refresh")

            assert response.status_code == 200
            data = response.json()
            assert "Authorization" in data

    def test_refresh_missing_token(self, client):
        """Test refresh with missing refresh token."""
        response = client.post("/refresh")
        assert response.status_code == 403

    def test_refresh_locked_user(self, client, session, test_user_data, mock_config):
        """Test refresh when user account is locked."""
        # Create a locked test user
        hashed_password = argon2_hasher.hash(test_user_data["password"])
        user = models.User(
            userid=test_user_data["userid"],
            hashed_password=hashed_password,
            active=True,
            is_locked=True,
        )
        session.add(user)
        session.commit()

        with patch("backend.api.auth.decode_jwt") as mock_decode:
            mock_decode.return_value = {
                "user_id": test_user_data["userid"],
            }

            client.cookies.set("refresh_token", "valid_token")
            response = client.post("/refresh")

            assert response.status_code == 200
            data = response.json()
            assert "Authorization" in data
