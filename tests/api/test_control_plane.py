"""
Tests for the control-plane API skeleton — Phase 13.1.A.

The control-plane router is mounted on the real app only when
``multitenancy.enabled`` is true, so these tests exercise the router in
isolation on a fresh FastAPI app with the registry-session dependency
overridden to the in-memory test database.
"""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import control_plane
from backend.auth.auth_handler import sign_jwt
from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE
from backend.persistence.partitions import get_registry_db


def _client(db_session):
    app = FastAPI()
    app.include_router(control_plane.router)

    def _override_registry_db():
        yield db_session

    app.dependency_overrides[get_registry_db] = _override_registry_db
    client = TestClient(app)
    # The control-plane router requires a valid bearer token; attach one by
    # default so every request in these tests is authenticated.
    client.headers.update({"Authorization": f"Bearer {sign_jwt('admin')}"})
    return client


def test_requires_authentication(db_session):
    client = _client(db_session)
    # Strip the default bearer token → unauthenticated request is rejected.
    resp = client.get("/api/control-plane/status", headers={"Authorization": ""})
    assert resp.status_code in (401, 403)


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


def test_list_users_and_filter_by_email(db_session):
    client = _client(db_session)
    client.post("/api/control-plane/users", json={"email": "a@example.com"})
    client.post("/api/control-plane/users", json={"email": "b@example.com"})

    all_users = client.get("/api/control-plane/users")
    assert all_users.status_code == 200
    assert {u["email"] for u in all_users.json()} == {"a@example.com", "b@example.com"}

    # Exact (case-insensitive) email filter backs the add-member lookup.
    filtered = client.get("/api/control-plane/users", params={"email": "A@EXAMPLE.COM"})
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["email"] == "a@example.com"


def test_status_reports_self_service_flag(db_session):
    client = _client(db_session)
    with patch.object(
        control_plane.config_module,
        "is_self_service_provisioning_enabled",
        return_value=False,
    ):
        body = client.get("/api/control-plane/status").json()
    assert body["self_service_provisioning"] is False
    # When off, the provisioner isn't probed.
    assert body["provisioner_configured"] is False


def test_auto_provision_refused_when_flag_disabled(db_session):
    client = _client(db_session)
    _, tenant_id = _make_user_and_tenant(client)
    with patch.object(
        control_plane.config_module,
        "is_self_service_provisioning_enabled",
        return_value=False,
    ):
        resp = client.post(
            f"/api/control-plane/tenants/{tenant_id}/auto-provision", json={}
        )
    assert resp.status_code == 403


def test_auto_provision_happy_path(db_session):
    client = _client(db_session)
    _, tenant_id = _make_user_and_tenant(client)
    summary = {
        "tenant_id": tenant_id,
        "dbname": "tenant_acme",
        "openbao_role": "acme-role",
        "revision": "rev1",
        "status": "provisioned",
    }
    with patch.object(
        control_plane.config_module,
        "is_self_service_provisioning_enabled",
        return_value=True,
    ), patch.object(control_plane, "_require_provision_admin"), patch.object(
        control_plane, "_audit_provision"
    ), patch(
        "backend.services.tenant_orchestration.auto_provision_tenant",
        return_value=summary,
    ) as orch:
        resp = client.post(
            f"/api/control-plane/tenants/{tenant_id}/auto-provision",
            json={"host": "db", "tier": "silo"},
        )
    assert resp.status_code == 200
    assert resp.json()["dbname"] == "tenant_acme"
    orch.assert_called_once()


def test_auto_provision_surfaces_error_detail(db_session):
    client = _client(db_session)
    _, tenant_id = _make_user_and_tenant(client)
    with patch.object(
        control_plane.config_module,
        "is_self_service_provisioning_enabled",
        return_value=True,
    ), patch.object(control_plane, "_require_provision_admin"), patch.object(
        control_plane, "_audit_provision"
    ), patch(
        "backend.services.tenant_orchestration.auto_provision_tenant",
        side_effect=RuntimeError("boom-detail"),
    ):
        resp = client.post(
            f"/api/control-plane/tenants/{tenant_id}/auto-provision", json={}
        )
    assert resp.status_code == 502
    assert "boom-detail" in resp.json()["detail"]


