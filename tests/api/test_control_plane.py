# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the multi-tenancy control-plane API.

The entire control-plane surface moved into the licensed ``multitenancy_engine``
(Pro+ relocation, moat slice 8); the OSS build ships only a 501 stub.  These
tests therefore come in two flavours:

* **Stub contract** (always runs) — mounts the OSS ``control_plane.router`` and
  asserts the unlicensed 501 + the bearer-token gate.
* **Behavioral** (skips without the compiled ``.so``) — builds the *engine's*
  router via the shared ``real_engine`` fixture and exercises every endpoint
  end-to-end, with the registry-session dependency overridden to the in-memory
  test database.  Relocated services (provisioning, orchestration, enrollment)
  run through the OSS shims, which delegate back into the engine.
"""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import control_plane
from backend.auth.auth_handler import sign_jwt
from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE
from backend.persistence.partitions import get_registry_db


def _engine_client(db_session, engine_mod):
    """Mount the *engine's* control-plane router on a fresh app, registry
    session overridden to the test DB and a default admin bearer token."""
    app = FastAPI()
    # Mirror production: proplus_routes mounts the self-prefixed ("/control-plane")
    # router at the canonical "/api/v1" surface (Phase 13.2.1).
    app.include_router(engine_mod.get_multitenancy_engine_router(), prefix="/api/v1")

    def _override_registry_db():
        yield db_session

    app.dependency_overrides[get_registry_db] = _override_registry_db
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {sign_jwt('admin')}"})
    return client


# ---------------------------------------------------------------------------
# Stub contract — always runs (no engine)
# ---------------------------------------------------------------------------


def _stub_client():
    app = FastAPI()
    app.include_router(control_plane.router, prefix="/api/v1")
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {sign_jwt('admin')}"})
    return client


def test_stub_requires_authentication():
    client = _stub_client()
    resp = client.get("/api/v1/control-plane/status", headers={"Authorization": ""})
    assert resp.status_code in (401, 403)


def test_stub_returns_501_when_engine_absent():
    client = _stub_client()
    # Any route, any method → unlicensed.
    for method, path in [
        ("get", "/api/v1/control-plane/status"),
        ("get", "/api/v1/control-plane/tenants"),
        ("post", "/api/v1/control-plane/tenants"),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 501
        assert "licensed" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Behavioral — against the engine's real router (skips without the .so)
# ---------------------------------------------------------------------------


def test_requires_authentication(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    resp = client.get("/api/v1/control-plane/status", headers={"Authorization": ""})
    assert resp.status_code in (401, 403)


def test_status_reports_zero_tenants_initially(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    resp = client.get("/api/v1/control-plane/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_count"] == 0
    assert "multitenancy_enabled" in body


def test_list_and_count_tenants(real_engine, db_session):
    db_session.add(
        RegistryTenant(name="Acme", slug="acme", status=TENANT_STATUS_ACTIVE)
    )
    db_session.add(
        RegistryTenant(name="Globex", slug="globex", status=TENANT_STATUS_ACTIVE)
    )
    db_session.commit()

    client = _engine_client(db_session, real_engine)
    resp = client.get("/api/v1/control-plane/tenants")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    slugs = {t["slug"] for t in body["tenants"]}
    assert slugs == {"acme", "globex"}


def test_list_tenants_filtered_by_status(real_engine, db_session):
    db_session.add(RegistryTenant(name="Active Co", slug="active", status="active"))
    db_session.add(
        RegistryTenant(name="Suspended Co", slug="suspended", status="suspended")
    )
    db_session.commit()

    client = _engine_client(db_session, real_engine)
    resp = client.get("/api/v1/control-plane/tenants", params={"status": "suspended"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["tenants"][0]["slug"] == "suspended"


def test_create_tenant_and_duplicate_slug(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    resp = client.post(
        "/api/v1/control-plane/tenants", json={"name": "Acme", "slug": "acme"}
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "acme"
    dup = client.post(
        "/api/v1/control-plane/tenants", json={"name": "Acme 2", "slug": "acme"}
    )
    assert dup.status_code == 409


def test_create_user_and_duplicate_email(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    resp = client.post(
        "/api/v1/control-plane/users", json={"email": "person@example.com"}
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "person@example.com"
    dup = client.post(
        "/api/v1/control-plane/users", json={"email": "person@example.com"}
    )
    assert dup.status_code == 409


def test_list_users_and_filter_by_email(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    client.post("/api/v1/control-plane/users", json={"email": "a@example.com"})
    client.post("/api/v1/control-plane/users", json={"email": "b@example.com"})

    all_users = client.get("/api/v1/control-plane/users")
    assert all_users.status_code == 200
    assert {u["email"] for u in all_users.json()} == {"a@example.com", "b@example.com"}

    filtered = client.get(
        "/api/v1/control-plane/users", params={"email": "A@EXAMPLE.COM"}
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["email"] == "a@example.com"


def test_status_reports_self_service_flag(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    with patch(
        "backend.config.config.is_self_service_provisioning_enabled",
        return_value=False,
    ):
        body = client.get("/api/v1/control-plane/status").json()
    assert body["self_service_provisioning"] is False
    assert body["provisioner_configured"] is False


def test_auto_provision_refused_when_flag_disabled(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    _, tenant_id = _make_user_and_tenant(client)
    with patch(
        "backend.config.config.is_self_service_provisioning_enabled",
        return_value=False,
    ):
        resp = client.post(
            f"/api/v1/control-plane/tenants/{tenant_id}/auto-provision", json={}
        )
    assert resp.status_code == 403


def test_auto_provision_happy_path(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    _, tenant_id = _make_user_and_tenant(client)
    summary = {
        "tenant_id": tenant_id,
        "dbname": "tenant_acme",
        "openbao_role": "acme-role",
        "revision": "rev1",
        "status": "provisioned",
    }
    with patch(
        "backend.config.config.is_self_service_provisioning_enabled",
        return_value=True,
    ), patch.object(real_engine, "_require_provision_admin"), patch.object(
        real_engine, "_audit_provision"
    ), patch(
        "backend.services.tenant_orchestration.auto_provision_tenant",
        return_value=summary,
    ) as orch:
        resp = client.post(
            f"/api/v1/control-plane/tenants/{tenant_id}/auto-provision",
            json={"host": "db", "tier": "silo"},
        )
    assert resp.status_code == 200
    assert resp.json()["dbname"] == "tenant_acme"
    orch.assert_called_once()


def test_auto_provision_surfaces_error_detail(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    _, tenant_id = _make_user_and_tenant(client)
    with patch(
        "backend.config.config.is_self_service_provisioning_enabled",
        return_value=True,
    ), patch.object(real_engine, "_require_provision_admin"), patch.object(
        real_engine, "_audit_provision"
    ), patch(
        "backend.services.tenant_orchestration.auto_provision_tenant",
        side_effect=RuntimeError("boom-detail"),
    ):
        resp = client.post(
            f"/api/v1/control-plane/tenants/{tenant_id}/auto-provision", json={}
        )
    assert resp.status_code == 502
    assert "boom-detail" in resp.json()["detail"]


def test_delete_tenant_rejects_wrong_confirmation(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    _, tenant_id = _make_user_and_tenant(client)
    with patch.object(real_engine, "_require_provision_admin"):
        resp = client.request(
            "DELETE",
            f"/api/v1/control-plane/tenants/{tenant_id}",
            json={"confirm": "wrong-slug", "drop_database": False},
        )
    assert resp.status_code == 400


def test_delete_tenant_happy_path(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    _, tenant_id = _make_user_and_tenant(client)  # slug "acme"
    summary = {
        "openbao_removed": True,
        "database_dropped": True,
        "registry_removed": True,
        "errors": [],
    }
    with patch.object(real_engine, "_require_provision_admin"), patch.object(
        real_engine, "_audit_delete"
    ), patch(
        "backend.services.tenant_orchestration.deprovision_tenant",
        return_value=summary,
    ) as dep:
        resp = client.request(
            "DELETE",
            f"/api/v1/control-plane/tenants/{tenant_id}",
            json={"confirm": "acme", "drop_database": True},
        )
    assert resp.status_code == 200
    assert resp.json()["registry_removed"] is True
    _, kwargs = dep.call_args
    assert kwargs["slug"] == "acme"
    assert kwargs["drop_database"] is True


def test_delete_tenant_unknown_returns_404(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    with patch.object(real_engine, "_require_provision_admin"):
        resp = client.request(
            "DELETE",
            "/api/v1/control-plane/tenants/00000000-0000-0000-0000-000000000000",
            json={"confirm": "x", "drop_database": False},
        )
    assert resp.status_code == 404


def test_migration_status_endpoint(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    with patch(
        "backend.services.migration_status.pending_tenant_migrations",
        return_value={
            "tenants_pending": 1,
            "tenant_slugs": ["acme"],
            "tenant_head": "rX",
        },
    ):
        resp = client.get("/api/v1/control-plane/migration-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenants_pending"] == 1
    assert body["tenant_slugs"] == ["acme"]


def test_enrollment_token_create_list_revoke(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    _, tenant_id = _make_user_and_tenant(client)
    with patch.object(real_engine, "_require_provision_admin"):
        created = client.post(
            f"/api/v1/control-plane/tenants/{tenant_id}/enrollment-tokens",
            json={"label": "laptops", "max_uses": 5},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["token"].startswith("sme_")
        assert body["summary"]["label"] == "laptops"
        token_id = body["summary"]["id"]

        listed = client.get(
            f"/api/v1/control-plane/tenants/{tenant_id}/enrollment-tokens"
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert "token" not in listed.json()[0]

        revoked = client.delete(
            f"/api/v1/control-plane/tenants/{tenant_id}/enrollment-tokens/{token_id}"
        )
        assert revoked.status_code == 204
        assert (
            client.get(
                f"/api/v1/control-plane/tenants/{tenant_id}/enrollment-tokens"
            ).json()[0]["revoked"]
            is True
        )


def test_enrollment_token_create_unknown_tenant_404(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    with patch.object(real_engine, "_require_provision_admin"):
        resp = client.post(
            "/api/v1/control-plane/tenants/00000000-0000-0000-0000-000000000000/"
            "enrollment-tokens",
            json={},
        )
    assert resp.status_code == 404


def _make_user_and_tenant(client):
    user_id = client.post(
        "/api/v1/control-plane/users", json={"email": "u@example.com"}
    ).json()["id"]
    tenant_id = client.post(
        "/api/v1/control-plane/tenants", json={"name": "Acme", "slug": "acme"}
    ).json()["id"]
    return user_id, tenant_id


def test_grant_crud_roundtrip(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    user_id, tenant_id = _make_user_and_tenant(client)

    created = client.post(
        "/api/v1/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id, "role": "admin"},
    )
    assert created.status_code == 201
    grant_id = created.json()["id"]

    listed = client.get("/api/v1/control-plane/grants", params={"user_id": user_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    dup = client.post(
        "/api/v1/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id},
    )
    assert dup.status_code == 409

    deleted = client.delete(f"/api/v1/control-plane/grants/{grant_id}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/control-plane/grants").json() == []


def test_grant_blocked_by_email_domain_allowlist(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    user_id, tenant_id = _make_user_and_tenant(client)

    add = client.post(
        f"/api/v1/control-plane/tenants/{tenant_id}/email-domains",
        json={"domain": "Allowed.COM"},
    )
    assert add.status_code == 201
    assert add.json()["domain"] == "allowed.com"  # normalized

    blocked = client.post(
        "/api/v1/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id},
    )
    assert blocked.status_code == 403


def test_grant_allowed_when_domain_allowlisted(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    user_id, tenant_id = _make_user_and_tenant(client)
    client.post(
        f"/api/v1/control-plane/tenants/{tenant_id}/email-domains",
        json={"domain": "example.com"},
    )
    ok = client.post(
        "/api/v1/control-plane/grants",
        json={"user_id": user_id, "tenant_id": tenant_id},
    )
    assert ok.status_code == 201


def test_email_domain_list_and_delete(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    _, tenant_id = _make_user_and_tenant(client)
    add = client.post(
        f"/api/v1/control-plane/tenants/{tenant_id}/email-domains",
        json={"domain": "example.com"},
    )
    domain_id = add.json()["id"]
    listed = client.get(f"/api/v1/control-plane/tenants/{tenant_id}/email-domains")
    assert [d["domain"] for d in listed.json()] == ["example.com"]
    deleted = client.delete(
        f"/api/v1/control-plane/tenants/{tenant_id}/email-domains/{domain_id}"
    )
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/v1/control-plane/tenants/{tenant_id}/email-domains").json()
        == []
    )


def _make_tenant(client, slug="acme"):
    return client.post(
        "/api/v1/control-plane/tenants", json={"name": slug.title(), "slug": slug}
    ).json()["id"]


def test_placement_upsert_and_get(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    tenant_id = _make_tenant(client)
    resp = client.put(
        f"/api/v1/control-plane/tenants/{tenant_id}/placement",
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
    assert "password" not in body and "secret" not in body

    got = client.get(f"/api/v1/control-plane/tenants/{tenant_id}/placement")
    assert got.status_code == 200
    assert got.json()["host"] == "db.internal"


def test_placement_upsert_updates_existing(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    tenant_id = _make_tenant(client)
    client.put(
        f"/api/v1/control-plane/tenants/{tenant_id}/placement",
        json={"dbname": "first", "tier": "silo"},
    )
    client.put(
        f"/api/v1/control-plane/tenants/{tenant_id}/placement",
        json={"dbname": "second", "tier": "silo"},
    )
    assert (
        client.get(f"/api/v1/control-plane/tenants/{tenant_id}/placement").json()[
            "dbname"
        ]
        == "second"
    )


def test_placement_unknown_tier_rejected(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    tenant_id = _make_tenant(client)
    resp = client.put(
        f"/api/v1/control-plane/tenants/{tenant_id}/placement",
        json={"tier": "bogus"},
    )
    assert resp.status_code == 422


def test_provision_requires_placement(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    tenant_id = _make_tenant(client)
    resp = client.post(f"/api/v1/control-plane/tenants/{tenant_id}/provision")
    assert resp.status_code == 400


def test_provision_runs_and_returns_revision(real_engine, db_session):
    client = _engine_client(db_session, real_engine)
    tenant_id = _make_tenant(client)
    client.put(
        f"/api/v1/control-plane/tenants/{tenant_id}/placement",
        json={"dbname": "acme", "tier": "silo", "openbao_role": "r"},
    )
    with patch(
        "backend.services.tenant_provisioning.provision_tenant_database",
        return_value="m10fedseclease",
    ):
        resp = client.post(f"/api/v1/control-plane/tenants/{tenant_id}/provision")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "provisioned"
    assert body["revision"] == "m10fedseclease"
