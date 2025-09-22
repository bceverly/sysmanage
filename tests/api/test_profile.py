"""
Unit tests for the profile API endpoints
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.persistence import db, models


@pytest.fixture
def test_user(session):
    """Create a test user in the database"""
    # Create user using the test session with the proper test models
    user = models.User(
        userid="test@example.com",
        first_name="John",
        last_name="Doe",
        active=True,
        hashed_password="hashed_password_123",
        last_access=datetime.now(timezone.utc),
        is_locked=False,
        failed_login_attempts=0,
        locked_at=None,
        profile_image=None,
        profile_image_type=None,
        profile_image_uploaded_at=None,
        is_admin=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_login_at=None,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def client():
    """Create a test client with authenticated user"""
    from backend.auth.auth_bearer import JWTBearer, get_current_user

    # Mock authentication dependencies that return the expected values
    async def mock_jwt_bearer():
        return "mock_token"

    async def mock_get_current_user():
        return "test@example.com"

    # Override the dependencies for testing using the actual functions
    app.dependency_overrides[JWTBearer()] = mock_jwt_bearer
    app.dependency_overrides[get_current_user] = mock_get_current_user

    test_client = TestClient(app)

    yield test_client

    # Clean up dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client_nonexistent_user():
    """Create a test client with non-existent user"""
    from backend.auth.auth_bearer import JWTBearer, get_current_user

    # Mock authentication dependencies
    async def mock_jwt_bearer():
        return "mock_token"

    async def mock_get_current_user():
        return "nonexistent@example.com"

    # Override the dependencies for testing
    app.dependency_overrides[JWTBearer()] = mock_jwt_bearer
    app.dependency_overrides[get_current_user] = mock_get_current_user

    test_client = TestClient(app)

    yield test_client

    # Clean up dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for authentication"""
    # nosemgrep: generic.secrets.security.detected-jwt-token.detected-jwt-token
    return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoidGVzdEBleGFtcGxlLmNvbSJ9.mock"


