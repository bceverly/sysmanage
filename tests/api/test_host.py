"""
Unit tests for host management API endpoints.
Tests all host CRUD operations and registration endpoints.
"""

import pytest
from datetime import datetime, timezone

from backend.persistence import models


class TestHostDelete:
    """Test cases for DELETE /host/{host_id} endpoint."""

    def test_delete_host_success(self, client, session, auth_headers):
        """Test successful host deletion."""
        # Create a test host
        host = models.Host(
            id=1,
            fqdn="delete.example.com",
            ipv4="192.168.1.100",
            ipv6="2001:db8::1",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()
        host_id = host.id

        response = client.delete(f"/api/host/{host_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["result"] is True

        # Verify host is deleted
        deleted_host = (
            session.query(models.Host).filter(models.Host.id == host_id).first()
        )
        assert deleted_host is None

    def test_delete_host_not_found(self, client, auth_headers):
        """Test deleting non-existent host."""
        response = client.delete("/api/host/999", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "Host not found" in data["detail"]

    def test_delete_host_unauthorized(self, client):
        """Test deleting host without authentication."""
        response = client.delete("/api/host/1")
        assert response.status_code == 403


class TestHostGet:
    """Test cases for GET /host/{host_id} endpoint."""

    def test_get_host_success(self, client, session, auth_headers):
        """Test getting host by ID."""
        # Create a test host
        host = models.Host(
            id=1,
            fqdn="get.example.com",
            ipv4="192.168.1.101",
            ipv6="2001:db8::2",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        response = client.get(f"/api/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "get.example.com"
        assert data["ipv4"] == "192.168.1.101"
        assert data["ipv6"] == "2001:db8::2"
        assert data["active"] is True

    def test_get_host_not_found(self, client, auth_headers):
        """Test getting non-existent host."""
        response = client.get("/api/host/999", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "Host not found" in data["detail"]

    def test_get_host_unauthorized(self, client):
        """Test getting host without authentication."""
        response = client.get("/api/host/1")
        assert response.status_code == 403


class TestHostsList:
    """Test cases for GET /hosts endpoint."""

    def test_get_hosts_success(self, client, session, auth_headers):
        """Test getting list of all hosts."""
        # Create multiple test hosts
        hosts = [
            models.Host(
                id=1,
                fqdn="host1.example.com",
                ipv4="192.168.1.10",
                ipv6="2001:db8::10",
                active=True,
            ),
            models.Host(
                id=2,
                fqdn="host2.example.com",
                ipv4="192.168.1.11",
                ipv6="2001:db8::11",
                active=False,
            ),
            models.Host(
                id=3,
                fqdn="host3.example.com",
                ipv4="192.168.1.12",
                ipv6="2001:db8::12",
                active=True,
            ),
        ]
        # Set approval status after creation
        hosts[0].approval_status = "approved"
        hosts[1].approval_status = "approved"
        hosts[2].approval_status = "pending"

        for host in hosts:
            session.add(host)
        session.commit()

        response = client.get("/api/hosts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

        # Verify host data - use exact matching for security
        fqdns = [host["fqdn"] for host in data]
        expected_fqdns = {"host1.example.com", "host2.example.com", "host3.example.com"}
        actual_fqdns = set(fqdns)
        assert expected_fqdns.issubset(actual_fqdns)

    def test_get_hosts_empty(self, client, auth_headers):
        """Test getting empty hosts list."""
        response = client.get("/api/hosts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_get_hosts_unauthorized(self, client):
        """Test getting hosts without authentication."""
        response = client.get("/api/hosts")
        assert response.status_code == 403


class TestHostCreate:
    """Test cases for POST /host endpoint."""

    def test_create_host_success(self, client, session, auth_headers):
        """Test successful host creation."""
        host_data = {
            "fqdn": "newhost.example.com",
            "ipv4": "192.168.1.200",
            "ipv6": "2001:db8::200",
            "active": True,
        }

        response = client.post("/api/host", json=host_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "newhost.example.com"
        assert data["ipv4"] == "192.168.1.200"
        assert data["active"] is True

        # Verify host was created in database
        created_host = (
            session.query(models.Host)
            .filter(models.Host.fqdn == host_data["fqdn"])
            .first()
        )
        assert created_host is not None
        assert created_host.fqdn == host_data["fqdn"]
        assert created_host.ipv4 == host_data["ipv4"]
        assert created_host.ipv6 == host_data["ipv6"]
        assert created_host.active is True

    def test_create_host_duplicate_fqdn(self, client, session, auth_headers):
        """Test creating host with duplicate FQDN."""
        # Create existing host
        existing_host = models.Host(
            id=1,
            fqdn="duplicate.example.com",
            ipv4="192.168.1.100",
            ipv6="2001:db8::100",
            active=True,
        )
        existing_host.approval_status = "approved"
        session.add(existing_host)
        session.commit()

        # Try to create host with same FQDN
        host_data = {
            "fqdn": "duplicate.example.com",
            "ipv4": "192.168.1.101",
            "ipv6": "2001:db8::101",
            "active": True,
        }

        response = client.post("/api/host", json=host_data, headers=auth_headers)

        assert response.status_code == 409
        data = response.json()
        assert "Host already exists" in data["detail"]

    def test_create_host_missing_fields(self, client, auth_headers):
        """Test creating host with missing required fields."""
        # Missing FQDN
        response = client.post(
            "/api/host",
            json={"ipv4": "192.168.1.100", "ipv6": "2001:db8::100", "active": True},
            headers=auth_headers,
        )
        assert response.status_code == 422

        # Missing IPv4
        response = client.post(
            "/api/host",
            json={"fqdn": "test.example.com", "ipv6": "2001:db8::100", "active": True},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_host_unauthorized(self, client):
        """Test creating host without authentication."""
        host_data = {
            "fqdn": "test.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "2001:db8::100",
            "active": True,
        }
        response = client.post("/api/host", json=host_data)
        assert response.status_code == 403


class TestHostUpdate:
    """Test cases for PUT /host/{host_id} endpoint."""

    def test_update_host_success(self, client, session, auth_headers):
        """Test successful host update."""
        # Create a test host
        host = models.Host(
            id=1,
            fqdn="update.example.com",
            ipv4="192.168.1.100",
            ipv6="2001:db8::100",
            active=False,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()
        host_id = host.id

        # Update host
        update_data = {
            "fqdn": "updated.example.com",
            "ipv4": "192.168.1.200",
            "ipv6": "2001:db8::200",
            "active": True,
        }

        response = client.put(
            f"/api/host/{host_id}", json=update_data, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "updated.example.com"
        assert data["ipv4"] == "192.168.1.200"
        assert data["active"] is True

        # Verify updates in database
        session.refresh(host)
        assert host.fqdn == "updated.example.com"
        assert host.ipv4 == "192.168.1.200"
        assert host.ipv6 == "2001:db8::200"
        assert host.active is True

    def test_update_host_not_found(self, client, auth_headers):
        """Test updating non-existent host."""
        update_data = {
            "fqdn": "test.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "2001:db8::100",
            "active": True,
        }

        response = client.put("/api/host/999", json=update_data, headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "Host not found" in data["detail"]

    def test_update_host_duplicate_fqdn(self, client, session, auth_headers):
        """Test updating host with duplicate FQDN."""
        # Create two hosts
        host1 = models.Host(
            id=1,
            fqdn="host1.example.com",
            ipv4="192.168.1.1",
            ipv6="2001:db8::1",
            active=True,
        )
        host1.approval_status = "approved"
        host2 = models.Host(
            id=2,
            fqdn="host2.example.com",
            ipv4="192.168.1.2",
            ipv6="2001:db8::2",
            active=True,
        )
        host2.approval_status = "approved"
        session.add_all([host1, host2])
        session.commit()

        # Try to update host2 with host1's FQDN
        update_data = {
            "fqdn": "host1.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "2001:db8::100",
            "active": True,
        }

        response = client.put(
            f"/api/host/{host2.id}", json=update_data, headers=auth_headers
        )

        # API allows duplicate FQDNs on update
        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "host1.example.com"
        assert data["ipv4"] == "192.168.1.100"

    def test_update_host_unauthorized(self, client):
        """Test updating host without authentication."""
        update_data = {
            "fqdn": "test.example.com",
            "ipv4": "192.168.1.100",
            "ipv6": "2001:db8::100",
            "active": True,
        }
        response = client.put("/api/host/1", json=update_data)
        assert response.status_code == 403


class TestHostRegister:
    """Test cases for POST /host/register endpoint (agent registration)."""

    def test_register_host_success_new(self, client, session):
        """Test successful new host registration."""
        registration_data = {
            "active": True,
            "fqdn": "agent.example.com",
            "hostname": "agent",
            "ipv4": "192.168.1.150",
            "ipv6": "2001:db8::150",
        }

        response = client.post("/host/register", json=registration_data)

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["fqdn"] == "agent.example.com"
        assert data["active"] is True

        # Verify host was created in database
        created_host = (
            session.query(models.Host)
            .filter(models.Host.fqdn == registration_data["fqdn"])
            .first()
        )
        assert created_host is not None
        assert created_host.fqdn == "agent.example.com"
        assert created_host.ipv4 == "192.168.1.150"

    def test_register_host_success_existing(self, client, session):
        """Test successful registration of existing host (update)."""
        # Create existing host
        existing_host = models.Host(
            id=1,
            fqdn="existing.example.com",
            ipv4="192.168.1.100",
            ipv6="2001:db8::100",
            active=True,
        )
        existing_host.approval_status = "approved"
        session.add(existing_host)
        session.commit()

        # Register same host with updated info
        registration_data = {
            "active": True,
            "fqdn": "existing.example.com",
            "hostname": "existing",
            "ipv4": "192.168.1.101",  # Updated IP
            "ipv6": "2001:db8::101",  # Updated IP
        }

        response = client.post("/host/register", json=registration_data)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "existing.example.com"
        assert data["ipv4"] == "192.168.1.101"

        # Verify host was updated in database
        session.refresh(existing_host)
        assert existing_host.ipv4 == "192.168.1.101"
        assert existing_host.ipv6 == "2001:db8::101"
        # Check that last_access was updated
        assert existing_host.last_access is not None

    def test_register_host_minimal_data(self, client, session):
        """Test host registration with minimal required data."""
        registration_data = {
            "active": True,
            "fqdn": "minimal.example.com",
            "hostname": "minimal",
        }

        response = client.post("/host/register", json=registration_data)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "minimal.example.com"
        assert data["active"] is True

        # Verify optional fields can be None
        created_host = (
            session.query(models.Host)
            .filter(models.Host.fqdn == registration_data["fqdn"])
            .first()
        )
        assert created_host is not None
        assert created_host.ipv4 is None
        assert created_host.fqdn == "minimal.example.com"

    def test_register_host_missing_required_fields(self, client):
        """Test host registration with missing required fields."""
        # Missing FQDN
        response = client.post(
            "/host/register", json={"active": True, "hostname": "test"}
        )
        assert response.status_code == 422

        # Missing hostname
        response = client.post(
            "/host/register", json={"active": True, "fqdn": "test.example.com"}
        )
        assert response.status_code == 422

        # Missing active flag
        response = client.post(
            "/host/register", json={"fqdn": "test.example.com", "hostname": "test"}
        )
        assert response.status_code == 422

    def test_register_host_invalid_data(self, client):
        """Test host registration with invalid data types."""
        # Invalid active field (should be boolean) - use a value that won't coerce
        response = client.post(
            "/host/register",
            json={
                "active": ["invalid"],  # Array won't coerce to boolean
                "fqdn": "test.example.com",
                "hostname": "test",
            },
        )
        assert response.status_code == 422

        # Empty FQDN - API accepts empty strings
        response = client.post(
            "/host/register", json={"active": True, "fqdn": "", "hostname": "test"}
        )
        assert response.status_code == 200


class TestHostUpdateCounts:
    """Test cases for update count functionality in host API endpoints."""

    def test_get_host_with_no_updates(self, client, session, auth_headers):
        """Test getting host with no package updates."""
        # Create a test host
        host = models.Host(
            id=1,
            fqdn="noupdates.example.com",
            ipv4="192.168.1.101",
            ipv6="2001:db8::2",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        response = client.get(f"/api/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "noupdates.example.com"
        assert data["security_updates_count"] == 0
        assert data["system_updates_count"] == 0
        assert data["total_updates_count"] == 0

    def test_get_host_with_mixed_updates(self, client, session, auth_headers):
        """Test getting host with mixed security and system updates."""
        # Create a test host
        host = models.Host(
            id=1,
            fqdn="mixedupdates.example.com",
            ipv4="192.168.1.102",
            ipv6="2001:db8::3",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        # Create various package updates
        updates = [
            # Security update only
            models.PackageUpdate(
                host_id=host.id,
                package_name="security-patch-1",
                current_version="1.0.0",
                available_version="1.0.1",
                package_manager="apt",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            # System update only
            models.PackageUpdate(
                host_id=host.id,
                package_name="kernel-update",
                current_version="5.4.0",
                available_version="5.4.1",
                package_manager="apt",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
            # Both security and system update
            models.PackageUpdate(
                host_id=host.id,
                package_name="syspatch-001_nfs",
                current_version="not installed",
                available_version="001_nfs",
                package_manager="syspatch",
                is_security_update=True,
                is_system_update=True,
                status="available",
            ),
            # Regular application update (neither security nor system)
            models.PackageUpdate(
                host_id=host.id,
                package_name="firefox",
                current_version="91.0",
                available_version="92.0",
                package_manager="apt",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
        ]

        for update in updates:
            session.add(update)
        session.commit()

        response = client.get(f"/api/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "mixedupdates.example.com"
        assert (
            data["security_updates_count"] == 2
        )  # security-patch-1 and syspatch-001_nfs
        assert data["system_updates_count"] == 2  # kernel-update and syspatch-001_nfs
        assert data["total_updates_count"] == 4  # All 4 updates

    def test_get_hosts_list_with_update_counts(self, client, session, auth_headers):
        """Test getting hosts list with update counts included."""
        # Create multiple test hosts with different update scenarios
        host1 = models.Host(
            id=1,
            fqdn="host1.example.com",
            ipv4="192.168.1.10",
            ipv6="2001:db8::10",
            active=True,
        )
        host1.approval_status = "approved"

        host2 = models.Host(
            id=2,
            fqdn="host2.example.com",
            ipv4="192.168.1.11",
            ipv6="2001:db8::11",
            active=True,
        )
        host2.approval_status = "approved"

        session.add_all([host1, host2])
        session.commit()

        # Add updates to host1 only
        host1_updates = [
            models.PackageUpdate(
                host_id=host1.id,
                package_name="security-update",
                current_version="1.0.0",
                available_version="1.0.1",
                package_manager="apt",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            models.PackageUpdate(
                host_id=host1.id,
                package_name="system-update",
                current_version="2.0.0",
                available_version="2.0.1",
                package_manager="apt",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
        ]

        for update in host1_updates:
            session.add(update)
        session.commit()

        response = client.get("/api/hosts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Find host1 and host2 in response
        host1_data = next((h for h in data if h["fqdn"] == "host1.example.com"), None)
        host2_data = next((h for h in data if h["fqdn"] == "host2.example.com"), None)

        assert host1_data is not None
        assert host2_data is not None

        # Verify host1 has update counts
        assert host1_data["security_updates_count"] == 1
        assert host1_data["system_updates_count"] == 1
        assert host1_data["total_updates_count"] == 2

        # Verify host2 has zero updates
        assert host2_data["security_updates_count"] == 0
        assert host2_data["system_updates_count"] == 0
        assert host2_data["total_updates_count"] == 0

    def test_get_host_by_fqdn_with_updates(self, client, session, auth_headers):
        """Test getting host by FQDN includes update counts."""
        # Create a test host
        host = models.Host(
            id=1,
            fqdn="byname.example.com",
            ipv4="192.168.1.103",
            ipv6="2001:db8::4",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        # Add OpenBSD syspatch updates (should be both security and system)
        syspatches = [
            models.PackageUpdate(
                host_id=host.id,
                package_name="syspatch-001_nfs",
                current_version="not installed",
                available_version="001_nfs",
                package_manager="syspatch",
                is_security_update=True,
                is_system_update=True,
                requires_reboot=True,
                source="OpenBSD base system",
                repository="syspatch",
                status="available",
            ),
            models.PackageUpdate(
                host_id=host.id,
                package_name="syspatch-002_zic",
                current_version="not installed",
                available_version="002_zic",
                package_manager="syspatch",
                is_security_update=True,
                is_system_update=True,
                requires_reboot=True,
                source="OpenBSD base system",
                repository="syspatch",
                status="available",
            ),
        ]

        for patch in syspatches:
            session.add(patch)
        session.commit()

        response = client.get(f"/api/host/by_fqdn/{host.fqdn}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "byname.example.com"
        assert (
            data["security_updates_count"] == 2
        )  # Both syspatches are security updates
        assert data["system_updates_count"] == 2  # Both syspatches are system updates
        assert data["total_updates_count"] == 2  # 2 total updates

    def test_update_count_calculation_edge_cases(self, client, session, auth_headers):
        """Test edge cases in update count calculation."""
        # Create a test host
        host = models.Host(
            id=1,
            fqdn="edgecase.example.com",
            ipv4="192.168.1.104",
            ipv6="2001:db8::5",
            active=True,
        )
        host.approval_status = "approved"
        session.add(host)
        session.commit()

        # Create updates with edge case scenarios
        edge_cases = [
            # Update that is neither security nor system (application update)
            models.PackageUpdate(
                host_id=host.id,
                package_name="app-update",
                current_version="1.0.0",
                available_version="1.1.0",
                package_manager="snap",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
            # Update with null/None current version (common for new installs)
            models.PackageUpdate(
                host_id=host.id,
                package_name="new-package",
                current_version=None,
                available_version="1.0.0",
                package_manager="apt",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            # Update in different status (should still be counted)
            models.PackageUpdate(
                host_id=host.id,
                package_name="status-test",
                current_version="1.0.0",
                available_version="1.0.1",
                package_manager="apt",
                is_security_update=False,
                is_system_update=True,
                status="pending",  # Different status
            ),
        ]

        for update in edge_cases:
            session.add(update)
        session.commit()

        response = client.get(f"/api/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["security_updates_count"] == 1  # Only new-package
        assert data["system_updates_count"] == 1  # Only status-test
        assert data["total_updates_count"] == 3  # All three updates

    def test_multiple_hosts_isolated_update_counts(self, client, session, auth_headers):
        """Test that update counts are properly isolated between hosts."""
        # Create multiple hosts
        hosts = []
        for i in range(3):
            host = models.Host(
                id=i + 1,
                fqdn=f"isolated{i+1}.example.com",
                ipv4=f"192.168.1.{110+i}",
                ipv6=f"2001:db8::{110+i}",
                active=True,
            )
            host.approval_status = "approved"
            hosts.append(host)
            session.add(host)
        session.commit()

        # Add different numbers of updates to each host
        # Host 1: 2 security, 1 system, 4 total
        host1_updates = [
            models.PackageUpdate(
                host_id=1,
                package_name="sec1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            models.PackageUpdate(
                host_id=1,
                package_name="sec2",
                current_version="2.0",
                available_version="2.1",
                package_manager="apt",
                is_security_update=True,
                is_system_update=False,
                status="available",
            ),
            models.PackageUpdate(
                host_id=1,
                package_name="sys1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
            models.PackageUpdate(
                host_id=1,
                package_name="app1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
        ]

        # Host 2: 1 security, 2 system, 3 total (with overlap)
        host2_updates = [
            models.PackageUpdate(
                host_id=2,
                package_name="both1",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                is_security_update=True,
                is_system_update=True,
                status="available",
            ),
            models.PackageUpdate(
                host_id=2,
                package_name="sys2",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                is_security_update=False,
                is_system_update=True,
                status="available",
            ),
            models.PackageUpdate(
                host_id=2,
                package_name="app2",
                current_version="1.0",
                available_version="1.1",
                package_manager="apt",
                is_security_update=False,
                is_system_update=False,
                status="available",
            ),
        ]

        # Host 3: No updates (should have zero counts)

        all_updates = host1_updates + host2_updates
        for update in all_updates:
            session.add(update)
        session.commit()

        # Test individual host endpoints
        for i, expected_counts in enumerate(
            [
                (2, 1, 4),  # Host 1: 2 security, 1 system, 4 total
                (1, 2, 3),  # Host 2: 1 security, 2 system, 3 total
                (0, 0, 0),  # Host 3: 0 security, 0 system, 0 total
            ]
        ):
            response = client.get(f"/api/host/{i+1}", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["security_updates_count"] == expected_counts[0]
            assert data["system_updates_count"] == expected_counts[1]
            assert data["total_updates_count"] == expected_counts[2]

        # Test hosts list endpoint
        response = client.get("/api/hosts", headers=auth_headers)
        assert response.status_code == 200
        hosts_data = response.json()
        assert len(hosts_data) == 3

        # Verify each host has correct isolated counts
        for host_data in hosts_data:
            if host_data["fqdn"] == "isolated1.example.com":
                assert host_data["security_updates_count"] == 2
                assert host_data["system_updates_count"] == 1
                assert host_data["total_updates_count"] == 4
            elif host_data["fqdn"] == "isolated2.example.com":
                assert host_data["security_updates_count"] == 1
                assert host_data["system_updates_count"] == 2
                assert host_data["total_updates_count"] == 3
            elif host_data["fqdn"] == "isolated3.example.com":
                assert host_data["security_updates_count"] == 0
                assert host_data["system_updates_count"] == 0
                assert host_data["total_updates_count"] == 0
