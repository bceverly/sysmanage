# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Single sign-on browser landing (found by the Phase 21 audit).

The OIDC callback and SAML ACS used to return the session as raw JSON to the
IdP's browser.  These tests pin the hand-off that replaced it: the callback
lands the browser on the console's /login/sso with the session in a one-shot
HttpOnly cookie (never the URL), failures land there with a reason code, and
the console takes the session exactly once.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import external_idp, sso_session
from backend.auth.auth_handler import decode_jwt, sign_jwt
from backend.persistence import models
from backend.persistence.db import Base

CONSOLE = "https://console.example.com"
OIDC_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    with sessionmaker(bind=eng)() as session:
        session.add_all(
            [
                models.ExternalIdpProvider(
                    id=OIDC_ID, name="Okta", type="oidc", enabled=True
                ),
                models.ExternalIdpProvider(
                    id=uuid.uuid4(), name="Azure", type="saml", enabled=True
                ),
                models.ExternalIdpProvider(
                    id=uuid.uuid4(), name="Directory", type="ldap", enabled=True
                ),
                models.ExternalIdpProvider(
                    id=uuid.uuid4(), name="Old", type="oidc", enabled=False
                ),
                models.ExternalIdpProvider(
                    id=uuid.uuid4(),
                    name="Tenant IdP",
                    type="oidc",
                    enabled=True,
                    tenant_id=TENANT_ID,
                ),
            ]
        )
        session.commit()
        yield session
    eng.dispose()


@pytest.fixture
def console():
    with patch.object(sso_session, "_console_url", return_value=CONSOLE):
        yield


def _engine():
    engine = MagicMock()
    engine.exchange_oidc_code.return_value = {
        "success": True,
        "subject": "okta-sub-1",
        "groups": [],
        "email": "user@acme.com",
        "error": None,
    }
    engine.map_external_groups_to_roles.return_value = []
    return engine


def _callback_request(state):
    request = MagicMock()
    request.query_params = {"code": "the-code", "state": state}
    return request


def _link_user(db):
    user = models.User(userid="user@acme.com", active=True, is_admin=False)
    user.external_idp_provider_id = OIDC_ID
    user.external_subject = "okta-sub-1"
    db.add(user)
    db.commit()


async def _callback(db, engine, state="state-1", issued=True):
    if issued:
        external_idp._OIDC_STATE_STORE[state] = str(OIDC_ID)
    with patch("backend.api.external_idp.module_loader") as loader, patch.object(
        external_idp, "_resolve_secret", return_value="client-secret"
    ):
        loader.get_module.return_value = engine
        return await external_idp.oidc_callback(
            str(OIDC_ID), _callback_request(state), db
        )


@pytest.mark.asyncio
async def test_oidc_callback_lands_signed_in_with_cookie_not_url(db, console):
    _link_user(db)
    result = await _callback(db, _engine())
    assert isinstance(result, RedirectResponse)
    assert result.status_code == 303
    assert result.headers["location"] == f"{CONSOLE}/login/sso"
    cookie = result.headers["set-cookie"]
    assert cookie.startswith("sysmanage_sso_handoff=")
    for attribute in ("HttpOnly", "Path=/api/auth/sso", "Max-Age=120", "Secure"):
        assert attribute in cookie
    assert "samesite=lax" in cookie.lower()
    token = cookie.split(";")[0].split("=", 1)[1]
    assert decode_jwt(token)["user_id"] == "user@acme.com"


@pytest.mark.asyncio
async def test_oidc_callback_bad_state_lands_with_reason(db, console):
    result = await _callback(db, _engine(), state="forged", issued=False)
    assert result.headers["location"] == f"{CONSOLE}/login/sso?error=failed"
    assert "set-cookie" not in result.headers


@pytest.mark.asyncio
async def test_oidc_callback_unlinked_identity_is_denied(db, console):
    result = await _callback(db, _engine())
    assert result.headers["location"] == f"{CONSOLE}/login/sso?error=denied"


@pytest.mark.asyncio
async def test_oidc_callback_without_engine_is_unavailable(db, console):
    result = await _callback(db, None)
    assert result.headers["location"] == f"{CONSOLE}/login/sso?error=unavailable"


