"""
Tests for the reboot orchestration model and service.

Tests cover:
- RebootOrchestration model creation and fields
- Orchestration service state machine (shutdown progress, agent reconnect, restart progress)
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

# =============================================================================
# MODEL TESTS
# =============================================================================


class TestRebootOrchestrationModel:
    """Tests for the RebootOrchestration SQLAlchemy model."""

    def test_model_creation(self, db_session):
        """Test creating a RebootOrchestration record."""
        from backend.persistence.models import Host, RebootOrchestration

        # Create a host first
        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        snapshot = [
            {
                "id": str(uuid.uuid4()),
                "child_name": "ubuntu-vm",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            }
        ]

        orch = RebootOrchestration(
            id=uuid.uuid4(),
            parent_host_id=host.id,
            status="pending_shutdown",
            child_hosts_snapshot=json.dumps(snapshot),
            initiated_by="test_user@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        # Verify
        result = db_session.query(RebootOrchestration).first()
        assert result is not None
        assert result.parent_host_id == host.id
        assert result.status == "pending_shutdown"
        assert result.shutdown_timeout_seconds == 120
        assert result.initiated_by == "test_user@example.com"
        assert json.loads(result.child_hosts_snapshot) == snapshot
        assert result.child_hosts_restart_status is None
        assert result.error_message is None

    def test_model_default_values(self, db_session):
        """Test default values for RebootOrchestration fields."""
        from backend.persistence.models import Host, RebootOrchestration

        host = Host(
            fqdn="parent2.example.com",
            ipv4="192.168.1.101",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        orch = RebootOrchestration(
            parent_host_id=host.id,
            child_hosts_snapshot="[]",
            initiated_by="admin@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        result = db_session.query(RebootOrchestration).first()
        assert result.id is not None
        assert result.status == "pending_shutdown"
        assert result.shutdown_timeout_seconds == 120
        assert result.initiated_at is not None

    def test_model_repr(self, db_session):
        """Test the string representation of RebootOrchestration."""
        from backend.persistence.models import Host, RebootOrchestration

        host = Host(
            fqdn="parent3.example.com",
            ipv4="192.168.1.102",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="rebooting",
            child_hosts_snapshot="[]",
            initiated_by="admin@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        result = db_session.query(RebootOrchestration).first()
        repr_str = repr(result)
        assert "RebootOrchestration" in repr_str
        assert "rebooting" in repr_str

    def test_model_cascade_delete(self, db_session):
        """Test that deleting the parent host cascades to orchestration records."""
        from sqlalchemy import text
        from backend.persistence.models import Host, RebootOrchestration

        # SQLite requires PRAGMA foreign_keys = ON to enforce CASCADE
        db_session.execute(text("PRAGMA foreign_keys = ON"))

        host = Host(
            fqdn="parent4.example.com",
            ipv4="192.168.1.103",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        orch = RebootOrchestration(
            parent_host_id=host.id,
            child_hosts_snapshot="[]",
            initiated_by="admin@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        assert db_session.query(RebootOrchestration).count() == 1

        db_session.delete(host)
        db_session.commit()

        assert db_session.query(RebootOrchestration).count() == 0

    def test_model_status_values(self, db_session):
        """Test that various status values can be set."""
        from backend.persistence.models import Host, RebootOrchestration

        host = Host(
            fqdn="parent5.example.com",
            ipv4="192.168.1.104",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        valid_statuses = [
            "pending_shutdown",
            "shutting_down",
            "rebooting",
            "pending_restart",
            "restarting",
            "completed",
            "failed",
        ]

        for status in valid_statuses:
            orch = RebootOrchestration(
                parent_host_id=host.id,
                status=status,
                child_hosts_snapshot="[]",
                initiated_by="admin@example.com",
            )
            db_session.add(orch)
            db_session.commit()

        results = db_session.query(RebootOrchestration).all()
        assert len(results) == len(valid_statuses)


# =============================================================================
# SERVICE TESTS
# =============================================================================


class TestCheckShutdownProgress:
    """Tests for the check_shutdown_progress service function."""

    def test_no_active_orchestration(self, db_session):
        """Test that nothing happens when there's no active orchestration."""
        from backend.services.reboot_orchestration_service import (
            check_shutdown_progress,
        )

        # Should not raise
        check_shutdown_progress(db_session, uuid.uuid4())

    def test_children_still_running(self, db_session):
        """Test that orchestration stays in shutting_down when children are still running."""
        from backend.persistence.models import Host, HostChild, RebootOrchestration
        from backend.services.reboot_orchestration_service import (
            check_shutdown_progress,
        )

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        child = HostChild(
            parent_host_id=host.id,
            child_name="test-vm",
            child_type="kvm",
            status="running",
        )
        db_session.add(child)

        snapshot = [
            {
                "id": str(child.id),
                "child_name": "test-vm",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            }
        ]

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="shutting_down",
            child_hosts_snapshot=json.dumps(snapshot),
            initiated_by="test@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        with patch("backend.services.reboot_orchestration_service.QueueOperations"):
            check_shutdown_progress(db_session, host.id)

        db_session.refresh(orch)
        assert orch.status == "shutting_down"

    def test_all_children_stopped(self, db_session):
        """Test that orchestration transitions to rebooting when all children are stopped."""
        from backend.persistence.models import Host, HostChild, RebootOrchestration
        from backend.services.reboot_orchestration_service import (
            check_shutdown_progress,
        )

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        child = HostChild(
            parent_host_id=host.id,
            child_name="test-vm",
            child_type="kvm",
            status="stopped",  # Already stopped
        )
        db_session.add(child)

        snapshot = [
            {
                "id": str(child.id),
                "child_name": "test-vm",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            }
        ]

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="shutting_down",
            child_hosts_snapshot=json.dumps(snapshot),
            initiated_by="test@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        with patch(
            "backend.services.reboot_orchestration_service.QueueOperations"
        ) as mock_queue_cls:
            mock_queue = MagicMock()
            mock_queue_cls.return_value = mock_queue

            check_shutdown_progress(db_session, host.id)

        db_session.refresh(orch)
        assert orch.status == "rebooting"
        assert orch.shutdown_completed_at is not None
        assert orch.reboot_issued_at is not None

    def test_shutdown_timeout_proceeds(self, db_session):
        """Test that orchestration proceeds after timeout even with running children."""
        from backend.persistence.models import Host, HostChild, RebootOrchestration
        from backend.services.reboot_orchestration_service import (
            check_shutdown_progress,
        )

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        child = HostChild(
            parent_host_id=host.id,
            child_name="stuck-vm",
            child_type="kvm",
            status="running",  # Still running
        )
        db_session.add(child)

        snapshot = [
            {
                "id": str(child.id),
                "child_name": "stuck-vm",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            }
        ]

        # Set initiated_at to 200 seconds ago (past the 120s timeout)
        old_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=200
        )

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="shutting_down",
            child_hosts_snapshot=json.dumps(snapshot),
            initiated_by="test@example.com",
            initiated_at=old_time,
            shutdown_timeout_seconds=120,
        )
        db_session.add(orch)
        db_session.commit()

        with patch(
            "backend.services.reboot_orchestration_service.QueueOperations"
        ) as mock_queue_cls:
            mock_queue = MagicMock()
            mock_queue_cls.return_value = mock_queue

            check_shutdown_progress(db_session, host.id)

        db_session.refresh(orch)
        assert orch.status == "rebooting"