def test_delete_tenant_rejects_wrong_confirmation(db_session):
    client = _client(db_session)
    _, tenant_id = _make_user_and_tenant(client)
    with patch.object(control_plane, "_require_provision_admin"):
        resp = client.request(
            "DELETE",
            f"/api/control-plane/tenants/{tenant_id}",
            json={"confirm": "wrong-slug", "drop_database": False},
        )
    assert resp.status_code == 400


def test_delete_tenant_happy_path(db_session):
    client = _client(db_session)
    _, tenant_id = _make_user_and_tenant(client)  # slug "acme"
    summary = {
        "openbao_removed": True,
        "database_dropped": True,
        "registry_removed": True,
        "errors": [],
    }
    with patch.object(control_plane, "_require_provision_admin"), patch.object(
        control_plane, "_audit_delete"
    ), patch(
        "backend.services.tenant_orchestration.deprovision_tenant",
        return_value=summary,
    ) as dep:
        resp = client.request(
            "DELETE",
            f"/api/control-plane/tenants/{tenant_id}",
            json={"confirm": "acme", "drop_database": True},
        )
    assert resp.status_code == 200
    assert resp.json()["registry_removed"] is True
    # slug + drop_database flag are passed through to the orchestrator.
    _, kwargs = dep.call_args
    assert kwargs["slug"] == "acme"
    assert kwargs["drop_database"] is True


def test_delete_tenant_unknown_returns_404(db_session):
    client = _client(db_session)
    with patch.object(control_plane, "_require_provision_admin"):
        resp = client.request(
            "DELETE",
            "/api/control-plane/tenants/00000000-0000-0000-0000-000000000000",
            json={"confirm": "x", "drop_database": False},
        )
    assert resp.status_code == 404


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


# ---------------------------------------------------------------------
# Placement + provisioning — Phase 13.1.C
# ---------------------------------------------------------------------


def _make_tenant(client, slug="acme"):
    return client.post(
        "/api/control-plane/tenants", json={"name": slug.title(), "slug": slug}
    ).json()["id"]


def test_placement_upsert_and_get(db_session):
    client = _client(db_session)
    tenant_id = _make_tenant(client)
    resp = client.put(
        f"/api/control-plane/tenants/{tenant_id}/placement",
        json={
            "host": "db.internal",
            "port": 5432,
            "dbname": "sysmanage_acme",
            "region": "us-east-1",
            "tier": "silo",
            "openbao_role": "tenant-acme-db",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dbname"] == "sysmanage_acme"
    assert body["openbao_role"] == "tenant-acme-db"
    # No credential field is ever exposed.
    assert "password" not in body and "secret" not in body

    got = client.get(f"/api/control-plane/tenants/{tenant_id}/placement")
    assert got.status_code == 200
    assert got.json()["host"] == "db.internal"


def test_placement_upsert_updates_existing(db_session):
    client = _client(db_session)
    tenant_id = _make_tenant(client)
    client.put(
        f"/api/control-plane/tenants/{tenant_id}/placement",
        json={"dbname": "first", "tier": "silo"},
    )
    client.put(
        f"/api/control-plane/tenants/{tenant_id}/placement",
        json={"dbname": "second", "tier": "silo"},
    )
    assert (
        client.get(f"/api/control-plane/tenants/{tenant_id}/placement").json()["dbname"]
        == "second"
    )


def test_placement_unknown_tier_rejected(db_session):
    client = _client(db_session)
    tenant_id = _make_tenant(client)
    resp = client.put(
        f"/api/control-plane/tenants/{tenant_id}/placement",
        json={"tier": "bogus"},
    )
    assert resp.status_code == 422


def test_provision_requires_placement(db_session):
    client = _client(db_session)
    tenant_id = _make_tenant(client)
    resp = client.post(f"/api/control-plane/tenants/{tenant_id}/provision")
    assert resp.status_code == 400


def test_provision_runs_and_returns_revision(db_session):
    from unittest.mock import patch

    client = _client(db_session)
    tenant_id = _make_tenant(client)
    client.put(
        f"/api/control-plane/tenants/{tenant_id}/placement",
        json={"dbname": "acme", "tier": "silo", "openbao_role": "r"},
    )
    with patch(
        "backend.services.tenant_provisioning.provision_tenant_database",
        return_value="m10fedseclease",
    ):
        resp = client.post(f"/api/control-plane/tenants/{tenant_id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "provisioned"
    assert body["revision"] == "m10fedseclease"
