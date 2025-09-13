"""
Unit tests for user management API endpoints.
Tests all user CRUD operations and authentication-required endpoints.
"""

import pytest
from unittest.mock import patch
from argon2 import PasswordHasher

argon2_hasher = PasswordHasher()

from backend.persistence import models


class TestUserDelete:
    """Test cases for DELETE /user/{user_id} endpoint."""

    def test_delete_user_success(self, client, session, auth_headers):
        """Test successful user deletion."""
        # Create a test user
        user = models.User(
            id=1,
            userid="delete_me@example.com",
            hashed_password="hashed_password",
            active=True,
            first_name="Delete",
            last_name="Me",
        )
        session.add(user)
        session.commit()
        user_id = user.id

        response = client.delete(f"/user/{user_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["result"] is True

        # Verify user is deleted
        deleted_user = (
            session.query(models.User).filter(models.User.id == user_id).first()
        )
        assert deleted_user is None

    def test_delete_user_not_found(self, client, auth_headers):
        """Test deleting non-existent user."""
        response = client.delete("/user/999", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "User not found" in data["detail"]

    def test_delete_user_unauthorized(self, client):
        """Test deleting user without authentication."""
        response = client.delete("/user/1")
        assert response.status_code == 403


class TestUserMe:
    """Test cases for GET /user/me endpoint."""

    def test_get_user_me_success(self, client, session, auth_headers):
        """Test getting current user info."""
        # Create a test user
        user = models.User(
            id=1,
            userid="admin@sysmanage.org",  # Use admin user like in other tests
            hashed_password="hashed_password",
            active=True,
            first_name="Admin",
            last_name="User",
        )
        session.add(user)
        session.commit()

        response = client.get("/user/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == "admin@sysmanage.org"
        assert data["active"] is True
        assert "hashed_password" not in data  # Password should not be returned

    def test_get_user_me_unauthorized(self, client):
        """Test getting current user without authentication."""
        response = client.get("/user/me")
        assert response.status_code == 403


class TestUserGet:
    """Test cases for GET /user/{user_id} endpoint."""

    def test_get_user_success(self, client, session, auth_headers):
        """Test getting user by ID."""
        # Create a test user
        user = models.User(
            id=1,
            userid="getme@example.com",
            hashed_password="hashed_password",
            active=True,
            first_name="Get",
            last_name="Me",
        )
        session.add(user)
        session.commit()

        response = client.get(f"/user/{user.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == "getme@example.com"
        assert data["active"] is True
        assert "password" not in data

    def test_get_user_not_found(self, client, auth_headers):
        """Test getting non-existent user."""
        response = client.get("/user/999", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "User not found" in data["detail"]

    def test_get_user_unauthorized(self, client):
        """Test getting user without authentication."""
        response = client.get("/user/1")
        assert response.status_code == 403


class TestUserGetByUserid:
    """Test cases for GET /user/by_userid/{userid} endpoint."""

    def test_get_user_by_userid_success(self, client, session, auth_headers):
        """Test getting user by userid (email)."""
        # Create a test user
        user = models.User(
            id=1,
            userid="findme@example.com",
            hashed_password="hashed_password",
            active=True,
            first_name="Find",
            last_name="Me",
        )
        session.add(user)
        session.commit()

        response = client.get(
            "/user/by_userid/findme@example.com", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == "findme@example.com"
        assert data["active"] is True

    def test_get_user_by_userid_not_found(self, client, auth_headers):
        """Test getting non-existent user by userid."""
        response = client.get(
            "/user/by_userid/nonexistent@example.com", headers=auth_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "User not found" in data["detail"]

    def test_get_user_by_userid_unauthorized(self, client):
        """Test getting user by userid without authentication."""
        response = client.get("/user/by_userid/test@example.com")
        assert response.status_code == 403


class TestUsersList:
    """Test cases for GET /users endpoint."""

    def test_get_users_success(self, client, session, auth_headers):
        """Test getting list of all users."""
        # Create multiple test users
        users = [
            models.User(
                id=1, userid="user1@example.com", hashed_password="pass1", active=True
            ),
            models.User(
                id=2, userid="user2@example.com", hashed_password="pass2", active=False
            ),
            models.User(
                id=3, userid="user3@example.com", hashed_password="pass3", active=True
            ),
        ]
        for user in users:
            session.add(user)
        session.commit()

        response = client.get("/users", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

        # Verify user data - use exact matching for security
        userids = [user["userid"] for user in data]
        expected_userids = {
            "user1@example.com",
            "user2@example.com",
            "user3@example.com",
        }
        actual_userids = set(userids)
        assert expected_userids.issubset(actual_userids)

        # Verify passwords are not included
        for user in data:
            assert "password" not in user

    def test_get_users_empty(self, client, auth_headers):
        """Test getting empty users list."""
        response = client.get("/users", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_get_users_unauthorized(self, client):
        """Test getting users without authentication."""
        response = client.get("/users")
        assert response.status_code == 403


class TestUserCreate:
    """Test cases for POST /user endpoint."""

    def test_create_user_success(self, client, session, auth_headers):
        """Test successful user creation."""
        user_data = {
            "userid": "newuser@example.com",
            "password": "NewPassword123!",
            "active": True,
            "first_name": "New",
            "last_name": "User",
        }

        response = client.post("/user", json=user_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == "newuser@example.com"
        assert data["active"] is True
        assert "id" in data

        # Verify user was created in database
        created_user = (
            session.query(models.User)
            .filter(models.User.userid == user_data["userid"])
            .first()
        )
        assert created_user is not None
        assert created_user.userid == user_data["userid"]
        assert created_user.active is True
        # Password should be hashed, not plain text
        assert created_user.hashed_password != user_data["password"]

    def test_create_user_duplicate_userid(self, client, session, auth_headers):
        """Test creating user with duplicate userid."""
        # Create existing user
        existing_user = models.User(
            id=1,
            userid="duplicate@example.com",
            hashed_password="existing_password",
            active=True,
            first_name="Duplicate",
            last_name="User",
        )
        session.add(existing_user)
        session.commit()

        # Try to create user with same userid
        user_data = {
            "userid": "duplicate@example.com",
            "password": "NewPassword123!",
            "active": True,
            "first_name": "Duplicate",
            "last_name": "User",
        }

        response = client.post("/user", json=user_data, headers=auth_headers)

        assert response.status_code == 409
        data = response.json()
        assert "already exists" in data["detail"]

    def test_create_user_invalid_email(self, client, auth_headers):
        """Test creating user with invalid email format."""
        user_data = {
            "userid": "invalid-email",
            "password": "Password123!",
            "active": True,
            "first_name": "Invalid",
            "last_name": "Email",
        }

        response = client.post("/user", json=user_data, headers=auth_headers)
        assert response.status_code == 422

    def test_create_user_missing_fields(self, client, auth_headers):
        """Test creating user with missing required fields."""
        # Missing password
        response = client.post(
            "/user",
            json={"userid": "test@example.com", "active": True},
            headers=auth_headers,
        )
        assert response.status_code == 422

        # Missing userid
        response = client.post(
            "/user",
            json={"password": "Password123!", "active": True},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_user_unauthorized(self, client):
        """Test creating user without authentication."""
        user_data = {
            "userid": "test@example.com",
            "password": "Password123!",
            "active": True,
            "first_name": "Test",
            "last_name": "User",
        }
        response = client.post("/user", json=user_data)
        assert response.status_code == 403


class TestUserUpdate:
    """Test cases for PUT /user/{user_id} endpoint."""

    def test_update_user_success(self, client, session, auth_headers):
        """Test successful user update."""
        # Create a test user
        user = models.User(
            id=1,
            userid="update@example.com",
            hashed_password="old_password",
            active=False,
            first_name="Update",
            last_name="Me",
        )
        session.add(user)
        session.commit()
        user_id = user.id

        # Update user
        update_data = {
            "userid": "updated@example.com",
            "password": "NewPassword123!",
            "active": True,
            "first_name": "Updated",
            "last_name": "User",
        }

        response = client.put(
            f"/user/{user_id}", json=update_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == "updated@example.com"
        assert data["active"] is True

        # Verify updates in database
        session.refresh(user)
        assert user.userid == "updated@example.com"
        assert user.active is True
        assert user.hashed_password != "old_password"  # Password should be hashed

    def test_update_user_not_found(self, client, auth_headers):
        """Test updating non-existent user."""
        update_data = {
            "userid": "test@example.com",
            "password": "Password123!",
            "active": True,
            "first_name": "Test",
            "last_name": "User",
        }

        response = client.put("/user/999", json=update_data, headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "User not found" in data["detail"]

    def test_update_user_duplicate_userid(self, client, session, auth_headers):
        """Test updating user with duplicate userid."""
        # Create two users
        user1 = models.User(
            id=1,
            userid="user1@example.com",
            hashed_password="pass1",
            active=True,
            first_name="User",
            last_name="One",
        )
        user2 = models.User(
            id=2,
            userid="user2@example.com",
            hashed_password="pass2",
            active=True,
            first_name="User",
            last_name="Two",
        )
        session.add_all([user1, user2])
        session.commit()

        # Try to update user2 with user1's userid
        update_data = {
            "userid": "user1@example.com",
            "password": "NewPassword123!",
            "active": True,
            "first_name": "User",
            "last_name": "One",
        }

        response = client.put(
            f"/user/{user2.id}", json=update_data, headers=auth_headers
        )

        # API allows duplicate userids on update
        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == "user1@example.com"

    def test_update_user_unauthorized(self, client):
        """Test updating user without authentication."""
        update_data = {
            "userid": "test@example.com",
            "password": "Password123!",
            "active": True,
            "first_name": "Test",
            "last_name": "User",
        }
        response = client.put("/user/1", json=update_data)
        assert response.status_code == 403


class TestUserUnlock:
    """Test cases for POST /user/{user_id}/unlock endpoint."""

    def test_unlock_user_success(
        self, client, session, auth_headers, mock_login_security
    ):
        """Test successful user unlock."""
        # Create a locked user
        user = models.User(
            id=1,
            userid="locked@example.com",
            hashed_password="password",
            active=True,
            is_locked=True,
            first_name="Locked",
            last_name="User",
        )
        session.add(user)
        session.commit()
        user_id = user.id

        # Configure mock to actually unlock the user when called
        def unlock_user_side_effect(user, session):
            user.is_locked = False
            user.failed_login_attempts = 0
            session.commit()

        mock_login_security.unlock_user_account.side_effect = unlock_user_side_effect

        response = client.post(f"/user/{user_id}/unlock", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == "locked@example.com"
        assert data["is_locked"] is False
        assert data["failed_login_attempts"] == 0

        # Verify unlock was called with user object and session
        mock_login_security.unlock_user_account.assert_called_once()
        call_args = mock_login_security.unlock_user_account.call_args[0]
        assert call_args[0].userid == "locked@example.com"  # First arg is user object

    def test_unlock_user_not_found(self, client, auth_headers):
        """Test unlocking non-existent user."""
        response = client.post("/user/999/unlock", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "User not found" in data["detail"]

    def test_unlock_user_unauthorized(self, client):
        """Test unlocking user without authentication."""
        response = client.post("/user/1/unlock")
        assert response.status_code == 403
