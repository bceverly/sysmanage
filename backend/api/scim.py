"""SCIM 2.0 inbound-provisioning API (Phase 13.1.E).

Pro+-gated, per-provider endpoints the IdP (Okta / Entra / …) PUSHES user
provisioning to:

    /api/scim/v2/{provider_id}/Users          GET (list/filter) · POST (create)
    /api/scim/v2/{provider_id}/Users/{id}     GET · PUT · PATCH · DELETE

These are NOT session endpoints — the IdP authenticates with a static bearer
token (``provider.scim_bearer_token_secret_id`` → Vault), so there is no
``JWTBearer``.  The SCIM **protocol** logic (validate/parse/render/patch/filter)
lives in the licensed ``external_idp_engine``; this layer authenticates the
token, calls the engine, and applies the create / grant / deactivate effects
through ``registry_service`` + the ``User`` model.  Provisioned users land in the
provider's tenant (when it is tenant-scoped) and are linked to the provider so
SSO sign-in finds them.
"""

import logging
import secrets as _secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from backend.api.external_idp import _resolve_secret
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)
router = APIRouter()

_SCIM_MEDIA = "application/scim+json"


def _engine():
    """Refuse the request when the Pro+ ``external_idp_engine`` isn't loaded."""
    engine = module_loader.get_module("external_idp_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_("SCIM provisioning requires a SysManage Professional+ license."),
        )
    return engine


def _scim_response(body: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=body, status_code=status_code, media_type=_SCIM_MEDIA)


def _scim_provider(db: Session, provider_id: str) -> models.ExternalIdpProvider:
    try:
        pid = uuid.UUID(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_("Unknown SCIM target")) from exc
    provider = (
        db.query(models.ExternalIdpProvider)
        .filter(models.ExternalIdpProvider.id == pid)
        .first()
    )
    if provider is None or not provider.scim_enabled:
        # Same 404 whether the provider is absent or SCIM is off — don't leak
        # which providers exist to an unauthenticated caller.
        raise HTTPException(status_code=404, detail=_("Unknown SCIM target"))
    return provider


def _authenticate(provider, request: Request) -> None:
    """Constant-time bearer-token check against the provider's SCIM token."""
    header = request.headers.get("authorization", "")
    presented = header[7:] if header.lower().startswith("bearer ") else ""
    expected = _resolve_secret(provider.scim_bearer_token_secret_id) or ""
    if not expected or not _secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=401,
            detail=_("Invalid or missing SCIM bearer token."),
            headers={"WWW-Authenticate": "Bearer"},
        )


def _location(request: Request, provider_id: str, user_id) -> str:
    return str(
        request.url_for("scim_get_user", provider_id=provider_id, user_id=user_id)
    )


def _to_record(user) -> dict:
    return {
        "id": str(user.id),
        "user_name": user.userid,
        "active": bool(user.active),
        "external_id": user.external_subject,
        "email": user.userid,
    }


def _grant_into_tenant(provider, email: str) -> None:
    """When the provider is tenant-scoped, ensure the registry identity + grant."""
    if not provider.tenant_id or not email:
        return
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )
    from backend.services import registry_service  # noqa: PLC0415

    with partition_session(partition=PARTITION_REGISTRY) as reg:
        ruser = registry_service.ensure_registry_user(reg, email)
        registry_service.ensure_grant(
            reg, ruser.id, provider.tenant_id, provider.jit_default_role
        )
        reg.commit()


@router.post("/api/scim/v2/{provider_id}/Users")
async def scim_create_user(
    provider_id: str, request: Request, payload: dict = Body(...)
):
    engine = _engine()
    db: Session = next(get_db())
    try:
        provider = _scim_provider(db, provider_id)
        _authenticate(provider, request)
        parsed = engine.scim_validate_user(payload)
        if not parsed["ok"]:
            return _scim_response(engine.scim_error(400, parsed["error"]), 400)
        attrs = parsed["attrs"]
        userid = attrs["user_name"].strip().lower()

        existing = (
            db.query(models.User)
            .filter(
                models.User.userid == userid,
                models.User.external_idp_provider_id == provider.id,
            )
            .first()
        )
        if existing is not None:
            return _scim_response(
                engine.scim_error(409, "User already exists", scim_type="uniqueness"),
                409,
            )

        # Re-link an existing local account with the same userid rather than
        # colliding on the unique userid constraint.
        user = db.query(models.User).filter(models.User.userid == userid).first()
        if user is None:
            user = models.User(userid=userid, active=attrs["active"], is_admin=False)
            db.add(user)
        user.active = attrs["active"]
        user.external_idp_provider_id = provider.id
        user.external_subject = attrs["external_id"]
        db.commit()
        db.refresh(user)

        _grant_into_tenant(provider, attrs["email"] or userid)
        logger.info(
            "SCIM-provisioned user %s for provider %s",
            sanitize_log(userid),
            sanitize_log(str(provider.id)),
        )
        record = _to_record(user)
        return _scim_response(
            engine.scim_user_to_resource(
                record, _location(request, provider_id, user.id)
            ),
            201,
        )
    finally:
        db.close()


