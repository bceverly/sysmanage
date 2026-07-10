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
    """Create a shared in-memory SQLite database for testing.

    ``engine.dispose()`` in the teardown closes the underlying
    sqlite3 connections so they don't surface as ResourceWarnings
    later when the GC catches them.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def test_session(test_engine):
    """Create a test database session + a baseline ``test-user`` row.

    The install/uninstall endpoints look up the operator via
    ``session.query(User).filter(User.userid == current_user).first()``
    and 401 if the row is missing.  Insert one here so the ``client``
    fixture's ``get_current_user='test-user'`` override has a real
    User to resolve to.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()
    user = models.User(
        userid="test-user",
        active=True,
        hashed_password="not-checked-in-tests",
    )
    session.add(user)
    session.commit()
    yield session
    session.close()


@pytest.fixture
def test_host(test_session, test_engine):
    """Create a test host in the database.

    ``Host.id`` is a ``GUID()`` column (UUID under the hood); the
    fixture used to insert ``id=1`` and then ``filter(Host.id == 1)``
    which round-trips as ``uuid.UUID("1")`` and raises ``ValueError:
    badly formed hexadecimal UUID string`` on read.  Use a real UUID.
    """
    host_uuid = uuid.uuid4()
    connection = test_engine.connect()
    connection.execute(
        models.Host.__table__.insert(),
        {
            "id": host_uuid,
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
    host = test_session.query(models.Host).filter(models.Host.id == host_uuid).first()
    yield host


@pytest.fixture
def client(test_session):
    """Create a test client with database session override + auth bypass.

    The package install router uses ``Depends(JWTBearer())`` at the
    router level + ``Depends(get_current_user)`` per-endpoint.  Tests
    pass a fake ``Bearer test-token`` which would fail real JWT
    decoding, so:

      * Patch ``decode_jwt`` to return a valid payload for any token
        — that lets ``JWTBearer.verify_jwt`` accept the fake header.
      * Override ``get_current_user`` to return a fixed user id.

    Both unmount on fixture teardown.
    """
    import time
    from unittest.mock import patch as _patch

    from backend.auth.auth_bearer import get_current_user

    def override_get_db():
        yield test_session

    def override_get_current_user():
        return "test-user"

    app.dependency_overrides[db.get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    fake_payload = {"user_id": "test-user", "expires": time.time() + 3600}
    # The install/uninstall endpoints build their OWN ``sessionmaker``
    # via ``db_module.get_engine()`` for the RBAC + audit-log queries
    # (rather than using the ``Depends(get_db)`` session).  Steer that
    # call at the test engine so the queries hit the in-memory DB that
    # has our test-user row.
    test_engine_value = test_session.get_bind()
    # ``User.has_role`` lazily walks the user_security_roles join.  The
    # test DB has the User row but no role assignments, so any role
    # check would return False.  Patch to always-true so the tests
    # exercise the install/uninstall flow rather than RBAC plumbing.
    with _patch(
        "backend.auth.auth_bearer.decode_jwt", return_value=fake_payload
    ), _patch.object(models.User, "has_role", return_value=True), _patch(
        "backend.persistence.db.get_engine", return_value=test_engine_value
    ):
        # Don't use the TestClient context manager — that would run
        # the FastAPI lifespan, which spins up background workers
        # (federation sync/push, alerting, etc.) that then raise
        # ``CancelledError`` on shutdown and show as teardown errors.
        # The endpoints we exercise here don't need lifespan startup.
        test_client = TestClient(app)
        yield test_client
    app.dependency_overrides = {}


@pytest.fixture
def mock_auth_header():
    """Mock authentication header"""
    return {"Authorization": "Bearer test-token"}


class TestPackageInstallationAPI:
    """Test cases for package installation API endpoints"""

    def test_install_packages_success(
        self, client, test_session, test_host, mock_auth_header
    ):
        """Test successful package installation request"""
        with patch(
            "backend.websocket.queue_manager.server_queue_manager.enqueue_message"
        ) as mock_enqueue:
            mock_enqueue.return_value = "mock-message-id"

            response = client.post(
                f"/api/v1/packages/install/{test_host.id}",
                json={
                    "package_names": ["vim", "curl", "htop"],
                    "requested_by": "test-user",
                },
                headers=mock_auth_header,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Phase 8 API refactor: the response shape changed from a list
        # of per-package ``installation_ids`` to a SINGLE ``request_id``
        # — multiple packages now group under one UUID (the docstring
        # on ``install_packages_operation`` calls this "UUID-based
        # grouping").  The agent reports completion with that one ID.
        assert data["request_id"]
        assert "Successfully queued 3 packages for installation" in data["message"]

        # Phase 8 schema: the endpoint writes ONE InstallationRequest
        # (carrying the shared ``request_id``) plus one InstallationPackage
        # per package, grouped by ``installation_request_id``.  The endpoint
        # commits on its OWN sessionmaker (pointed at the same engine), so
        # ``expire_all()`` drops the test session's identity map and forces
        # a re-read of the rows the endpoint just committed.
        test_session.expire_all()
        requests = (
            test_session.query(models.InstallationRequest)
            .filter(models.InstallationRequest.host_id == test_host.id)
            .all()
        )
        assert len(requests) == 1
        request_row = requests[0]
        assert str(request_row.id) == data["request_id"]
        # Created "pending", then advanced to "in_progress" once the
        # command message is queued to the agent.
        assert request_row.status == "in_progress"
        assert request_row.requested_by == "test-user"
        assert request_row.operation_type == "install"

        # One InstallationPackage row per package, all under the request.
        packages = (
            test_session.query(models.InstallationPackage)
            .filter(
                models.InstallationPackage.installation_request_id == request_row.id
            )
            .all()
        )
        assert len(packages) == 3
        assert {pkg.package_name for pkg in packages} == {"vim", "curl", "htop"}
        for pkg in packages:
            # The agent picks the real manager; the request defaults to "auto".
            assert pkg.package_manager == "auto"

    def test_install_packages_host_not_found(self, client, mock_auth_header):
        """Test package installation with non-existent host"""
        response = client.post(
            "/api/v1/packages/install/999",
            json={"package_names": ["vim"], "requested_by": "test-user"},
            headers=mock_auth_header,
        )

        assert response.status_code == 404
        assert "Host not found or not active" in response.json()["detail"]

    def test_install_packages_empty_list(self, client, test_host, mock_auth_header):
        """Test package installation with empty package list"""
        response = client.post(
            f"/api/v1/packages/install/{test_host.id}",
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
            "/api/v1/packages/install/2",
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

        # Update status to installing.  SQLite stores DateTimes as
        # naive strings; the value we read back loses ``tzinfo``, so
        # compare the naive form to avoid a tz-mismatch failure.
        new_now = datetime.now(timezone.utc)
        log_entry.status = "installing"
        log_entry.started_at = new_now
        test_session.commit()

        assert log_entry.status == "installing"
        assert log_entry.started_at == new_now.replace(tzinfo=None)

        # Update status to completed
        completion_time = datetime.now(timezone.utc)
        log_entry.status = "completed"
        log_entry.success = True
        log_entry.completed_at = completion_time
        log_entry.installed_version = "1.0.0"
        test_session.commit()

        assert log_entry.status == "completed"
        assert log_entry.success is True
        # SQLite strips tzinfo on storage — compare naive (see comment
        # above on ``started_at``).
        assert log_entry.completed_at == completion_time.replace(tzinfo=None)
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
        # Phase 8.x rename: the WS handler ``handle_package_installation_status``
        # was generalised to ``handle_installation_status`` (now covers OS-level
        # package installs AND binary installs).  Alias-imported here to keep
        # the test body's call sites unchanged.
        from backend.api.message_handlers import (
            handle_installation_status as handle_package_installation_status,
        )

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
        # Phase 8.x rename: the WS handler ``handle_package_installation_status``
        # was generalised to ``handle_installation_status`` (now covers OS-level
        # package installs AND binary installs).  Alias-imported here to keep
        # the test body's call sites unchanged.
        from backend.api.message_handlers import (
            handle_installation_status as handle_package_installation_status,
        )

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
        # Phase 8.x rename: the WS handler ``handle_package_installation_status``
        # was generalised to ``handle_installation_status`` (now covers OS-level
        # package installs AND binary installs).  Alias-imported here to keep
        # the test body's call sites unchanged.
        from backend.api.message_handlers import (
            handle_installation_status as handle_package_installation_status,
        )

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
        # The error envelope is ``{message_type, error_type, message, data}``
        # — the human-readable text lives under ``message``, not ``error``.
        assert "Missing installation_id" in result["message"]
