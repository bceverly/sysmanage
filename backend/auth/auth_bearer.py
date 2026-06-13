"""
This module ise used to verify the JWT token we use for authentication
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.auth_handler import decode_jwt
from backend.config import config
from backend.i18n import _


class JWTBearer(HTTPBearer):
    """
    This is a subclass of the FastAPI HTTPBearer class that is used to manage
    authentication via JWT
    """

    def __init__(self, auto_error: bool = True):
        """
        We are turning on auto_error here
        """
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        """
        This function verifies the JWT token as well as the overall
        credential scheme used.
        """
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if credentials:
            if credentials.scheme != "Bearer":
                raise HTTPException(
                    status_code=403, detail=_("Invalid authentication scheme.")
                )
            if not self.verify_jwt(credentials.credentials):
                raise HTTPException(status_code=401, detail=_("Expired token."))

            return credentials.credentials

        raise HTTPException(status_code=403, detail=_("Invalid authorization code."))

    def verify_jwt(self, jwtoken: str) -> bool:
        """
        This function decodes and verifies the JWT token.

        MFA-pending tokens (carrying ``mfa_pending: True``) are
        deliberately rejected here so they can't be used to access
        regular endpoints — their only valid recipient is
        ``/api/auth/mfa/verify``, which decodes them via
        ``decode_mfa_pending_token`` directly.
        """
        try:
            payload = decode_jwt(jwtoken)
        except (ValueError, TypeError, KeyError):
            payload = None
        if not payload:
            return False
        if payload.get("mfa_pending"):
            return False
        return True


async def get_current_user(  # NOSONAR
    token: str = Depends(JWTBearer()),
) -> str:
    """
    Extract the current user's userid from the JWT token.
    """
    try:
        payload = decode_jwt(token)
        if payload and "user_id" in payload:
            return payload["user_id"]
    except (ValueError, TypeError, KeyError):
        # Any decode/validation problem falls through to the 401 below;
        # we intentionally swallow the specific exception details rather
        # than echoing them back to the client.
        payload = None  # noqa: F841 — placates py/empty-except

    raise HTTPException(status_code=401, detail=_("Could not validate credentials"))


async def get_current_tenant(  # NOSONAR
    token: str = Depends(JWTBearer()),
) -> Optional[str]:
    """Resolve and verify the request's active tenant — Phase 13.1.B.

    Behavior by deployment mode:

    * **Multi-tenancy disabled (default).** Returns ``None`` — there is no
      tenant scoping and every endpoint behaves exactly as in single-tenant
      mode.  No registry lookup is performed.
    * **Multi-tenancy enabled.** Reads the ``tenant_id`` claim from the
      token.  If absent (e.g. a user with several grants who hasn't picked
      one yet), returns ``None`` and lets the caller decide.  If present,
      it is **verified against the registry**: the user must hold a live,
      non-expired grant to that active tenant, else 403.  This is the
      membership check that makes a stolen/forged ``tenant_id`` claim
      useless on its own.
    """
    if not config.is_multitenancy_enabled():
        return None

    try:
        payload = decode_jwt(token) or {}
    except (ValueError, TypeError, KeyError):
        payload = {}

    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        return None

    user_id = payload.get("user_id")

    # Late imports avoid a module-load cycle (partitions → db → config) and
    # keep auth_bearer importable in contexts that never touch the registry.
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        get_sessionmaker,
    )
    from backend.services import registry_service  # noqa: PLC0415

    session = get_sessionmaker(partition=PARTITION_REGISTRY)()
    try:
        if not registry_service.has_active_grant(session, user_id, tenant_id):
            raise HTTPException(
                status_code=403,
                detail=_("You do not have access to the selected account."),
            )
    finally:
        session.close()

    return tenant_id
