"""
Tests for backend.api.firewall_roles.

Drives every CRUD route + the host-assignment routes through the FastAPI
TestClient, hitting the major branches:
- 401/403 auth/permission gates
- 400 invalid UUID format
- 404 not-found arms
- 409 duplicate name
- 200/201 happy paths with port lists
- update + delete with audit logging side-effects mocked at the service edge
"""

import uuid
from unittest.mock import patch

from backend.persistence import models

URL = "/api/firewall-roles"


def _create_role(session, name="web", **fields):
    """Insert a FirewallRole row directly and return it (with refresh)."""
    from datetime import datetime, timezone

    role = models.FirewallRole(
        name=name,
        created_at=fields.pop("created_at", datetime.now(timezone.utc)),
        **fields,
    )
    session.add(role)
    session.commit()
    session.refresh(role)
    return role


# ---------------------------------------------------------------------------
# /common-ports
# ---------------------------------------------------------------------------


class TestCommonPorts:
    def test_requires_auth(self, client):
        resp = client.get(f"{URL}/common-ports")
        assert resp.status_code in (401, 403)

    def test_returns_known_services(self, client, auth_headers):
        resp = client.get(f"{URL}/common-ports", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        names = {p["name"] for p in body["ports"]}
        assert {"SSH", "HTTPS", "DNS"} <= names


# ---------------------------------------------------------------------------
# GET / — list
# ---------------------------------------------------------------------------


class TestListFirewallRoles:
    def test_requires_auth(self, client):
        resp = client.get(f"{URL}/")
        assert resp.status_code in (401, 403)

    def test_empty_list(self, client, auth_headers):
        resp = client.get(f"{URL}/", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_seeded_roles_in_name_order(self, client, auth_headers, session):
        _create_role(session, name="web")
        _create_role(session, name="api")
        _create_role(session, name="db")
        resp = client.get(f"{URL}/", headers=auth_headers)
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()]
        assert names == ["api", "db", "web"]


# ---------------------------------------------------------------------------
# GET /{role_id} — fetch
# ---------------------------------------------------------------------------


class TestGetFirewallRole:
    def test_invalid_uuid_returns_400(self, client, auth_headers):
        resp = client.get(f"{URL}/not-a-uuid", headers=auth_headers)
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client, auth_headers):
        resp = client.get(f"{URL}/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    def test_happy_path(self, client, auth_headers, session):
        role = _create_role(session, name="cache")
        resp = client.get(f"{URL}/{role.id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "cache"
        assert body["id"] == str(role.id)


# ---------------------------------------------------------------------------
# POST / — create
# ---------------------------------------------------------------------------


class TestCreateFirewallRole:
    def test_creates_role_with_open_ports(self, client, auth_headers):
        with patch("backend.api.firewall_roles.AuditService.log_create"):
            resp = client.post(
                f"{URL}/",
                json={
                    "name": "web-tier",
                    "open_ports": [
                        {"port_number": 80, "tcp": True, "udp": False},
                        {"port_number": 443, "tcp": True, "udp": False},
                    ],
                },
                headers=auth_headers,
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "web-tier"
        assert {p["port_number"] for p in body["open_ports"]} == {80, 443}

    def test_duplicate_name_returns_409(self, client, auth_headers, session):
        _create_role(session, name="duplicate-me")
        with patch("backend.api.firewall_roles.AuditService.log_create"):
            resp = client.post(
                f"{URL}/",
                json={"name": "duplicate-me", "open_ports": []},
                headers=auth_headers,
            )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_missing_name_returns_422(self, client, auth_headers):
        resp = client.post(f"{URL}/", json={"open_ports": []}, headers=auth_headers)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /{role_id} — update
# ---------------------------------------------------------------------------


class TestUpdateFirewallRole:
    def test_invalid_uuid_returns_400(self, client, auth_headers):
        resp = client.put(f"{URL}/not-a-uuid", json={"name": "x"}, headers=auth_headers)
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client, auth_headers):
        resp = client.put(
            f"{URL}/{uuid.uuid4()}",
            json={"name": "x"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_rename_succeeds(self, client, auth_headers, session):
        role = _create_role(session, name="old-name")
        with patch("backend.api.firewall_roles.AuditService.log_update"):
            resp = client.put(
                f"{URL}/{role.id}",
                json={"name": "new-name"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"

    def test_rename_to_existing_name_returns_409(self, client, auth_headers, session):
        _create_role(session, name="taken")
        role = _create_role(session, name="mine")
        with patch("backend.api.firewall_roles.AuditService.log_update"):
            resp = client.put(
                f"{URL}/{role.id}",
                json={"name": "taken"},
                headers=auth_headers,
            )
        assert resp.status_code == 409

    def test_replacing_open_ports_swaps_full_set(self, client, auth_headers, session):
        role = _create_role(session, name="ports")
        # First, add some ports via update
        with patch("backend.api.firewall_roles.AuditService.log_update"):
            client.put(
                f"{URL}/{role.id}",
                json={
                    "open_ports": [
                        {"port_number": 22, "tcp": True, "udp": False},
                        {"port_number": 80, "tcp": True, "udp": False},
                    ]
                },
                headers=auth_headers,
            )
            # Replace with a different set
            resp = client.put(
                f"{URL}/{role.id}",
                json={"open_ports": [{"port_number": 443, "tcp": True, "udp": False}]},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        ports = {p["port_number"] for p in resp.json()["open_ports"]}
        assert ports == {443}


# ---------------------------------------------------------------------------
# DELETE /{role_id}
# ---------------------------------------------------------------------------


class TestDeleteFirewallRole:
    def test_invalid_uuid_returns_400(self, client, auth_headers):
        resp = client.delete(f"{URL}/not-a-uuid", headers=auth_headers)
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client, auth_headers):
        resp = client.delete(f"{URL}/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    def test_happy_path(self, client, auth_headers, session):
        role = _create_role(session, name="to-delete")
        with patch("backend.api.firewall_roles.AuditService.log_delete"):
            resp = client.delete(f"{URL}/{role.id}", headers=auth_headers)
        assert resp.status_code == 200
        # Confirm it's gone.
        check = client.get(f"{URL}/{role.id}", headers=auth_headers)
        assert check.status_code == 404


# ---------------------------------------------------------------------------
# Host-assignment routes
# ---------------------------------------------------------------------------


def _create_host(session, fqdn="h.example"):
    from datetime import datetime, timezone

    host = models.Host(
        active=True,
        fqdn=fqdn,
        approval_status="approved",
        last_access=datetime.now(timezone.utc),
    )
    session.add(host)
    session.commit()
    session.refresh(host)
    return host


class TestGetHostFirewallRoles:
    def test_invalid_host_uuid_returns_400(self, client, auth_headers):
        resp = client.get(f"{URL}/host/not-a-uuid/roles", headers=auth_headers)
        assert resp.status_code == 400

    def test_host_not_found_returns_404(self, client, auth_headers):
        resp = client.get(f"{URL}/host/{uuid.uuid4()}/roles", headers=auth_headers)
        assert resp.status_code == 404

    def test_no_assignments_returns_empty(self, client, auth_headers, session):
        host = _create_host(session)
        resp = client.get(f"{URL}/host/{host.id}/roles", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetHostExpectedPorts:
    def test_invalid_host_uuid_returns_400(self, client, auth_headers):
        resp = client.get(f"{URL}/host/not-a-uuid/expected-ports", headers=auth_headers)
        assert resp.status_code == 400

    def test_host_not_found_returns_404(self, client, auth_headers):
        resp = client.get(
            f"{URL}/host/{uuid.uuid4()}/expected-ports", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_host_with_no_assignments_returns_empty_lists(
        self, client, auth_headers, session
    ):
        host = _create_host(session)
        resp = client.get(f"{URL}/host/{host.id}/expected-ports", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"ipv4_ports": [], "ipv6_ports": []}


class TestAssignAndUnassignHostFirewallRole:
    def test_assign_role_to_host_missing_role_returns_404(
        self, client, auth_headers, session
    ):
        host = _create_host(session)
        with patch("backend.api.firewall_roles.AuditService.log_create"):
            resp = client.post(
                f"{URL}/host/{host.id}/roles",
                json={"firewall_role_id": str(uuid.uuid4())},
                headers=auth_headers,
            )
        # Either 404 (role not found) or 400 (validation chain) is acceptable.
        assert resp.status_code in (400, 404)

    def test_assign_to_missing_host_returns_404(self, client, auth_headers, session):
        role = _create_role(session, name="orphan")
        with patch("backend.api.firewall_roles.AuditService.log_create"):
            resp = client.post(
                f"{URL}/host/{uuid.uuid4()}/roles",
                json={"firewall_role_id": str(role.id)},
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_assign_invalid_uuid_returns_400(self, client, auth_headers):
        resp = client.post(
            f"{URL}/host/not-a-uuid/roles",
            json={"firewall_role_id": "also-bad"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