@pytest.mark.asyncio
async def test_oidc_callback_without_mfa_says_so(db, console, caplog):
    """Phase 22.8: a provider requiring multi-factor sign-in refuses a token
    without it, with its own reason on the SSO page and a log line naming the
    provider and what the token said."""
    _link_user(db)
    engine = _engine()
    engine.exchange_oidc_code.return_value = {
        "success": False,
        "subject": "okta-sub-1",
        "groups": [],
        "email": "user@acme.com",
        "error": "the identity provider did not confirm multi-factor sign-in (amr=['pwd'])",
        "reason": "mfa_required",
    }
    with caplog.at_level("WARNING", logger=external_idp.logger.name):
        result = await _callback(db, engine)
    assert result.headers["location"] == f"{CONSOLE}/login/sso?error=mfa_required"
    assert "set-cookie" not in result.headers
    assert "Okta" in caplog.text and "amr=['pwd']" in caplog.text


@pytest.mark.asyncio
async def test_other_engine_failures_keep_the_generic_reason(db, console):
    engine = _engine()
    engine.exchange_oidc_code.return_value = {
        "success": False, "subject": None, "groups": [], "email": None,
        "error": "token exchange failed", "reason": None,
    }  # fmt: skip
    result = await _callback(db, engine)
    assert result.headers["location"] == f"{CONSOLE}/login/sso?error=failed"


def test_the_provider_carries_the_mfa_settings_to_the_engine(db):
    provider = db.query(models.ExternalIdpProvider).filter_by(id=OIDC_ID).one()
    assert provider.to_dict()["require_mfa"] is False  # off by default
    provider.require_mfa = True
    provider.oidc_acr_values = "gold"
    config = provider.to_dict()
    assert config["require_mfa"] is True and config["oidc_acr_values"] == "gold"


def test_http_console_gets_no_secure_flag():
    with patch.object(sso_session, "_console_url", return_value="http://dev:3000"):
        result = sso_session.landing("user@acme.com", None)
    assert "Secure" not in result.headers["set-cookie"]


@pytest.mark.asyncio
async def test_providers_lists_enabled_server_wide_sso_only(db):
    with patch.object(sso_session, "_module_loaded", return_value=True):
        listed = await sso_session.list_sso_providers(None, db)
    assert [(p["name"], p["type"]) for p in listed] == [
        ("Azure", "saml"),
        ("Okta", "oidc"),
    ]
    okta = listed[1]
    assert okta["start_url"] == f"/api/auth/oidc/{OIDC_ID}/start"


@pytest.mark.asyncio
async def test_providers_for_a_named_tenant(db):
    with patch.object(sso_session, "_module_loaded", return_value=True):
        listed = await sso_session.list_sso_providers(str(TENANT_ID), db)
        garbage = await sso_session.list_sso_providers("not-a-uuid", db)
    assert [p["name"] for p in listed] == ["Tenant IdP"]
    assert garbage == []


@pytest.mark.asyncio
async def test_providers_empty_without_license(db):
    with patch.object(sso_session, "_module_loaded", return_value=False):
        assert await sso_session.list_sso_providers(None, db) == []


def _request_with(cookie):
    request = MagicMock()
    request.cookies = {sso_session.HANDOFF_COOKIE: cookie} if cookie else {}
    return request


@pytest.mark.asyncio
async def test_take_session_hands_over_once_and_sets_refresh_cookie():
    token = sign_jwt("user@acme.com", tenant_id=str(TENANT_ID))
    response = Response()
    with patch("backend.api.auth._set_refresh_cookie") as refresh:
        body = await sso_session.take_sso_session(_request_with(token), response)
    assert body == {"Authorization": token, "userid": "user@acme.com"}
    refresh.assert_called_once()
    # The hand-off cookie is cleared in the same response.
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f"{sso_session.HANDOFF_COOKIE}=")
    assert "Max-Age=0" in cleared


@pytest.mark.asyncio
@pytest.mark.parametrize("cookie", [None, "not-a-jwt"])
async def test_take_session_without_valid_cookie_is_401(cookie):
    with pytest.raises(HTTPException) as exc:
        await sso_session.take_sso_session(_request_with(cookie), Response())
    assert exc.value.status_code == 401
