# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Browser landing for single sign-on (OIDC + SAML).

Until 2026-10-01 the OIDC callback and the SAML ACS returned the session as
raw JSON to the browser the identity provider sent there, and the login page
had no way to start SSO -- so a real browser sign-in ended on a page of JSON
(found by the Phase 21 audit, behind a ticked Phase 13 box).

THE HAND-OFF
------------
The IdP's browser arrives at our callback/ACS, not at the web UI, so the
session has to cross from one to the other.  It must not travel in a URL --
a token in a query string or fragment lands in history, logs and Referer
headers.  So the callback sets a short-lived, HttpOnly cookie scoped to
``/api/auth/sso`` and redirects the browser to the console's ``/login/sso``
page; that page asks ``POST /api/auth/sso/session`` for the session, which
hands it over once and deletes the cookie.  The cookie is SameSite=Lax: the
SAML ACS is a cross-site POST, and Lax still lets the console's own request
carry it.  Failures redirect to the same page with a reason code, so the user
lands on the console with a message instead of a JSON error.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.auth.auth_handler import decode_jwt, sign_jwt, sign_refresh_token
from backend.config import config
from backend.config.public_url import build_public_base_url
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

HANDOFF_COOKIE = "sysmanage_sso_handoff"
HANDOFF_PATH = "/api/auth/sso"
HANDOFF_SECONDS = 120
LANDING_PATH = "/login/sso"
SSO_TYPES = ("oidc", "saml")

# Failure reasons the landing page knows how to explain, by the status the
# sign-in refused with.  Only the code travels in the URL; the detail (which
# can carry IdP error text) stays in the server log.
REASON_FAILED = "failed"
_REASONS = {402: "unavailable", 403: "denied"}


def _console_url() -> str:
    from backend.api.password_reset import (  # pylint: disable=import-outside-toplevel
        get_dynamic_hostname,
    )

    return build_public_base_url(config.get_config(), get_dynamic_hostname)


def landing(userid: str, tenant_id: Optional[str]) -> RedirectResponse:
    """Send the signed-in browser to the console with the session in a
    short-lived HttpOnly cookie (never in the URL)."""
    base = _console_url()
    response = RedirectResponse(url=f"{base}{LANDING_PATH}", status_code=303)
    response.set_cookie(
        key=HANDOFF_COOKIE,
        value=sign_jwt(userid, tenant_id=tenant_id),
        max_age=HANDOFF_SECONDS,
        path=HANDOFF_PATH,
        secure=base.startswith("https://"),
        httponly=True,
        samesite="lax",
    )
    return response


def failure(status_code: int) -> RedirectResponse:
    """Send the browser to the console's SSO page with a reason to explain."""
    reason = _REASONS.get(status_code, REASON_FAILED)
    return RedirectResponse(
        url=f"{_console_url()}{LANDING_PATH}?error={reason}", status_code=303
    )


def _module_loaded() -> bool:
    return module_loader.get_module("external_idp_engine") is not None


@router.get("/api/auth/sso/providers")
async def list_sso_providers(
    tenant_id: Optional[str] = None, db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Enabled OIDC/SAML providers to offer on the login page (anonymous).

    Server-wide providers only, unless the page names a tenant: on a shared
    multi-tenant console, listing every tenant's IdP would show visitors the
    names of the customers on it."""
    if not _module_loaded():
        return []
    query = db.query(models.ExternalIdpProvider).filter(
        models.ExternalIdpProvider.enabled.is_(True),
        models.ExternalIdpProvider.type.in_(SSO_TYPES),
    )
    if tenant_id:
        try:
            tenant = uuid.UUID(tenant_id)
        except ValueError:
            return []
        query = query.filter(models.ExternalIdpProvider.tenant_id == tenant)
    else:
        query = query.filter(models.ExternalIdpProvider.tenant_id.is_(None))
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "type": row.type,
            "start_url": f"/api/auth/{row.type}/{row.id}/start",
        }
        for row in query.order_by(models.ExternalIdpProvider.name).all()
    ]


@router.post("/api/auth/sso/session")
async def take_sso_session(request: Request, response: Response) -> Dict[str, Any]:
    """Hand the console the session an SSO callback just created -- once.

    The cookie is deleted whatever happens, and the refresh cookie is set the
    same way a password login sets it."""
    token = request.cookies.get(HANDOFF_COOKIE)
    response.delete_cookie(HANDOFF_COOKIE, path=HANDOFF_PATH)
    claims = decode_jwt(token) if token else None
    if not claims or not claims.get("user_id"):
        raise HTTPException(
            status_code=401,
            detail=_("The single sign-on session has expired. Sign in again."),
        )
    userid = claims["user_id"]
    tenant_id = claims.get("tenant_id")
    from backend.api.auth import (  # pylint: disable=import-outside-toplevel
        _is_secure_cookie_enabled,
        _set_refresh_cookie,
    )

    _set_refresh_cookie(
        response,
        sign_refresh_token(userid, tenant_id=tenant_id),
        config.get_jwt_refresh_timeout(),
        _is_secure_cookie_enabled(config.get_config()),
    )
    return {"Authorization": token, "userid": userid}
