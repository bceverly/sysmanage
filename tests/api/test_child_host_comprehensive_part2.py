# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Comprehensive unit tests for child host management (part 2).

Split from test_child_host_comprehensive.py:
- Parent-child relationship tests
- Auto-approve token tests
- WSL-specific tests
- Pydantic model tests
- Error handling and edge case tests
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Boolean,
    DateTime,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from backend.api.child_host_models import (
    ChildHostResponse,
    CreateChildHostRequest,
    CreateWslChildHostRequest,
    DistributionResponse,
    VirtualizationSupportResponse,
    ConfigureKvmNetworkingRequest,
)
from backend.persistence.models.core import GUID

# =============================================================================
# TEST DATABASE SETUP
# =============================================================================

TestBase = declarative_base()


class TestHostChild(TestBase):
    """Test version of HostChild model for unit tests."""

    __tablename__ = "host_child"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    parent_host_id = Column(GUID(), nullable=False)
    child_host_id = Column(GUID(), nullable=True)
    child_name = Column(String(255), nullable=False)
    child_type = Column(String(50), nullable=False)
    distribution = Column(String(100), nullable=True)
    distribution_version = Column(String(50), nullable=True)
    install_path = Column(String(500), nullable=True)
    default_username = Column(String(100), nullable=True)
    hostname = Column(String(255), nullable=True)
    wsl_guid = Column(String(36), nullable=True)
    auto_approve_token = Column(String(36), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    installation_step = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    installed_at = Column(DateTime, nullable=True)


class TestChildHostDistribution(TestBase):
    """Test version of ChildHostDistribution model for unit tests."""

    __tablename__ = "child_host_distribution"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    child_type = Column(String(50), nullable=False)
    distribution_name = Column(String(100), nullable=False)
    distribution_version = Column(String(50), nullable=False)
    display_name = Column(String(200), nullable=False)
    install_identifier = Column(String(200), nullable=True)
    executable_name = Column(String(100), nullable=True)
    cloud_image_url = Column(String(500), nullable=True)
    iso_url = Column(String(500), nullable=True)
    agent_install_method = Column(String(50), nullable=True)
    agent_install_commands = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    min_agent_version = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


class TestHost(TestBase):
    """Test version of Host model for unit tests."""

    __tablename__ = "host"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    fqdn = Column(String(255), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    platform = Column(String(50), nullable=True)
    is_agent_privileged = Column(Boolean, nullable=True, default=False)
    reboot_required = Column(Boolean, nullable=False, default=False)
    reboot_required_reason = Column(String(255), nullable=True)
    virtualization_types = Column(String, nullable=True)
    virtualization_capabilities = Column(String, nullable=True)


class TestUser(TestBase):
    """Test version of User model for unit tests."""

    __tablename__ = "user"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    userid = Column(String(255), nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    hashed_password = Column(String(255), nullable=False)
    _role_cache = None

    def load_role_cache(self, session):
        pass

        self._role_cache = MagicMock()
        self._role_cache.has_role.return_value = True

    def has_role(self, role):
        if self._role_cache is None:
            return False
        return self._role_cache.has_role(role)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def test_engine():
    """Create an in-memory SQLite database for testing.

    Uses ``yield`` + ``engine.dispose()`` so each test cleanly closes its
    connection pool. Without dispose, the underlying sqlite3.Connection
    objects leak and surface as ResourceWarnings in unrelated tests when
    the garbage collector eventually sweeps them.
    """
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestBase.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def test_session(test_engine):
    """Create a database session for testing."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_host(test_session):
    """Create a sample host for testing."""
    host = TestHost(
        id=uuid.uuid4(),
        fqdn="testhost.example.com",
        active=True,
        platform="Linux",
        is_agent_privileged=True,
    )
    test_session.add(host)
    test_session.commit()
    test_session.refresh(host)
    return host


@pytest.fixture
def sample_windows_host(test_session):
    """Create a sample Windows host for testing."""
    host = TestHost(
        id=uuid.uuid4(),
        fqdn="windowshost.example.com",
        active=True,
        platform="Windows",
        is_agent_privileged=True,
    )
    test_session.add(host)
    test_session.commit()
    test_session.refresh(host)
    return host


@pytest.fixture
def sample_openbsd_host(test_session):
    """Create a sample OpenBSD host for testing."""
    host = TestHost(
        id=uuid.uuid4(),
        fqdn="openbsdhost.example.com",
        active=True,
        platform="OpenBSD",
        is_agent_privileged=True,
    )
    test_session.add(host)
    test_session.commit()
    test_session.refresh(host)
    return host


@pytest.fixture
def sample_freebsd_host(test_session):
    """Create a sample FreeBSD host for testing."""
    host = TestHost(
        id=uuid.uuid4(),
        fqdn="freebsdhost.example.com",
        active=True,
        platform="FreeBSD",
        is_agent_privileged=True,
    )
    test_session.add(host)
    test_session.commit()
    test_session.refresh(host)
    return host


@pytest.fixture
def sample_user(test_session):
    """Create a sample user for testing."""
    user = TestUser(
        id=uuid.uuid4(),
        userid="admin@sysmanage.org",
        active=True,
        hashed_password="hashed",
    )
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    user.load_role_cache(test_session)
    return user


@pytest.fixture
def sample_distribution(test_session):
    """Create a sample distribution for testing."""
    dist = TestChildHostDistribution(
        id=uuid.uuid4(),
        child_type="wsl",
        distribution_name="Ubuntu",
        distribution_version="24.04",
        display_name="Ubuntu 24.04 LTS (Noble)",
        install_identifier="Ubuntu-24.04",
        executable_name="ubuntu2404.exe",
        agent_install_method="apt_launchpad",
        agent_install_commands=json.dumps(
            ["sudo apt update", "sudo apt install sysmanage-agent"]
        ),
        is_active=True,
    )
    test_session.add(dist)
    test_session.commit()
    test_session.refresh(dist)
    return dist


@pytest.fixture
def sample_lxd_distribution(test_session):
    """Create a sample LXD distribution for testing."""
    dist = TestChildHostDistribution(
        id=uuid.uuid4(),
        child_type="lxd",
        distribution_name="Ubuntu",
        distribution_version="22.04",
        display_name="Ubuntu 22.04 LTS (Jammy)",
        install_identifier="ubuntu:22.04",
        agent_install_method="apt_launchpad",
        agent_install_commands=json.dumps(
            ["sudo apt update", "sudo apt install sysmanage-agent"]
        ),
        is_active=True,
    )
    test_session.add(dist)
    test_session.commit()
    test_session.refresh(dist)
    return dist


@pytest.fixture
def sample_kvm_distribution(test_session):
    """Create a sample KVM distribution for testing."""
    dist = TestChildHostDistribution(
        id=uuid.uuid4(),
        child_type="kvm",
        distribution_name="Debian",
        distribution_version="12",
        display_name="Debian 12 (Bookworm)",
        install_identifier="debian12",
        cloud_image_url="https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2",
        agent_install_method="apt",
        agent_install_commands=json.dumps(
            ["sudo apt update", "sudo apt install sysmanage-agent"]
        ),
        is_active=True,
    )
    test_session.add(dist)
    test_session.commit()
    test_session.refresh(dist)
    return dist


@pytest.fixture
def sample_child_host(test_session, sample_host):
    """Create a sample child host for testing."""
    child = TestHostChild(
        id=uuid.uuid4(),
        parent_host_id=sample_host.id,
        child_name="Ubuntu-24.04",
        child_type="wsl",
        distribution="Ubuntu",
        distribution_version="24.04",
        hostname="wsl-ubuntu",
        status="running",
        default_username="testuser",
    )
    test_session.add(child)
    test_session.commit()
    test_session.refresh(child)
    return child


@pytest.fixture
def sample_lxd_child_host(test_session, sample_host):
    """Create a sample LXD child host for testing."""
    child = TestHostChild(
        id=uuid.uuid4(),
        parent_host_id=sample_host.id,
        child_name="my-container",
        child_type="lxd",
        distribution="Ubuntu",
        distribution_version="22.04",
        hostname="container-ubuntu",
        status="running",
        default_username="ubuntu",
    )
    test_session.add(child)
    test_session.commit()
    test_session.refresh(child)
    return child


@pytest.fixture
def sample_kvm_child_host(test_session, sample_host):
    """Create a sample KVM child host for testing."""
    child = TestHostChild(
        id=uuid.uuid4(),
        parent_host_id=sample_host.id,
        child_name="test-vm",
        child_type="kvm",
        distribution="Debian",
        distribution_version="12",
        hostname="kvm-debian",
        status="running",
        default_username="debian",
    )
    test_session.add(child)
    test_session.commit()
    test_session.refresh(child)
    return child


# =============================================================================
# PARENT-CHILD RELATIONSHIP TESTS
# =============================================================================


class TestParentChildRelationship:
    """Tests for parent-child host relationships."""

    def test_multiple_children_same_parent(self, test_session, sample_host):
        """Test multiple child hosts under the same parent."""
        for i in range(5):
            child = TestHostChild(
                parent_host_id=sample_host.id,
                child_name=f"child-{i}",
                child_type="lxd",
                status="running",
            )
            test_session.add(child)
        test_session.commit()

        children = (
            test_session.query(TestHostChild)
            .filter(TestHostChild.parent_host_id == sample_host.id)
            .all()
        )
        assert len(children) == 5

    def test_child_host_linked_to_registered_host(self, test_session, sample_host):
        """Test child host linked to its registered host record."""
        registered_host_id = uuid.uuid4()
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_host_id=registered_host_id,  # Link to registered host
            child_name="linked-vm",
            child_type="kvm",
            status="running",
        )
        test_session.add(child)
        test_session.commit()

        assert child.child_host_id == registered_host_id

    def test_children_isolated_between_hosts(
        self, test_session, sample_host, sample_windows_host
    ):
        """Test that children are properly isolated between parent hosts."""
        # Create children for Linux host
        for i in range(3):
            child = TestHostChild(
                parent_host_id=sample_host.id,
                child_name=f"linux-child-{i}",
                child_type="lxd",
                status="running",
            )
            test_session.add(child)

        # Create children for Windows host
        for i in range(2):
            child = TestHostChild(
                parent_host_id=sample_windows_host.id,
                child_name=f"windows-child-{i}",
                child_type="wsl",
                status="running",
            )
            test_session.add(child)

        test_session.commit()

        linux_children = (
            test_session.query(TestHostChild)
            .filter(TestHostChild.parent_host_id == sample_host.id)
            .all()
        )
        windows_children = (
            test_session.query(TestHostChild)
            .filter(TestHostChild.parent_host_id == sample_windows_host.id)
            .all()
        )

        assert len(linux_children) == 3
        assert len(windows_children) == 2

        # Verify no cross-contamination
        for child in linux_children:
            assert child.child_type == "lxd"
        for child in windows_children:
            assert child.child_type == "wsl"


# =============================================================================
# AUTO-APPROVE TOKEN TESTS
# =============================================================================


class TestAutoApproveToken:
    """Tests for auto-approve token functionality."""

    def test_create_child_with_auto_approve_token(self, test_session, sample_host):
        """Test creating child host with auto-approve token."""
        token = str(uuid.uuid4())
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="auto-approve-vm",
            child_type="kvm",
            status="creating",
            auto_approve_token=token,
        )
        test_session.add(child)
        test_session.commit()

        assert child.auto_approve_token == token

    def test_lookup_child_by_auto_approve_token(self, test_session, sample_host):
        """Test looking up child host by auto-approve token."""
        token = str(uuid.uuid4())
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="token-lookup-vm",
            child_type="lxd",
            status="creating",
            auto_approve_token=token,
        )
        test_session.add(child)
        test_session.commit()

        found = (
            test_session.query(TestHostChild)
            .filter(TestHostChild.auto_approve_token == token)
            .first()
        )

        assert found is not None
        assert found.child_name == "token-lookup-vm"

    def test_clear_auto_approve_token_after_registration(
        self, test_session, sample_host
    ):
        """Test clearing auto-approve token after successful registration."""
        token = str(uuid.uuid4())
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="registered-vm",
            child_type="kvm",
            status="creating",
            auto_approve_token=token,
        )
        test_session.add(child)
        test_session.commit()

        # Simulate registration completion
        child.status = "running"
        child.auto_approve_token = None  # Clear token after use
        child.child_host_id = uuid.uuid4()  # Link to registered host
        test_session.commit()

        assert child.auto_approve_token is None
        assert child.child_host_id is not None


# =============================================================================
# WSL-SPECIFIC TESTS
# =============================================================================


class TestWslSpecific:
    """Tests for WSL-specific functionality."""

    def test_wsl_guid_storage(self, test_session, sample_windows_host):
        """Test storing WSL GUID for instance identification."""
        wsl_guid = str(uuid.uuid4())
        child = TestHostChild(
            parent_host_id=sample_windows_host.id,
            child_name="Ubuntu-24.04",
            child_type="wsl",
            status="running",
            wsl_guid=wsl_guid,
        )
        test_session.add(child)
        test_session.commit()

        assert child.wsl_guid == wsl_guid

    def test_lookup_wsl_by_guid(self, test_session, sample_windows_host):
        """Test looking up WSL instance by GUID."""
        wsl_guid = str(uuid.uuid4())
        child = TestHostChild(
            parent_host_id=sample_windows_host.id,
            child_name="Ubuntu-22.04",
            child_type="wsl",
            status="running",
            wsl_guid=wsl_guid,
        )
        test_session.add(child)
        test_session.commit()

        found = (
            test_session.query(TestHostChild)
            .filter(
                TestHostChild.parent_host_id == sample_windows_host.id,
                TestHostChild.wsl_guid == wsl_guid,
            )
            .first()
        )

        assert found is not None
        assert found.child_name == "Ubuntu-22.04"

    def test_wsl_guid_prevents_stale_delete(self, test_session, sample_windows_host):
        """Test that WSL GUID can be used to prevent stale delete commands."""
        old_guid = str(uuid.uuid4())
        new_guid = str(uuid.uuid4())

        # Create child with new GUID
        child = TestHostChild(
            parent_host_id=sample_windows_host.id,
            child_name="Ubuntu",
            child_type="wsl",
            status="running",
            wsl_guid=new_guid,
        )
        test_session.add(child)
        test_session.commit()

        # Simulate checking if a delete command with old GUID should proceed
        matching = (
            test_session.query(TestHostChild)
            .filter(
                TestHostChild.parent_host_id == sample_windows_host.id,
                TestHostChild.child_name == "Ubuntu",
                TestHostChild.wsl_guid == old_guid,
            )
            .first()
        )

        # Should not find a match (delete command would be rejected)
        assert matching is None


# =============================================================================
# PYDANTIC MODEL TESTS
# =============================================================================


class TestPydanticModels:
    """Tests for Pydantic request/response models."""

    def test_child_host_response_model(self):
        """Test ChildHostResponse model creation."""
        response = ChildHostResponse(
            id="123e4567-e89b-12d3-a456-426614174000",
            parent_host_id="456e7890-e89b-12d3-a456-426614174000",
            child_name="test-vm",
            child_type="kvm",
            status="running",
            created_at="2024-01-01T00:00:00Z",
        )
        assert response.child_name == "test-vm"
        assert response.status == "running"

    def test_create_child_host_request_validation(self):
        """Test CreateChildHostRequest validation."""
        request = CreateChildHostRequest(
            child_type="lxd",
            distribution_id="123e4567-e89b-12d3-a456-426614174000",
            hostname="test-container",
            username="ubuntu",
            password="securepassword",
        )
        assert request.child_type == "lxd"
        assert request.auto_approve is False  # Default

    def test_create_child_host_request_with_auto_approve(self):
        """Test CreateChildHostRequest with auto_approve enabled."""
        request = CreateChildHostRequest(
            child_type="kvm",
            distribution_id="123e4567-e89b-12d3-a456-426614174000",
            hostname="auto-vm",
            username="debian",
            password="securepassword",
            auto_approve=True,
        )
        assert request.auto_approve is True

    def test_create_wsl_child_host_request_defaults(self):
        """Test CreateWslChildHostRequest default values."""
        request = CreateWslChildHostRequest(
            distribution="Ubuntu-24.04",
            hostname="wsl-host",
            username="wsluser",
            password="wslpass",
        )
        assert request.child_type == "wsl"
        assert request.memory == "2G"
        assert request.cpus == 2
        assert request.disk_size == "20G"

    def test_create_wsl_child_host_request_kvm(self):
        """Test CreateWslChildHostRequest for KVM."""
        request = CreateWslChildHostRequest(
            child_type="kvm",
            distribution="debian12",
            hostname="kvm-host",
            username="kvmuser",
            password="kvmpass",
            vm_name="test-vm",
            memory="4G",
            disk_size="50G",
            cpus=4,
        )
        assert request.child_type == "kvm"
        assert request.vm_name == "test-vm"
        assert request.memory == "4G"

    def test_distribution_response_model(self):
        """Test DistributionResponse model."""
        response = DistributionResponse(
            id="123",
            child_type="wsl",
            distribution_name="Ubuntu",
            distribution_version="24.04",
            display_name="Ubuntu 24.04 LTS",
            is_active=True,
        )
        assert response.distribution_name == "Ubuntu"
        assert response.is_active is True

    def test_virtualization_support_response_model(self):
        """Test VirtualizationSupportResponse model."""
        response = VirtualizationSupportResponse(
            supported_types=["wsl", "hyperv"],
            wsl_enabled=True,
            wsl_version=2,
            requires_reboot=False,
        )
        assert "wsl" in response.supported_types
        assert response.wsl_version == 2

    def test_configure_kvm_networking_request_nat(self):
        """Test ConfigureKvmNetworkingRequest for NAT mode."""
        request = ConfigureKvmNetworkingRequest(
            mode="nat",
            network_name="default",
        )
        assert request.mode == "nat"
        assert request.network_name == "default"

    def test_configure_kvm_networking_request_bridged(self):
        """Test ConfigureKvmNetworkingRequest for bridged mode."""
        request = ConfigureKvmNetworkingRequest(
            mode="bridged",
            bridge="br0",
        )
        assert request.mode == "bridged"
        assert request.bridge == "br0"


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_child_host_with_error_state(self, test_session, sample_host):
        """Test child host in error state with error message."""
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="error-vm",
            child_type="kvm",
            status="error",
            error_message="Failed to allocate resources: insufficient memory",
        )
        test_session.add(child)
        test_session.commit()

        assert child.status == "error"
        assert "insufficient memory" in child.error_message

    def test_child_host_installation_failure(self, test_session, sample_host):
        """Test child host installation failure."""
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="failed-install-vm",
            child_type="lxd",
            status="error",
            installation_step="Installing agent",
            error_message="Agent installation timed out",
        )
        test_session.add(child)
        test_session.commit()

        assert child.installation_step == "Installing agent"
        assert "timed out" in child.error_message

    def test_long_error_message(self, test_session, sample_host):
        """Test handling of long error messages."""
        long_error = "Error: " + "A" * 10000
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="long-error-vm",
            child_type="kvm",
            status="error",
            error_message=long_error,
        )
        test_session.add(child)
        test_session.commit()

        assert len(child.error_message) > 10000


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_child_host_with_special_characters_in_name(
        self, test_session, sample_host
    ):
        """Test child host with special characters in name."""
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="test_vm-2024.01",
            child_type="kvm",
            status="running",
        )
        test_session.add(child)
        test_session.commit()

        assert child.child_name == "test_vm-2024.01"

    def test_child_host_with_unicode_in_username(self, test_session, sample_host):
        """Test child host with unicode in username."""
        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="unicode-vm",
            child_type="lxd",
            status="running",
            default_username="usuario",
        )
        test_session.add(child)
        test_session.commit()

        assert child.default_username == "usuario"

    def test_empty_distribution_version(self, test_session):
        """Test distribution with empty version."""
        dist = TestChildHostDistribution(
            child_type="custom",
            distribution_name="CustomOS",
            distribution_version="",
            display_name="Custom OS (No Version)",
            is_active=True,
        )
        test_session.add(dist)
        test_session.commit()

        assert dist.distribution_version == ""

    def test_child_host_timestamps(self, test_session, sample_host):
        """Test child host timestamp fields."""
        before_create = datetime.now(timezone.utc).replace(tzinfo=None)

        child = TestHostChild(
            parent_host_id=sample_host.id,
            child_name="timestamp-vm",
            child_type="kvm",
            status="running",
        )
        test_session.add(child)
        test_session.commit()

        after_create = datetime.now(timezone.utc).replace(tzinfo=None)

        assert before_create <= child.created_at <= after_create
        assert before_create <= child.updated_at <= after_create
