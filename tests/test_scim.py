# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.E — SCIM 2.0 inbound-provisioning endpoints (OSS plumbing).

The SCIM protocol logic lives in the Pro+ ``external_idp_engine``; here we test
the OSS endpoint layer: the bearer-token gate, the 402/404 gates, and that a
SCIM create/patch/delete actually provisions / deactivates the linked ``User``.
The engine is mocked so these tests need neither the compiled ``.so`` nor a real
IdP.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import scim
from backend.persistence.db import Base
from backend.persistence import models

PROVIDER_ID = uuid.uuid4()
TOKEN = "scim-secret-token"


@pytest.fixture
def env():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    SessionLocal = sessionmaker(bind=eng)
    with SessionLocal() as s:
        s.add(
            models.ExternalIdpProvider(
                id=PROVIDER_ID,
                name="acme-scim",
                type="saml",
                enabled=True,
                tenant_id=None,  # server-global → no registry grant in this test
                scim_enabled=True,
                scim_bearer_token_secret_id=f"literal:{TOKEN}",
            )
        )
        s.commit()

    def _fake_get_db():
        yield SessionLocal()

    engine_mock = _engine_mock()
    loader = patch("backend.api.scim.module_loader")
    getdb = patch("backend.api.scim.get_db", _fake_get_db)
    mock_loader = loader.start()
    mock_loader.get_module.return_value = engine_mock
    getdb.start()
    try:
        yield SessionLocal, engine_mock
    finally:
        loader.stop()
        getdb.stop()
        eng.dispose()


def _engine_mock():
    """A mock engine whose SCIM methods behave like the real pure functions."""
    e = MagicMock()
    e.scim_validate_user.side_effect = lambda p: (
        {
            "ok": True,
            "error": None,
            "attrs": {
                "user_name": p["userName"],
                "email": p.get("userName"),
                "external_id": p.get("externalId"),
                "active": bool(p.get("active", True)),
                "display_name": p.get("displayName"),
            },
        }
        if p.get("userName")
        else {"ok": False, "error": "userName is required", "attrs": None}
    )
    e.scim_user_to_resource.side_effect = lambda rec, loc=None: {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": rec["id"],
        "userName": rec["user_name"],
        "active": rec["active"],
    }
    e.scim_list_to_resource.side_effect = lambda res, total=None: {
        "totalResults": total if total is not None else len(res),
        "Resources": list(res),
    }
    e.scim_error.side_effect = lambda status, detail, scim_type=None: {
        "status": str(status),
        "detail": detail,
    }
    e.scim_parse_filter.side_effect = lambda f: (
        {"attribute": "userName", "op": "eq", "value": f.split('"')[1]}
        if f and "userName eq" in f
        else None
    )
    e.scim_apply_patch.side_effect = lambda attrs, payload: {
        "ok": True,
        "error": None,
        "attrs": {
            **attrs,
            "active": (
                payload["Operations"][0]["value"]
                if not isinstance(payload["Operations"][0].get("value"), dict)
                else payload["Operations"][0]["value"].get("active", attrs["active"])
            ),
        },
    }
    return e


def _request(token=TOKEN, query=None, url="https://h/api/scim/v2/p/Users/x"):
    req = MagicMock()
    req.headers = {"authorization": f"Bearer {token}"} if token else {}
    req.query_params = query or {}
    req.url_for = MagicMock(return_value=url)
    return req


@pytest.mark.asyncio
async def test_create_user_provisions(env):
    SessionLocal, _ = env
    payload = {"userName": "jdoe@acme.com", "externalId": "ext-1", "active": True}
    resp = await scim.scim_create_user(str(PROVIDER_ID), _request(), payload)
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 201
    with SessionLocal() as s:
        u = s.query(models.User).filter_by(userid="jdoe@acme.com").first()
        assert u is not None
        assert u.external_idp_provider_id == PROVIDER_ID
        assert u.external_subject == "ext-1"
        assert u.active is True


@pytest.mark.asyncio
async def test_create_duplicate_returns_409(env):
    SessionLocal, _ = env
    with SessionLocal() as s:
        u = models.User(userid="dup@acme.com", active=True, is_admin=False)
        u.external_idp_provider_id = PROVIDER_ID
        u.external_subject = "ext-9"
        s.add(u)
        s.commit()
    resp = await scim.scim_create_user(
        str(PROVIDER_ID), _request(), {"userName": "dup@acme.com"}
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bad_token_401(env):
    with pytest.raises(HTTPException) as exc:
        await scim.scim_create_user(
            str(PROVIDER_ID), _request(token="wrong"), {"userName": "x@acme.com"}
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_401(env):
    with pytest.raises(HTTPException) as exc:
        await scim.scim_list_users(str(PROVIDER_ID), _request(token=None))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_402_without_engine(env):
    with patch("backend.api.scim.module_loader") as loader:
        loader.get_module.return_value = None
        with pytest.raises(HTTPException) as exc:
            await scim.scim_list_users(str(PROVIDER_ID), _request())
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_scim_disabled_provider_404(env):
    SessionLocal, _ = env
    with SessionLocal() as s:
        s.query(models.ExternalIdpProvider).filter_by(id=PROVIDER_ID).update(
            {"scim_enabled": False}
        )
        s.commit()
    with pytest.raises(HTTPException) as exc:
        await scim.scim_list_users(str(PROVIDER_ID), _request())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_filter_by_username(env):
    SessionLocal, _ = env
    with SessionLocal() as s:
        u = models.User(userid="find@acme.com", active=True, is_admin=False)
        u.external_idp_provider_id = PROVIDER_ID
        s.add(u)
        s.commit()
    req = _request(query={"filter": 'userName eq "find@acme.com"'})
    resp = await scim.scim_list_users(str(PROVIDER_ID), req)
    import json

    body = json.loads(resp.body.decode())
    assert body["totalResults"] == 1
    assert body["Resources"][0]["userName"] == "find@acme.com"


@pytest.mark.asyncio
async def test_patch_deactivates_user(env):
    SessionLocal, _ = env
    with SessionLocal() as s:
        u = models.User(userid="off@acme.com", active=True, is_admin=False)
        u.external_idp_provider_id = PROVIDER_ID
        s.add(u)
        s.commit()
        uid = u.id
    payload = {"Operations": [{"op": "replace", "path": "active", "value": False}]}
    await scim.scim_patch_user(str(PROVIDER_ID), str(uid), _request(), payload)
    with SessionLocal() as s:
        assert s.query(models.User).filter_by(id=uid).first().active is False


@pytest.mark.asyncio
async def test_delete_deactivates_user(env):
    SessionLocal, _ = env
    with SessionLocal() as s:
        u = models.User(userid="gone@acme.com", active=True, is_admin=False)
        u.external_idp_provider_id = PROVIDER_ID
        s.add(u)
        s.commit()
        uid = u.id
    resp = await scim.scim_delete_user(str(PROVIDER_ID), str(uid), _request())
    assert resp.status_code == 204
    with SessionLocal() as s:
        assert s.query(models.User).filter_by(id=uid).first().active is False