class TestHandleAgentReconnect:
    """Tests for the handle_agent_reconnect service function."""

    def test_no_active_orchestration(self, db_session):
        """Test that nothing happens when there's no orchestration in rebooting state."""
        from backend.services.reboot_orchestration_service import (
            handle_agent_reconnect,
        )

        handle_agent_reconnect(db_session, uuid.uuid4())

    def test_agent_reconnect_starts_children(self, db_session):
        """Test that agent reconnect transitions to restarting and enqueues start commands."""
        from backend.persistence.models import Host, RebootOrchestration
        from backend.services.reboot_orchestration_service import (
            handle_agent_reconnect,
        )

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        snapshot = [
            {
                "id": str(uuid.uuid4()),
                "child_name": "vm1",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            },
            {
                "id": str(uuid.uuid4()),
                "child_name": "vm2",
                "child_type": "lxd",
                "pre_reboot_status": "running",
            },
        ]

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="rebooting",
            child_hosts_snapshot=json.dumps(snapshot),
            initiated_by="test@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        with patch(
            "backend.services.reboot_orchestration_service.QueueOperations"
        ) as mock_queue_cls:
            mock_queue = MagicMock()
            mock_queue_cls.return_value = mock_queue

            handle_agent_reconnect(db_session, host.id)

            # Should have enqueued 2 start commands
            assert mock_queue.enqueue_message.call_count == 2

        db_session.refresh(orch)
        assert orch.status == "restarting"
        assert orch.agent_reconnected_at is not None
        assert orch.child_hosts_restart_status is not None

        restart_status = json.loads(orch.child_hosts_restart_status)
        assert len(restart_status) == 2
        assert all(entry["restart_status"] == "pending" for entry in restart_status)


