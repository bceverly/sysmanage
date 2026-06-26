"""
Tests for tenant routing & account switching — Phase 13.1.B.

Covers ``get_current_tenant`` (the membership-verifying dependency) and the
data-plane ``/api/auth/accounts`` + ``/api/auth/switch-account`` endpoints.
All exercise the in-memory test DB, which (in test mode) is also what the
registry partition resolves to.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api import auth
from backend.auth.auth_bearer import get_current_tenant
from backend.auth.auth_handler import sign_jwt
from backend.persistence.models import (
    RegistryTenant,
    RegistryUser,
    RegistryUserTenantGrant,
)


def _seed_user_with_grant(db_session, slug="acme"):
    user = RegistryUser(email=f"u@{slug}.com")
    tenant = RegistryTenant(name=slug.title(), slug=slug, status="active")
    db_session.add_all([user, tenant])
    db_session.commit()
    db_session.add(
        RegistryUserTenantGrant(user_id=user.id, tenant_id=tenant.id, role="admin")
    )
    db_session.commit()
    return user, tenant


# ----- get_current_tenant -------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_tenant_none_when_disabled(db_session, monkeypatch):
    """Disabled (default) → always None, no registry lookup."""
    monkeypatch.setattr(
        "backend.auth.auth_bearer.config.is_multitenancy_enabled", lambda: False
    )
    token = sign_jwt("anyone", tenant_id="whatever")
    assert await get_current_tenant(token) is None


@pytest.mark.asyncio
async def test_get_current_tenant_verifies_grant(db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.auth.auth_bearer.config.is_multitenancy_enabled", lambda: True
    )
    user, tenant = _seed_user_with_grant(db_session)
    token = sign_jwt(str(user.id), tenant_id=str(tenant.id))
    assert await get_current_tenant(token) == str(tenant.id)


@pytest.mark.asyncio
async def test_get_current_tenant_rejects_without_grant(db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.auth.auth_bearer.config.is_multitenancy_enabled", lambda: True
    )
    user, _ = _seed_user_with_grant(db_session)
    # A tenant the user has NO grant to.
    other = RegistryTenant(name="Other", slug="other", status="active")
    db_session.add(other)
    db_session.commit()
    token = sign_jwt(str(user.id), tenant_id=str(other.id))
    with pytest.raises(HTTPException) as exc:
        await get_current_tenant(token)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_tenant_none_when_claim_absent(db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.auth.auth_bearer.config.is_multitenancy_enabled", lambda: True
    )
    token = sign_jwt("u1")  # no tenant claim
    assert await get_current_tenant(token) is None


# ----- /api/auth/switch-account + /api/auth/accounts ----------------------


def _auth_client():
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    return TestClient(app)


def test_switch_account_disabled_returns_400(db_session, monkeypatch):
    monkeypatch.setattr(
        "backend.api.auth.config.is_multitenancy_enabled", lambda: False
    )
    user, tenant = _seed_user_with_grant(db_session)
    client = _auth_client()
    token = sign_jwt(str(user.id))
    resp = client.post(
        "/api/auth/switch-account",
        json={"tenant_id": str(tenant.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_switch_account_success_remints_with_tenant(db_session, monkeypatch):
    monkeypatch.setattr("backend.api.auth.config.is_multitenancy_enabled", lambda: True)
    user, tenant = _seed_user_with_grant(db_session)
    client = _auth_client()
    token = sign_jwt(str(user.id))
    resp = client.post(
        "/api/auth/switch-account",
        json={"tenant_id": str(tenant.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    new_token = resp.json()["Authorization"]

    import jwt as _jwt

    claims = _jwt.decode(new_token, options={"verify_signature": False})
    assert claims["tenant_id"] == str(tenant.id)
    assert claims["user_id"] == str(user.id)


def test_switch_account_without_grant_403(db_session, monkeypatch):
    monkeypatch.setattr("backend.api.auth.config.is_multitenancy_enabled", lambda: True)
    user, _ = _seed_user_with_grant(db_session)
    other = RegistryTenant(name="Other", slug="other", status="active")
    db_session.add(other)
    db_session.commit()
    client = _auth_client()
    token = sign_jwt(str(user.id))
    resp = client.post(
        "/api/auth/switch-account",
        json={"tenant_id": str(other.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_list_accounts_returns_grants(db_session, monkeypatch):
    monkeypatch.setattr("backend.api.auth.config.is_multitenancy_enabled", lambda: True)
    user, tenant = _seed_user_with_grant(db_session)
    client = _auth_client()
    token = sign_jwt(str(user.id))
    resp = client.get(
        "/api/auth/accounts", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["accounts"][0]["slug"] == tenant.slug
