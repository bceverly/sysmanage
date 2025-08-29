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

        response = client.delete(f"/host/{host_id}", headers=auth_headers)

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
        response = client.delete("/host/999", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "Host not found" in data["detail"]

    def test_delete_host_unauthorized(self, client):
        """Test deleting host without authentication."""
        response = client.delete("/host/1")
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

        response = client.get(f"/host/{host.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["fqdn"] == "get.example.com"
        assert data["ipv4"] == "192.168.1.101"
        assert data["ipv6"] == "2001:db8::2"
        assert data["active"] is True

    def test_get_host_not_found(self, client, auth_headers):
        """Test getting non-existent host."""
        response = client.get("/host/999", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "Host not found" in data["detail"]

    def test_get_host_unauthorized(self, client):
        """Test getting host without authentication."""
        response = client.get("/host/1")
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

        response = client.get("/hosts", headers=auth_headers)

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
        response = client.get("/hosts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_get_hosts_unauthorized(self, client):
        """Test getting hosts without authentication."""
        response = client.get("/hosts")
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

        response = client.post("/host", json=host_data, headers=auth_headers)

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

        response = client.post("/host", json=host_data, headers=auth_headers)

        assert response.status_code == 409
        data = response.json()
        assert "Host already exists" in data["detail"]

    def test_create_host_missing_fields(self, client, auth_headers):
        """Test creating host with missing required fields."""
        # Missing FQDN
        response = client.post(
            "/host",
            json={"ipv4": "192.168.1.100", "ipv6": "2001:db8::100", "active": True},
            headers=auth_headers,
        )
        assert response.status_code == 422

        # Missing IPv4
        response = client.post(
            "/host",
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
        response = client.post("/host", json=host_data)
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
            f"/host/{host_id}", json=update_data, headers=auth_headers
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

        response = client.put("/host/999", json=update_data, headers=auth_headers)

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
            f"/host/{host2.id}", json=update_data, headers=auth_headers
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
        response = client.put("/host/1", json=update_data)
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
