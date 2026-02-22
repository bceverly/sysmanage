"""
Tests for the reboot orchestration API endpoints.

Tests cover:
- GET /api/host/{host_id}/reboot/pre-check
- POST /api/host/{host_id}/reboot/orchestrated
- GET /api/host/{host_id}/reboot/orchestration/{orch_id}
- License/permission checks
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestRebootPreCheck:
    """Tests for the reboot pre-check endpoint."""

    def test_pre_check_no_children(self, client, db_session):
        """Test pre-check on a host with no child hosts."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        response = client.get(f"/api/host/{host.id}/reboot/pre-check")
        assert response.status_code == 200
        data = response.json()
        assert data["has_running_children"] is False
        assert data["running_count"] == 0
        assert data["running_children"] == []

    def test_pre_check_with_running_children(self, client, db_session):
        """Test pre-check on a host with running child hosts."""
        from backend.persistence.models import Host, HostChild

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
            child_name="ubuntu-vm",
            child_type="kvm",
            status="running",
        )
        child2 = HostChild(
            parent_host_id=host.id,
            child_name="stopped-vm",
            child_type="kvm",
            status="stopped",
        )
        db_session.add(child1)
        db_session.add(child2)
        db_session.commit()

        response = client.get(f"/api/host/{host.id}/reboot/pre-check")
        assert response.status_code == 200
        data = response.json()
        assert data["has_running_children"] is True
        assert data["running_count"] == 1
        assert data["total_children"] == 2
        assert len(data["running_children"]) == 1
        assert data["running_children"][0]["child_name"] == "ubuntu-vm"

    def test_pre_check_host_not_found(self, client):
        """Test pre-check with non-existent host."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/host/{fake_id}/reboot/pre-check")
        assert response.status_code == 404

    def test_pre_check_container_engine_status(self, client, db_session):
        """Test pre-check reports container engine availability."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        # Without Pro+ module
        response = client.get(f"/api/host/{host.id}/reboot/pre-check")
        assert response.status_code == 200
        data = response.json()
        assert data["has_container_engine"] is False


class TestOrchestratedReboot:
    """Tests for the orchestrated reboot endpoint."""

    def test_orchestrated_reboot_requires_pro_plus(self, client, db_session):
        """Test that orchestrated reboot requires Pro+ license."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        response = client.post(f"/api/host/{host.id}/reboot/orchestrated")
        assert response.status_code == 402

    def test_orchestrated_reboot_inactive_host(self, client, db_session):
        """Test orchestrated reboot on inactive host."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=False,
        )
        db_session.add(host)
        db_session.commit()

        with patch("backend.api.reboot_orchestration.module_loader") as mock_loader:
            mock_loader.get_module.return_value = MagicMock()  # Pro+ available

            response = client.post(f"/api/host/{host.id}/reboot/orchestrated")
            assert response.status_code == 400

    def test_orchestrated_reboot_no_running_children(self, client, db_session):
        """Test orchestrated reboot when no children are running."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        with patch("backend.api.reboot_orchestration.module_loader") as mock_loader:
            mock_loader.get_module.return_value = MagicMock()

            response = client.post(f"/api/host/{host.id}/reboot/orchestrated")
            assert response.status_code == 400

    def test_orchestrated_reboot_success(self, client, db_session):
        """Test successful orchestrated reboot initiation."""
        from backend.persistence.models import Host, HostChild, RebootOrchestration

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
            child_name="ubuntu-vm",
            child_type="kvm",
            status="running",
        )
        db_session.add(child)
        db_session.commit()

        with patch("backend.api.reboot_orchestration.module_loader") as mock_loader:
            mock_loader.get_module.return_value = MagicMock()

            with patch(
                "backend.api.reboot_orchestration.QueueOperations"
            ) as mock_queue_cls:
                mock_queue = MagicMock()
                mock_queue_cls.return_value = mock_queue

                response = client.post(f"/api/host/{host.id}/reboot/orchestrated")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shutting_down"
        assert data["child_count"] == 1
        assert "orchestration_id" in data

        # Verify orchestration record was created
        orch = db_session.query(RebootOrchestration).first()
        assert orch is not None
        assert orch.status == "shutting_down"
        assert orch.initiated_by == "test_user@example.com"

    def test_orchestrated_reboot_host_not_found(self, client):
        """Test orchestrated reboot with non-existent host."""
        fake_id = str(uuid.uuid4())

        with patch("backend.api.reboot_orchestration.module_loader") as mock_loader:
            mock_loader.get_module.return_value = MagicMock()

            response = client.post(f"/api/host/{fake_id}/reboot/orchestrated")
            assert response.status_code == 404


class TestGetOrchestrationStatus:
    """Tests for the orchestration status endpoint."""

    def test_get_orchestration_status(self, client, db_session):
        """Test getting orchestration status."""
        from backend.persistence.models import Host, RebootOrchestration

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
            }
        ]

        orch = RebootOrchestration(
            parent_host_id=host.id,
            status="shutting_down",
            child_hosts_snapshot=json.dumps(snapshot),
            initiated_by="test_user@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        response = client.get(f"/api/host/{host.id}/reboot/orchestration/{orch.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shutting_down"
        assert data["initiated_by"] == "test_user@example.com"
        assert len(data["child_hosts_snapshot"]) == 1

    def test_get_orchestration_not_found(self, client, db_session):
        """Test getting non-existent orchestration."""
        from backend.persistence.models import Host

        host = Host(
            fqdn="parent.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        db_session.add(host)
        db_session.commit()

        fake_orch_id = str(uuid.uuid4())
        response = client.get(
            f"/api/host/{host.id}/reboot/orchestration/{fake_orch_id}"
        )
        assert response.status_code == 404

    def test_get_orchestration_wrong_host(self, client, db_session):
        """Test getting orchestration with wrong host ID."""
        from backend.persistence.models import Host, RebootOrchestration

        host1 = Host(
            fqdn="parent1.example.com",
            ipv4="192.168.1.100",
            ipv6="::1",
            active=True,
        )
        host2 = Host(
            fqdn="parent2.example.com",
            ipv4="192.168.1.101",
            ipv6="::1",
            active=True,
        )
        db_session.add(host1)
        db_session.add(host2)
        db_session.commit()

        orch = RebootOrchestration(
            parent_host_id=host1.id,
            status="shutting_down",
            child_hosts_snapshot="[]",
            initiated_by="test_user@example.com",
        )
        db_session.add(orch)
        db_session.commit()

        # Try to access orchestration using wrong host ID
        response = client.get(f"/api/host/{host2.id}/reboot/orchestration/{orch.id}")
        assert response.status_code == 404
