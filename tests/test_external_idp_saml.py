# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.E — SAML 2.0 external-IdP endpoints (OSS plumbing).

The cryptographic verification lives in the Pro+ ``external_idp_engine``; here we
test the OSS endpoint layer that drives it: provider-type gating, the SP-metadata
passthrough, the SP-initiated redirect + RelayState bookkeeping, and the ACS that
turns a verified assertion into a session JWT.  The engine is mocked so these
tests are deterministic and need no real IdP.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import external_idp
from backend.persistence.db import Base
from backend.persistence import models

PROVIDER_ID = uuid.uuid4()


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    with sessionmaker(bind=eng)() as session:
        session.add(
            models.ExternalIdpProvider(
                id=PROVIDER_ID,
                name="acme-saml",
                type="saml",
                enabled=True,
                saml_idp_entity_id="https://idp.acme.com/meta",
                saml_idp_sso_url="https://idp.acme.com/sso",
                saml_idp_x509_cert="FAKECERT==",
                saml_sp_entity_id="https://sm.example.com/sp",
                saml_sp_acs_url=f"https://sm.example.com/api/auth/saml/{PROVIDER_ID}/acs",
            )
        )
        session.commit()
        yield session
    eng.dispose()


def _mock_engine():
    engine = MagicMock()
    engine.get_saml_sp_metadata.return_value = {
        "metadata": "<md:EntityDescriptor/>",
        "error": None,
    }
    engine.build_saml_authn_request.return_value = {
        "url": "https://idp.acme.com/sso?SAMLRequest=abc",
        "request_id": "_req123",
        "error": None,
    }
    engine.process_saml_response.return_value = {
        "success": True,
        "subject": "saml-subject-1",
        "groups": ["admins"],
        "email": "user@acme.com",
        "error": None,
    }
    engine.map_external_groups_to_roles.return_value = []
    return engine


def _patch_engine(engine):
    loader = patch("backend.api.external_idp.module_loader")
    mock_loader = loader.start()
    mock_loader.get_module.return_value = engine
    return loader


@pytest.mark.asyncio
async def test_saml_metadata_returns_xml(db):
    engine = _mock_engine()
    p = _patch_engine(engine)
    try:
        resp = await external_idp.saml_metadata(str(PROVIDER_ID), db)
    finally:
        p.stop()
    assert isinstance(resp, Response)
    assert resp.media_type == "application/samlmetadata+xml"
    assert b"EntityDescriptor" in resp.body


@pytest.mark.asyncio
async def test_saml_start_redirects_and_stores_relaystate(db):
    engine = _mock_engine()
    p = _patch_engine(engine)
    try:
        external_idp._SAML_STATE_STORE.clear()
        resp = await external_idp.saml_start(str(PROVIDER_ID), db)
    finally:
        p.stop()
    assert isinstance(resp, RedirectResponse)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://idp.acme.com/sso")
    # exactly one RelayState recorded, bound to (provider, request_id)
    (stashed,) = external_idp._SAML_STATE_STORE.values()
    assert stashed == (str(PROVIDER_ID), "_req123")


@pytest.mark.asyncio
async def test_saml_start_rejects_non_saml_provider(db):
    db.query(models.ExternalIdpProvider).filter_by(id=PROVIDER_ID).update(
        {"type": "oidc"}
    )
    db.commit()
    engine = _mock_engine()
    p = _patch_engine(engine)
    try:
        with pytest.raises(HTTPException) as exc:
            await external_idp.saml_start(str(PROVIDER_ID), db)
    finally:
        p.stop()
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_saml_acs_issues_jwt_for_linked_user(db):
    # A local account already linked to this IdP identity (set the external
    # fields by attribute, mirroring the OIDC/JIT code path — User has a custom
    # __init__ that doesn't take them as kwargs).
    linked = models.User(userid="user@acme.com", active=True, is_admin=False)
    linked.external_idp_provider_id = PROVIDER_ID
    linked.external_subject = "saml-subject-1"
    db.add(linked)
    db.commit()
    engine = _mock_engine()
    p = _patch_engine(engine)
    relay = "relay-token-1"
    external_idp._SAML_STATE_STORE[relay] = (str(PROVIDER_ID), "_req123")
    request = MagicMock()
    request.form = AsyncMock(
        return_value={"SAMLResponse": "b64assertion", "RelayState": relay}
    )
    try:
        result = await external_idp.saml_acs(str(PROVIDER_ID), request, db)
    finally:
        p.stop()
    assert "Authorization" in result
    # the verified assertion + request_id were handed to the engine
    _, _, req_id = engine.process_saml_response.call_args.args
    assert req_id == "_req123"
    # RelayState is single-use
    assert relay not in external_idp._SAML_STATE_STORE


@pytest.mark.asyncio
async def test_saml_acs_rejects_unknown_relaystate(db):
    engine = _mock_engine()
    p = _patch_engine(engine)
    request = MagicMock()
    request.form = AsyncMock(
        return_value={"SAMLResponse": "x", "RelayState": "never-issued"}
    )
    try:
        with pytest.raises(HTTPException) as exc:
            await external_idp.saml_acs(str(PROVIDER_ID), request, db)
    finally:
        p.stop()
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_saml_acs_401_when_assertion_invalid(db):
    engine = _mock_engine()
    engine.process_saml_response.return_value = {
        "success": False,
        "subject": None,
        "groups": [],
        "email": None,
        "error": "signature mismatch",
    }
    p = _patch_engine(engine)
    relay = "relay-token-2"
    external_idp._SAML_STATE_STORE[relay] = (str(PROVIDER_ID), "_req")
    request = MagicMock()
    request.form = AsyncMock(
        return_value={"SAMLResponse": "tampered", "RelayState": relay}
    )
    try:
        with pytest.raises(HTTPException) as exc:
            await external_idp.saml_acs(str(PROVIDER_ID), request, db)
    finally:
        p.stop()
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_saml_endpoints_402_without_engine(db):
    loader = patch("backend.api.external_idp.module_loader")
    mock_loader = loader.start()
    mock_loader.get_module.return_value = None  # engine not licensed/loaded
    try:
        with pytest.raises(HTTPException) as exc:
            await external_idp.saml_start(str(PROVIDER_ID), db)
    finally:
        loader.stop()
    assert exc.value.status_code == 402