@router.get("/api/scim/v2/{provider_id}/Users")
async def scim_list_users(provider_id: str, request: Request):
    engine = _engine()
    db: Session = next(get_db())
    try:
        provider = _scim_provider(db, provider_id)
        _authenticate(provider, request)
        query = db.query(models.User).filter(
            models.User.external_idp_provider_id == provider.id
        )
        filter_str = request.query_params.get("filter")
        if filter_str:
            parsed = engine.scim_parse_filter(filter_str)
            if parsed and parsed["attribute"].lower() in ("username", "userid"):
                query = query.filter(
                    models.User.userid == parsed["value"].strip().lower()
                )
            elif parsed and parsed["attribute"].lower() == "externalid":
                query = query.filter(models.User.external_subject == parsed["value"])
            else:
                # Unsupported filter → an empty result (never a blind match-all).
                return _scim_response(engine.scim_list_to_resource([], 0))
        resources = [
            engine.scim_user_to_resource(
                _to_record(u), _location(request, provider_id, u.id)
            )
            for u in query.all()
        ]
        return _scim_response(engine.scim_list_to_resource(resources, len(resources)))
    finally:
        db.close()


def _get_user_or_404(db, provider, user_id):
    try:
        uid = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_("User not found")) from exc
    user = (
        db.query(models.User)
        .filter(
            models.User.id == uid,
            models.User.external_idp_provider_id == provider.id,
        )
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail=_("User not found"))
    return user


@router.get("/api/scim/v2/{provider_id}/Users/{user_id}", name="scim_get_user")
async def scim_get_user(provider_id: str, user_id: str, request: Request):
    engine = _engine()
    db: Session = next(get_db())
    try:
        provider = _scim_provider(db, provider_id)
        _authenticate(provider, request)
        user = _get_user_or_404(db, provider, user_id)
        return _scim_response(
            engine.scim_user_to_resource(
                _to_record(user), _location(request, provider_id, user.id)
            )
        )
    finally:
        db.close()


@router.put("/api/scim/v2/{provider_id}/Users/{user_id}")
async def scim_replace_user(
    provider_id: str, user_id: str, request: Request, payload: dict = Body(...)
):
    engine = _engine()
    db: Session = next(get_db())
    try:
        provider = _scim_provider(db, provider_id)
        _authenticate(provider, request)
        user = _get_user_or_404(db, provider, user_id)
        parsed = engine.scim_validate_user(payload)
        if not parsed["ok"]:
            return _scim_response(engine.scim_error(400, parsed["error"]), 400)
        attrs = parsed["attrs"]
        user.active = attrs["active"]
        user.external_subject = attrs["external_id"]
        db.commit()
        db.refresh(user)
        return _scim_response(
            engine.scim_user_to_resource(
                _to_record(user), _location(request, provider_id, user.id)
            )
        )
    finally:
        db.close()


@router.patch("/api/scim/v2/{provider_id}/Users/{user_id}")
async def scim_patch_user(
    provider_id: str, user_id: str, request: Request, payload: dict = Body(...)
):
    engine = _engine()
    db: Session = next(get_db())
    try:
        provider = _scim_provider(db, provider_id)
        _authenticate(provider, request)
        user = _get_user_or_404(db, provider, user_id)
        result = engine.scim_apply_patch(_to_record(user), payload)
        if not result["ok"]:
            return _scim_response(engine.scim_error(400, result["error"]), 400)
        attrs = result["attrs"]
        # The deprovision signal — Okta/Entra PATCH ``active=false``.
        user.active = bool(attrs.get("active", user.active))
        if attrs.get("external_id") is not None:
            user.external_subject = attrs["external_id"]
        db.commit()
        db.refresh(user)
        return _scim_response(
            engine.scim_user_to_resource(
                _to_record(user), _location(request, provider_id, user.id)
            )
        )
    finally:
        db.close()


@router.delete("/api/scim/v2/{provider_id}/Users/{user_id}")
async def scim_delete_user(provider_id: str, user_id: str, request: Request):
    """Deprovision — soft-deactivate (preserve the audit trail), 204."""
    _engine()
    db: Session = next(get_db())
    try:
        provider = _scim_provider(db, provider_id)
        _authenticate(provider, request)
        user = _get_user_or_404(db, provider, user_id)
        user.active = False
        db.commit()
        logger.info(
            "SCIM-deprovisioned user %s for provider %s",
            sanitize_log(user.userid),
            sanitize_log(str(provider.id)),
        )
        return Response(status_code=204)
    finally:
        db.close()
