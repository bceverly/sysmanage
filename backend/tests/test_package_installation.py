"""
Unit tests for the package installation API endpoints and functionality
"""

import uuid
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
def test_engine():
    """Create a shared in-memory SQLite database for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def test_session(test_engine):
    """Create a test database session"""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_host(test_session, test_engine):
    """Create a test host in the database"""
    connection = test_engine.connect()
    connection.execute(
        models.Host.__table__.insert(),
        {
            "id": 1,
            "fqdn": "test-host.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "::1",
            "active": True,
            "status": "up",
            "approval_status": "approved",
            "last_access": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
        },
    )
    connection.commit()
    connection.close()

    # Retrieve the host from the session
    host = test_session.query(models.Host).filter(models.Host.id == 1).first()
    yield host


@pytest.fixture
def client(test_session):
    """Create a test client with database session override"""

    def override_get_db():
        yield test_session

    app.dependency_overrides[db.get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


@pytest.fixture
def mock_auth_header():
    """Mock authentication header"""
    return {"Authorization": "Bearer test-token"}


class TestPackageInstallationAPI:
    """Test cases for package installation API endpoints"""

    def test_install_packages_success(self, client, test_host, mock_auth_header):
        """Test successful package installation request"""
        with patch(
            "backend.websocket.queue_manager.server_queue_manager.enqueue_message"
        ) as mock_enqueue:
            mock_enqueue.return_value = "mock-message-id"

            response = client.post(
                f"/api/packages/install/{test_host.id}",
                json={
                    "package_names": ["vim", "curl", "htop"],
                    "requested_by": "test-user",
                },
                headers=mock_auth_header,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["installation_ids"]) == 3
        assert "Successfully queued 3 packages for installation" in data["message"]

        # Verify that installation log entries were created
        installation_logs = test_host.software_installation_logs
        assert len(installation_logs) == 3

        package_names = [log.package_name for log in installation_logs]
        assert "vim" in package_names
        assert "curl" in package_names
        assert "htop" in package_names

        # Verify all logs have correct initial status
        for log in installation_logs:
            assert log.status == "queued"
            assert log.requested_by == "test-user"
            assert log.package_manager == "auto"
            assert log.installation_id in data["installation_ids"]

    def test_install_packages_host_not_found(self, client, mock_auth_header):
        """Test package installation with non-existent host"""
        response = client.post(
            "/api/packages/install/999",
            json={"package_names": ["vim"], "requested_by": "test-user"},
            headers=mock_auth_header,
        )

        assert response.status_code == 404
        assert "Host not found or not active" in response.json()["detail"]

    def test_install_packages_empty_list(self, client, test_host, mock_auth_header):
        """Test package installation with empty package list"""
        response = client.post(
            f"/api/packages/install/{test_host.id}",
            json={"package_names": [], "requested_by": "test-user"},
            headers=mock_auth_header,
        )

        assert response.status_code == 400
        assert "No packages specified for installation" in response.json()["detail"]

    def test_install_packages_inactive_host(
        self, client, test_session, test_engine, mock_auth_header
    ):
        """Test package installation with inactive host"""
        # Create an inactive host
        connection = test_engine.connect()
        connection.execute(
            models.Host.__table__.insert(),
            {
                "id": 2,
                "fqdn": "inactive-host.example.com",
                "ipv4": "192.168.1.101",
                "active": False,
                "status": "down",
                "approval_status": "pending",
                "created_at": datetime.now(timezone.utc),
            },
        )
        connection.commit()
        connection.close()

        response = client.post(
            "/api/packages/install/2",
            json={"package_names": ["vim"], "requested_by": "test-user"},
            headers=mock_auth_header,
        )

        assert response.status_code == 404
        assert "Host not found or not active" in response.json()["detail"]


class TestSoftwareInstallationLogModel:
    """Test cases for SoftwareInstallationLog model"""

    def test_create_installation_log(self, test_session, test_host):
        """Test creating a software installation log entry"""
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        log_entry = models.SoftwareInstallationLog(
            host_id=test_host.id,
            package_name="test-package",
            package_manager="apt",
            requested_version="1.0.0",
            requested_by="test-user",
            installation_id=installation_id,
            status="pending",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )

        test_session.add(log_entry)
        test_session.commit()
        test_session.refresh(log_entry)

        assert log_entry.id is not None
        assert log_entry.host_id == test_host.id
        assert log_entry.package_name == "test-package"
        assert log_entry.package_manager == "apt"
        assert log_entry.requested_version == "1.0.0"
        assert log_entry.requested_by == "test-user"
        assert log_entry.installation_id == installation_id
        assert log_entry.status == "pending"
        assert log_entry.success is None  # Should be None initially

    def test_update_installation_status(self, test_session, test_host):
        """Test updating installation log status"""
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        log_entry = models.SoftwareInstallationLog(
            host_id=test_host.id,
            package_name="test-package",
            package_manager="apt",
            requested_by="test-user",
            installation_id=installation_id,
            status="pending",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )

        test_session.add(log_entry)
        test_session.commit()

        # Update status to installing
        new_now = datetime.now(timezone.utc)
        log_entry.status = "installing"
        log_entry.started_at = new_now
        test_session.commit()

        assert log_entry.status == "installing"
        assert log_entry.started_at == new_now

        # Update status to completed
        completion_time = datetime.now(timezone.utc)
        log_entry.status = "completed"
        log_entry.success = True
        log_entry.completed_at = completion_time
        log_entry.installed_version = "1.0.0"
        test_session.commit()

        assert log_entry.status == "completed"
        assert log_entry.success is True
        assert log_entry.completed_at == completion_time
        assert log_entry.installed_version == "1.0.0"

    def test_installation_log_relationship(self, test_session, test_host):
        """Test relationship between Host and SoftwareInstallationLog"""
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        log_entry = models.SoftwareInstallationLog(
            host_id=test_host.id,
            package_name="test-package",
            package_manager="apt",
            requested_by="test-user",
            installation_id=installation_id,
            status="pending",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )

        test_session.add(log_entry)
        test_session.commit()

        # Test forward relationship
        assert log_entry.host == test_host

        # Test backward relationship
        assert log_entry in test_host.software_installation_logs
        assert len(test_host.software_installation_logs) == 1


class TestPackageInstallationMessageHandling:
    """Test cases for package installation message handling"""

    def test_handle_package_installation_status_success(self, test_session, test_host):
        """Test handling successful package installation status message"""
        from backend.api.message_handlers import handle_package_installation_status

        # Create an installation log entry
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        log_entry = models.SoftwareInstallationLog(
            host_id=test_host.id,
            package_name="test-package",
            package_manager="apt",
            requested_by="test-user",
            installation_id=installation_id,
            status="pending",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )

        test_session.add(log_entry)
        test_session.commit()

        # Mock connection object
        mock_connection = Mock()
        mock_connection.host_id = test_host.id
        mock_connection.hostname = test_host.fqdn

        # Test status update to "completed"
        message_data = {
            "installation_id": installation_id,
            "status": "completed",
            "package_name": "test-package",
            "requested_by": "test-user",
            "installed_version": "1.0.0",
            "installation_log": "Package installed successfully",
        }

        # Call the handler
        import asyncio

        result = asyncio.run(
            handle_package_installation_status(
                test_session, mock_connection, message_data
            )
        )

        assert result["message_type"] == "package_installation_status_ack"
        assert result["status"] == "updated"

        # Verify the database was updated
        test_session.refresh(log_entry)
        assert log_entry.status == "completed"
        assert log_entry.success is True
        assert log_entry.installed_version == "1.0.0"
        assert log_entry.installation_log == "Package installed successfully"
        assert log_entry.completed_at is not None

    def test_handle_package_installation_status_failed(self, test_session, test_host):
        """Test handling failed package installation status message"""
        from backend.api.message_handlers import handle_package_installation_status

        # Create an installation log entry
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        log_entry = models.SoftwareInstallationLog(
            host_id=test_host.id,
            package_name="test-package",
            package_manager="apt",
            requested_by="test-user",
            installation_id=installation_id,
            status="installing",
            requested_at=now,
            started_at=now,
            created_at=now,
            updated_at=now,
        )

        test_session.add(log_entry)
        test_session.commit()

        # Mock connection object
        mock_connection = Mock()
        mock_connection.host_id = test_host.id
        mock_connection.hostname = test_host.fqdn

        # Test status update to "failed"
        message_data = {
            "installation_id": installation_id,
            "status": "failed",
            "package_name": "test-package",
            "requested_by": "test-user",
            "error_message": "Package not found in repository",
        }

        # Call the handler
        import asyncio

        result = asyncio.run(
            handle_package_installation_status(
                test_session, mock_connection, message_data
            )
        )

        assert result["message_type"] == "package_installation_status_ack"
        assert result["status"] == "updated"

        # Verify the database was updated
        test_session.refresh(log_entry)
        assert log_entry.status == "failed"
        assert log_entry.success is False
        assert log_entry.error_message == "Package not found in repository"
        assert log_entry.completed_at is not None

    def test_handle_package_installation_status_missing_id(
        self, test_session, test_host
    ):
        """Test handling package installation status with missing installation_id"""
        from backend.api.message_handlers import handle_package_installation_status

        # Mock connection object
        mock_connection = Mock()
        mock_connection.host_id = test_host.id
        mock_connection.hostname = test_host.fqdn

        # Test message without installation_id
        message_data = {
            "status": "completed",
            "package_name": "test-package",
            "requested_by": "test-user",
        }

        # Call the handler
        import asyncio

        result = asyncio.run(
            handle_package_installation_status(
                test_session, mock_connection, message_data
            )
        )

        assert result["message_type"] == "error"
        assert "Missing installation_id" in result["error"]