class TestProfileAPI:
    """Test cases for profile API endpoints"""

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_get_profile_success(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client,
        test_db,
        session,
        test_user,
        mock_jwt_token,
    ):
        """Test successful profile retrieval"""
        # Mock JWT decoding to return valid user
        import time

        mock_decode_jwt.return_value = {
            "user_id": test_user.userid,
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client.get("/api/profile", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == test_user.userid
        assert data["first_name"] == test_user.first_name
        assert data["last_name"] == test_user.last_name
        assert data["active"] == test_user.active

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_get_profile_user_not_found(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client_nonexistent_user,
        test_db,
        mock_jwt_token,
    ):
        """Test profile retrieval when user doesn't exist"""
        # Mock JWT decoding to return non-existent user
        import time

        mock_decode_jwt.return_value = {
            "user_id": "nonexistent@example.com",
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client_nonexistent_user.get("/api/profile", headers=headers)

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    def test_get_profile_no_auth(self, client):
        """Test profile retrieval without authentication"""
        response = client.get("/api/profile")

        assert response.status_code == 403

    @patch("backend.auth.auth_handler.decode_jwt")
    def test_get_profile_invalid_token(self, mock_decode_jwt, client):
        """Test profile retrieval with invalid token"""
        mock_decode_jwt.side_effect = Exception("Invalid token")

        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/api/profile", headers=headers)

        assert response.status_code == 401

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_update_profile_success(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client,
        test_db,
        session,
        test_user,
        mock_jwt_token,
    ):
        """Test successful profile update"""
        # Mock JWT decoding to return valid user
        import time

        mock_decode_jwt.return_value = {
            "user_id": test_user.userid,
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        update_data = {"first_name": "Jane", "last_name": "Smith"}

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client.put("/api/profile", json=update_data, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == test_user.userid
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Smith"
        assert data["active"] == test_user.active

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_update_profile_partial(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client,
        test_db,
        session,
        test_user,
        mock_jwt_token,
    ):
        """Test partial profile update (only first name)"""
        # Mock JWT decoding to return valid user
        import time

        mock_decode_jwt.return_value = {
            "user_id": test_user.userid,
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        update_data = {"first_name": "Jane"}

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client.put("/api/profile", json=update_data, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == test_user.userid
        assert data["first_name"] == "Jane"
        assert data["last_name"] == test_user.last_name  # Should remain unchanged
        assert data["active"] == test_user.active

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_update_profile_empty_data(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client,
        test_db,
        session,
        test_user,
        mock_jwt_token,
    ):
        """Test profile update with empty data"""
        # Mock JWT decoding to return valid user
        import time

        mock_decode_jwt.return_value = {
            "user_id": test_user.userid,
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        update_data = {}

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client.put("/api/profile", json=update_data, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == test_user.userid
        assert data["first_name"] == test_user.first_name  # Should remain unchanged
        assert data["last_name"] == test_user.last_name  # Should remain unchanged
        assert data["active"] == test_user.active

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_update_profile_null_values(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client,
        test_db,
        session,
        test_user,
        mock_jwt_token,
    ):
        """Test profile update with null values"""
        # Mock JWT decoding to return valid user
        import time

        mock_decode_jwt.return_value = {
            "user_id": test_user.userid,
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        update_data = {"first_name": None, "last_name": None}

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client.put("/api/profile", json=update_data, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["userid"] == test_user.userid
        assert data["first_name"] is None
        assert data["last_name"] is None
        assert data["active"] == test_user.active

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_update_profile_user_not_found(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client,
        test_db,
        mock_jwt_token,
    ):
        """Test profile update when user doesn't exist"""
        # Mock JWT decoding to return non-existent user
        import time

        mock_decode_jwt.return_value = {
            "user_id": "nonexistent@example.com",
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        update_data = {"first_name": "Jane", "last_name": "Smith"}

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client.put("/api/profile", json=update_data, headers=headers)

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    def test_update_profile_no_auth(self, client):
        """Test profile update without authentication"""
        update_data = {"first_name": "Jane", "last_name": "Smith"}

        response = client.put("/api/profile", json=update_data)

        assert response.status_code == 403

    @patch("backend.auth.auth_handler.decode_jwt")
    def test_update_profile_invalid_token(self, mock_decode_jwt, client):
        """Test profile update with invalid token"""
        mock_decode_jwt.side_effect = Exception("Invalid token")

        update_data = {"first_name": "Jane", "last_name": "Smith"}

        headers = {"Authorization": "Bearer invalid_token"}
        response = client.put("/api/profile", json=update_data, headers=headers)

        assert response.status_code == 401

    @patch("backend.auth.auth_bearer.decode_jwt")
    @patch("backend.persistence.db.get_engine")
    def test_update_profile_updates_last_access(
        self,
        mock_get_engine,
        mock_decode_jwt,
        client,
        test_db,
        session,
        test_user,
        mock_jwt_token,
    ):
        """Test that profile update updates the last_access timestamp"""
        # Mock JWT decoding to return valid user
        import time

        mock_decode_jwt.return_value = {
            "user_id": test_user.userid,
            "expires": time.time() + 3600,  # Valid for 1 hour
        }

        # Mock database engine
        mock_get_engine.return_value = test_db

        original_last_access = test_user.last_access

        update_data = {"first_name": "Updated"}

        headers = {"Authorization": f"Bearer {mock_jwt_token}"}
        response = client.put("/api/profile", json=update_data, headers=headers)

        assert response.status_code == 200

        # Refresh user from database to get updated last_access
        session.refresh(test_user)
        assert test_user.last_access > original_last_access

    def test_profile_model_validation(self):
        """Test ProfileUpdate model validation"""
        from backend.api.profile import ProfileUpdate

        # Test valid data
        profile_update = ProfileUpdate(first_name="John", last_name="Doe")
        assert profile_update.first_name == "John"
        assert profile_update.last_name == "Doe"

        # Test optional fields
        profile_update = ProfileUpdate()
        assert profile_update.first_name is None
        assert profile_update.last_name is None

        # Test partial data
        profile_update = ProfileUpdate(first_name="John")
        assert profile_update.first_name == "John"
        assert profile_update.last_name is None

    def test_profile_response_model(self):
        """Test ProfileResponse model"""
        from backend.api.profile import ProfileResponse

        profile_response = ProfileResponse(
            userid="test@example.com",
            first_name="John",
            last_name="Doe",
            active=True,
            password_requirements="Test requirements",
        )

        assert profile_response.userid == "test@example.com"
        assert profile_response.first_name == "John"
        assert profile_response.last_name == "Doe"
        assert profile_response.active is True
        assert profile_response.password_requirements == "Test requirements"

        # Test with null names
        profile_response = ProfileResponse(
            userid="test@example.com",
            active=True,
            password_requirements="Test requirements",
        )

        assert profile_response.userid == "test@example.com"
        assert profile_response.first_name is None
        assert profile_response.last_name is None
        assert profile_response.active is True
        assert profile_response.password_requirements == "Test requirements"
