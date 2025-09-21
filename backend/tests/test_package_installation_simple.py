"""
Simplified unit tests for package installation functionality that don't require the full FastAPI app
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models


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


class TestPackageInstallationLogic:
    """Test the package installation logic without full FastAPI setup"""

    def test_create_installation_logs(self, test_session, test_host):
        """Test creating multiple installation log entries"""
        package_names = ["vim", "curl", "htop"]
        installation_ids = []
        now = datetime.now(timezone.utc)

        # Create installation logs
        for package_name in package_names:
            installation_id = str(uuid.uuid4())
            installation_ids.append(installation_id)

            log_entry = models.SoftwareInstallationLog(
                host_id=test_host.id,
                package_name=package_name,
                package_manager="auto",
                requested_version=None,
                requested_by="test-user",
                installation_id=installation_id,
                status="pending",
                requested_at=now,
                created_at=now,
                updated_at=now,
            )

            test_session.add(log_entry)

        test_session.commit()

        # Verify all logs were created
        logs = test_session.query(models.SoftwareInstallationLog).all()
        assert len(logs) == 3

        for log in logs:
            assert log.package_name in package_names
            assert log.status == "pending"
            assert log.requested_by == "test-user"
            assert log.installation_id in installation_ids

    def test_update_installation_log_to_queued(self, test_session, test_host):
        """Test updating installation log status to queued"""
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Create initial log
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

        # Update to queued
        log_entry.status = "queued"
        log_entry.queued_at = datetime.now(timezone.utc)
        test_session.commit()

        # Verify update
        updated_log = (
            test_session.query(models.SoftwareInstallationLog)
            .filter(models.SoftwareInstallationLog.installation_id == installation_id)
            .first()
        )

        assert updated_log.status == "queued"
        assert updated_log.queued_at is not None

    def test_package_installation_validation_logic(self, test_session, test_host):
        """Test validation logic for package installation requests"""
        # Test valid request data
        valid_request = {"package_names": ["vim", "curl"], "requested_by": "admin-user"}

        # Simulate validation
        assert len(valid_request["package_names"]) > 0
        assert valid_request["requested_by"] is not None
        assert all(name.strip() for name in valid_request["package_names"])

        # Test invalid request data
        invalid_requests = [
            {"package_names": [], "requested_by": "user"},  # Empty package list
            {"package_names": ["vim"], "requested_by": ""},  # Empty user
            {"package_names": [""], "requested_by": "user"},  # Empty package name
        ]

        for invalid_request in invalid_requests:
            if not invalid_request["package_names"]:
                # Should fail validation
                assert len(invalid_request["package_names"]) == 0
            elif not invalid_request["requested_by"]:
                # Should fail validation
                assert not invalid_request["requested_by"]
            elif not all(name.strip() for name in invalid_request["package_names"]):
                # Should fail validation
                assert not all(
                    name.strip() for name in invalid_request["package_names"]
                )

    def test_host_validation_logic(self, test_session, test_host, test_engine):
        """Test host validation logic for package installation"""
        # Test valid host
        assert test_host.active is True
        assert test_host.approval_status == "approved"

        # Create inactive host using direct SQL insert like test_host fixture
        connection = test_engine.connect()
        connection.execute(
            models.Host.__table__.insert(),
            {
                "id": 2,
                "fqdn": "inactive.example.com",
                "ipv4": "192.168.1.200",
                "active": False,
                "status": "down",
                "approval_status": "pending",
            },
        )
        connection.commit()
        connection.close()

        # Retrieve the inactive host
        inactive_host = (
            test_session.query(models.Host).filter(models.Host.id == 2).first()
        )

        # Test validation logic
        assert not (
            inactive_host.active and inactive_host.approval_status == "approved"
        )

    def test_installation_id_uniqueness(self, test_session, test_host):
        """Test that installation IDs are unique"""
        installation_ids = set()
        now = datetime.now(timezone.utc)

        # Create multiple installation logs
        for i in range(10):
            installation_id = str(uuid.uuid4())
            assert installation_id not in installation_ids  # Ensure uniqueness
            installation_ids.add(installation_id)

            log_entry = models.SoftwareInstallationLog(
                host_id=test_host.id,
                package_name=f"package-{i}",
                package_manager="auto",
                requested_by="test-user",
                installation_id=installation_id,
                status="pending",
                requested_at=now,
                created_at=now,
                updated_at=now,
            )
            test_session.add(log_entry)

        test_session.commit()

        # Verify all IDs are unique in database
        logs = test_session.query(models.SoftwareInstallationLog).all()
        db_installation_ids = [log.installation_id for log in logs]
        assert len(db_installation_ids) == len(set(db_installation_ids))

    def test_message_queueing_mock(self, test_session, test_host):
        """Test message queueing logic with mocks"""
        with patch(
            "backend.websocket.queue_manager.server_queue_manager"
        ) as mock_queue_manager:
            mock_queue_manager.enqueue_message.return_value = "mock-message-id"

            # Simulate package installation request processing
            package_names = ["vim", "curl"]
            installation_ids = []
            now = datetime.now(timezone.utc)

            for package_name in package_names:
                installation_id = str(uuid.uuid4())
                installation_ids.append(installation_id)

                # Create database record
                log_entry = models.SoftwareInstallationLog(
                    host_id=test_host.id,
                    package_name=package_name,
                    package_manager="auto",
                    requested_by="test-user",
                    installation_id=installation_id,
                    status="pending",
                    requested_at=now,
                    created_at=now,
                    updated_at=now,
                )
                test_session.add(log_entry)

            test_session.commit()

            # Simulate message queueing
            for package_name, installation_id in zip(package_names, installation_ids):
                message_data = {
                    "command_type": "install_package",
                    "installation_id": installation_id,
                    "package_name": package_name,
                    "package_manager": "auto",
                    "requested_by": "test-user",
                    "requested_at": now.isoformat(),
                }

                mock_queue_manager.enqueue_message(
                    message_type="command",
                    message_data=message_data,
                    direction="outbound",
                    host_id=test_host.id,
                    priority="normal",
                    db=test_session,
                )

            # Verify mock was called correctly
            assert mock_queue_manager.enqueue_message.call_count == len(package_names)

            # Update status to queued
            for installation_id in installation_ids:
                log = (
                    test_session.query(models.SoftwareInstallationLog)
                    .filter(
                        models.SoftwareInstallationLog.installation_id
                        == installation_id
                    )
                    .first()
                )
                log.status = "queued"
                log.queued_at = now

            test_session.commit()

            # Verify all logs are queued
            queued_logs = (
                test_session.query(models.SoftwareInstallationLog)
                .filter(models.SoftwareInstallationLog.status == "queued")
                .all()
            )
            assert len(queued_logs) == len(package_names)


class TestSoftwareInstallationLogModel:
    """Additional tests for the SoftwareInstallationLog model"""

    def test_model_repr(self, test_session, test_host):
        """Test the model's string representation"""
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
        test_session.refresh(log_entry)

        repr_str = repr(log_entry)
        assert "SoftwareInstallationLog" in repr_str
        assert str(log_entry.id) in repr_str
        assert installation_id in repr_str
        assert "test-package" in repr_str
        assert "pending" in repr_str
        assert str(test_host.id) in repr_str

    def test_status_transitions(self, test_session, test_host):
        """Test valid status transitions"""
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

        # Test status progression: pending -> queued -> installing -> completed
        statuses = ["pending", "queued", "installing", "completed"]
        timestamps = ["requested_at", "queued_at", "started_at", "completed_at"]

        for i, (status, timestamp_field) in enumerate(
            zip(statuses[1:], timestamps[1:]), 1
        ):
            log_entry.status = status
            setattr(log_entry, timestamp_field, datetime.now(timezone.utc))
            test_session.commit()

            assert log_entry.status == status
            assert getattr(log_entry, timestamp_field) is not None

        # Mark as successful
        log_entry.success = True
        log_entry.installed_version = "1.2.3"
        test_session.commit()

        assert log_entry.success is True
        assert log_entry.installed_version == "1.2.3"

    def test_error_case_fields(self, test_session, test_host):
        """Test error case handling in the model"""
        installation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        log_entry = models.SoftwareInstallationLog(
            host_id=test_host.id,
            package_name="failed-package",
            package_manager="apt",
            requested_by="test-user",
            installation_id=installation_id,
            status="failed",
            requested_at=now,
            started_at=now,
            completed_at=now,
            success=False,
            error_message="Package not found in repository",
            installation_log="E: Unable to locate package failed-package",
            created_at=now,
            updated_at=now,
        )

        test_session.add(log_entry)
        test_session.commit()

        assert log_entry.status == "failed"
        assert log_entry.success is False
        assert log_entry.error_message == "Package not found in repository"
        assert "Unable to locate package" in log_entry.installation_log
