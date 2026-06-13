"""
Tests for the control-plane API skeleton — Phase 13.1.A.

The control-plane router is mounted on the real app only when
``multitenancy.enabled`` is true, so these tests exercise the router in
isolation on a fresh FastAPI app with the registry-session dependency
overridden to the in-memory test database.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import control_plane
from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE
from backend.persistence.partitions import get_registry_db


def _client(db_session):
    app = FastAPI()
    app.include_router(control_plane.router)

    def _override_registry_db():
        yield db_session

    app.dependency_overrides[get_registry_db] = _override_registry_db
    return TestClient(app)


def test_status_reports_zero_tenants_initially(db_session):
    client = _client(db_session)
    resp = client.get("/api/control-plane/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_count"] == 0
    assert "multitenancy_enabled" in body


def test_list_and_count_tenants(db_session):
    db_session.add(
        RegistryTenant(name="Acme", slug="acme", status=TENANT_STATUS_ACTIVE)
    )
    db_session.add(
        RegistryTenant(name="Globex", slug="globex", status=TENANT_STATUS_ACTIVE)
    )
    db_session.commit()

    client = _client(db_session)
    resp = client.get("/api/control-plane/tenants")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    slugs = {t["slug"] for t in body["tenants"]}
    assert slugs == {"acme", "globex"}


def test_list_tenants_filtered_by_status(db_session):
    db_session.add(RegistryTenant(name="Active Co", slug="active", status="active"))
    db_session.add(
        RegistryTenant(name="Suspended Co", slug="suspended", status="suspended")
    )
    db_session.commit()

    client = _client(db_session)
    resp = client.get("/api/control-plane/tenants", params={"status": "suspended"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["tenants"][0]["slug"] == "suspended"


# ---------------------------------------------------------------------
# CRUD — Phase 13.1.B
# ---------------------------------------------------------------------


def test_create_tenant_and_duplicate_slug(db_session):
    client = _client(db_session)
    resp = client.post(
        "/api/control-plane/tenants", json={"name": "Acme", "slug": "acme"}
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "acme"
    # Duplicate slug → 409.
    dup = client.post(
        "/api/control-plane/tenants", json={"name": "Acme 2", "slug": "acme"}
    )
    assert dup.status_code == 409


def test_create_user_and_duplicate_email(db_session):
    client = _client(db_session)
    resp = client.post("/api/control-plane/users", json={"email": "person@example.com"})
    assert resp.status_code == 201
    assert resp.json()["email"] == "person@example.com"
    dup = client.post("/api/control-plane/users", json={"email": "person@example.com"})
    assert dup.status_code == 409


def _make_user_and_tenant(client):
    user_id = client.post(
        "/api/control-plane/users", json={"email": "u@example.com"}
    ).json()["id"]
    tenant_id = client.post(
        "/api/control-plane/tenants", json={"name": "Acme", "slug": "acme"}
    ).json()["id"]
    return user_id, tenant_id


def test_grant_crud_roundtrip(db_session):
    client = _client(db_session)
    user_id, tenant_id = _make_user_and_tenant(client)

    created = client.post(
        "/api/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id, "role": "admin"},
    )
    assert created.status_code == 201
    grant_id = created.json()["id"]

    listed = client.get("/api/control-plane/grants", params={"user_id": user_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Duplicate grant → 409.
    dup = client.post(
        "/api/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id},
    )
    assert dup.status_code == 409

    deleted = client.delete(f"/api/control-plane/grants/{grant_id}")
    assert deleted.status_code == 204
    assert client.get("/api/control-plane/grants").json() == []


def test_grant_blocked_by_email_domain_allowlist(db_session):
    client = _client(db_session)
    user_id, tenant_id = _make_user_and_tenant(client)

    # Allowlist a different domain than the user's.
    add = client.post(
        f"/api/control-plane/tenants/{tenant_id}/email-domains",
        json={"domain": "Allowed.COM"},
    )
    assert add.status_code == 201
    assert add.json()["domain"] == "allowed.com"  # normalized

    blocked = client.post(
        "/api/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id},
    )
    assert blocked.status_code == 403


def test_grant_allowed_when_domain_allowlisted(db_session):
    client = _client(db_session)
    user_id, tenant_id = _make_user_and_tenant(client)
    client.post(
        f"/api/control-plane/tenants/{tenant_id}/email-domains",
        json={"domain": "example.com"},
    )
    ok = client.post(
        "/api/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id},
    )
    assert ok.status_code == 201


def test_email_domain_list_and_delete(db_session):
    client = _client(db_session)
    _, tenant_id = _make_user_and_tenant(client)
    add = client.post(
        f"/api/control-plane/tenants/{tenant_id}/email-domains",
        json={"domain": "example.com"},
    )
    domain_id = add.json()["id"]
    listed = client.get(f"/api/control-plane/tenants/{tenant_id}/email-domains")
    assert [d["domain"] for d in listed.json()] == ["example.com"]
    deleted = client.delete(
        f"/api/control-plane/tenants/{tenant_id}/email-domains/{domain_id}"
    )
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/control-plane/tenants/{tenant_id}/email-domains").json() == []
    )