class TestCheckRestartProgress:
    """Tests for the check_restart_progress service function."""

    def test_no_active_orchestration(self, db_session):
        """Test that nothing happens when there's no orchestration in restarting state."""
        from backend.services.reboot_orchestration_service import (
            check_restart_progress,
        )

        check_restart_progress(db_session, uuid.uuid4())

    def test_partial_restart(self, db_session):
        """Test that orchestration stays in restarting when some children haven't started."""
        from backend.persistence.models import Host, HostChild, RebootOrchestration
        from backend.services.reboot_orchestration_service import (
            check_restart_progress,
        )

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        child1 = HostChild(
            parent_host_id=host.id,
            child_name="vm1",
            child_type="kvm",
            status="running",
        )
        child2 = HostChild(
            parent_host_id=host.id,
            child_name="vm2",
            child_type="kvm",
            status="stopped",  # Not yet started
        )
        db_session.add(child1)
        db_session.add(child2)

        snapshot = [
            {
                "id": str(child1.id),
                "child_name": "vm1",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            },
            {
                "id": str(child2.id),
                "child_name": "vm2",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            },
        ]

        restart_status = [
            {
                "id": str(child1.id),
                "child_name": "vm1",
                "restart_status": "pending",
                "error": None,
            },
            {
                "id": str(child2.id),
                "child_name": "vm2",
                "restart_status": "pending",
                "error": None,
            },
        ]

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="restarting",
            child_hosts_snapshot=json.dumps(snapshot),
            child_hosts_restart_status=json.dumps(restart_status),
            initiated_by="test@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        check_restart_progress(db_session, host.id)

        db_session.refresh(orch)
        assert orch.status == "restarting"  # Still in progress

    def test_all_children_restarted(self, db_session):
        """Test that orchestration completes when all children are running."""
        from backend.persistence.models import Host, HostChild, RebootOrchestration
        from backend.services.reboot_orchestration_service import (
            check_restart_progress,
        )

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        child1 = HostChild(
            parent_host_id=host.id,
            child_name="vm1",
            child_type="kvm",
            status="running",
        )
        child2 = HostChild(
            parent_host_id=host.id,
            child_name="vm2",
            child_type="kvm",
            status="running",
        )
        db_session.add(child1)
        db_session.add(child2)

        snapshot = [
            {
                "id": str(child1.id),
                "child_name": "vm1",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            },
            {
                "id": str(child2.id),
                "child_name": "vm2",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            },
        ]

        restart_status = [
            {
                "id": str(child1.id),
                "child_name": "vm1",
                "restart_status": "pending",
                "error": None,
            },
            {
                "id": str(child2.id),
                "child_name": "vm2",
                "restart_status": "pending",
                "error": None,
            },
        ]

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="restarting",
            child_hosts_snapshot=json.dumps(snapshot),
            child_hosts_restart_status=json.dumps(restart_status),
            initiated_by="test@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        check_restart_progress(db_session, host.id)

        db_session.refresh(orch)
        assert orch.status == "completed"
        assert orch.restart_completed_at is not None
        assert orch.error_message is None

    def test_restart_with_failures(self, db_session):
        """Test that orchestration completes with error message when some children fail."""
        from backend.persistence.models import Host, HostChild, RebootOrchestration
        from backend.services.reboot_orchestration_service import (
            check_restart_progress,
        )

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        child1 = HostChild(
            parent_host_id=host.id,
            child_name="vm1",
            child_type="kvm",
            status="running",
        )
        child2 = HostChild(
            parent_host_id=host.id,
            child_name="vm2",
            child_type="kvm",
            status="error",
            error_message="Failed to start",
        )
        db_session.add(child1)
        db_session.add(child2)

        snapshot = [
            {
                "id": str(child1.id),
                "child_name": "vm1",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            },
            {
                "id": str(child2.id),
                "child_name": "vm2",
                "child_type": "kvm",
                "pre_reboot_status": "running",
            },
        ]

        restart_status = [
            {
                "id": str(child1.id),
                "child_name": "vm1",
                "restart_status": "pending",
                "error": None,
            },
            {
                "id": str(child2.id),
                "child_name": "vm2",
                "restart_status": "pending",
                "error": None,
            },
        ]

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="restarting",
            child_hosts_snapshot=json.dumps(snapshot),
            child_hosts_restart_status=json.dumps(restart_status),
            initiated_by="test@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        check_restart_progress(db_session, host.id)

        db_session.refresh(orch)
        assert orch.status == "completed"
        assert orch.error_message is not None
        assert "1" in orch.error_message  # 1 of 2 failed
