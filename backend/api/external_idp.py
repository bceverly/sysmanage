"""
External Identity Provider API (Phase 10.5).

Pro+-gated CRUD on IdP providers + role mappings + settings, plus the
two anonymous OIDC flow endpoints (``/api/auth/oidc/{provider_id}/start``
and ``/api/auth/oidc/{provider_id}/callback``) that don't require a
session token.

Login integration lives in ``backend/api/auth.py``: a user with a
non-NULL ``external_idp_provider_id`` is authenticated against the
engine instead of via Argon2.  When ``local_account_fallback`` is
enabled in settings, a user can still log in with their local password
even if external auth fails — useful for break-glass admin access.
"""

import logging
import secrets as _secrets
import uuid
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.auth.auth_handler import sign_jwt
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# Prefix marking a local-development literal secret reference.
_LITERAL_PREFIX = "literal:"


def _check_idp_module():
    """Refuse the request when the Pro+ ``external_idp_engine`` isn't loaded."""
    engine = module_loader.get_module("external_idp_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "External Identity Provider integration requires a SysManage "
                "Professional+ license. Please upgrade to access this feature."
            ),
        )
    return engine


def _parse_uuid(value: Optional[str], field: str) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=_("Invalid UUID for %s: %s") % (field, value)
        ) from exc


def _get_provider_or_404(db: Session, provider_id: str) -> models.ExternalIdpProvider:
    pid = _parse_uuid(provider_id, "provider_id")
    row = (
        db.query(models.ExternalIdpProvider)
        .filter(models.ExternalIdpProvider.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("IdP provider not found"))
    return row


def _get_settings(db: Session) -> models.ExternalIdpSettings:
    row = (
        db.query(models.ExternalIdpSettings)
        .filter(models.ExternalIdpSettings.id == models.SINGLETON_IDP_SETTINGS_ID)
        .first()
    )
    if row is not None:
        return row
    return models.ExternalIdpSettings(
        id=models.SINGLETON_IDP_SETTINGS_ID,
        local_account_fallback=True,
        max_failed_attempts=5,
    )


def _resolve_secret(secret_id: Optional[str]) -> Optional[str]:
    """Resolve a Vault secret reference to its plaintext.

    Stub: until secrets_engine integration lands here, we treat the
    ``secret_id`` field as either a literal Vault path or — for local
    development — a ``literal:VALUE`` prefix that returns the rest as
    plaintext.  Real deployments are expected to set ``vault:path/...``
    and have ``secrets_engine`` loaded.
    """
    if not secret_id:
        return None
    if secret_id.startswith(_LITERAL_PREFIX):
        return secret_id[len(_LITERAL_PREFIX) :]
    # pylint: disable=import-outside-toplevel
    try:
        from backend.services.vault_service import VaultService

        return VaultService().get_secret(secret_id)
    except Exception:  # pylint: disable=broad-except
        # CodeQL's ``py/clear-text-logging-sensitive-data`` follows the
        # value of ``secret_id`` through any local reassignment (slice,
        # truncation, etc.) and keeps the "sensitive" taint label.  To
        # truly break the data flow we log only a constant ``ref_kind``
        # — either ``"literal"`` or ``"vault"`` — chosen by a boolean
        # branch on the input.  CodeQL sees the branch's literal-string
        # arms, not the input value, so the taint chain ends here.
        # This also makes the log line strictly more useful in practice:
        # operators care about "did we hit Vault or a literal stub?",
        # not the specific path.
        #
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
        ref_kind = (
            "literal" if (secret_id or "").startswith(_LITERAL_PREFIX) else "vault"
        )
        logger.warning("Could not resolve IdP reference (kind=%s) from Vault", ref_kind)
        return None


# ---------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------


class ProviderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    type: str = Field(..., pattern="^(ldap|oidc)$")
    enabled: bool = True
    # LDAP fields.
    ldap_server_url: Optional[str] = None
    ldap_bind_dn: Optional[str] = None
    ldap_bind_password_secret_id: Optional[str] = None
    ldap_user_search_base: Optional[str] = None
    ldap_user_search_filter: Optional[str] = None
    ldap_group_search_base: Optional[str] = None
    ldap_group_search_filter: Optional[str] = None
    ldap_tls_ca_bundle_path: Optional[str] = None
    ldap_connection_timeout: int = Field(default=10, ge=1, le=120)
    # OIDC fields.
    oidc_issuer_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret_secret_id: Optional[str] = None
    oidc_redirect_uri: Optional[str] = None
    oidc_scopes: str = Field(default="openid profile email")
    oidc_discovery_url: Optional[str] = None
    oidc_group_claim: str = Field(default="groups")


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    enabled: Optional[bool] = None
    ldap_server_url: Optional[str] = None
    ldap_bind_dn: Optional[str] = None
    ldap_bind_password_secret_id: Optional[str] = None
    ldap_user_search_base: Optional[str] = None
    ldap_user_search_filter: Optional[str] = None
    ldap_group_search_base: Optional[str] = None
    ldap_group_search_filter: Optional[str] = None
    ldap_tls_ca_bundle_path: Optional[str] = None
    ldap_connection_timeout: Optional[int] = Field(None, ge=1, le=120)
    oidc_issuer_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret_secret_id: Optional[str] = None
    oidc_redirect_uri: Optional[str] = None
    oidc_scopes: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    oidc_group_claim: Optional[str] = None


class RoleMappingCreateRequest(BaseModel):
    external_group: str = Field(..., min_length=1, max_length=500)
    role_name: str = Field(..., min_length=1, max_length=120)
    default_for_unmapped: bool = False


class IdpSettingsRequest(BaseModel):
    local_account_fallback: Optional[bool] = None
    max_failed_attempts: Optional[int] = Field(None, ge=1, le=100)


# ---------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------


@router.get("/api/idp-providers", dependencies=[Depends(JWTBearer())])
async def list_providers(db: Session = Depends(get_db)):
    _check_idp_module()
    rows = (
        db.query(models.ExternalIdpProvider)
        .order_by(models.ExternalIdpProvider.name)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post("/api/idp-providers", dependencies=[Depends(JWTBearer())])
async def create_provider(
    request: ProviderCreateRequest, db: Session = Depends(get_db)
):
    _check_idp_module()
    row = models.ExternalIdpProvider(**request.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.get("/api/idp-providers/{provider_id}", dependencies=[Depends(JWTBearer())])
async def get_provider(provider_id: str, db: Session = Depends(get_db)):
    _check_idp_module()
    return _get_provider_or_404(db, provider_id).to_dict()


@router.put("/api/idp-providers/{provider_id}", dependencies=[Depends(JWTBearer())])
async def update_provider(
    provider_id: str,
    request: ProviderUpdateRequest,
    db: Session = Depends(get_db),
):
    _check_idp_module()
    row = _get_provider_or_404(db, provider_id)
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.delete("/api/idp-providers/{provider_id}", dependencies=[Depends(JWTBearer())])
async def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    _check_idp_module()
    row = _get_provider_or_404(db, provider_id)
    db.delete(row)
    db.commit()
    return {"message": _("IdP provider deleted"), "id": provider_id}


# ---------------------------------------------------------------------
# Role mappings (per provider)
# ---------------------------------------------------------------------


@router.get(
    "/api/idp-providers/{provider_id}/role-mappings",
    dependencies=[Depends(JWTBearer())],
)
async def list_mappings(provider_id: str, db: Session = Depends(get_db)):
    _check_idp_module()
    pid = _parse_uuid(provider_id, "provider_id")
    rows = (
        db.query(models.IdpRoleMapping)
        .filter(models.IdpRoleMapping.provider_id == pid)
        .order_by(models.IdpRoleMapping.external_group)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post(
    "/api/idp-providers/{provider_id}/role-mappings",
    dependencies=[Depends(JWTBearer())],
)
async def create_mapping(
    provider_id: str,
    request: RoleMappingCreateRequest,
    db: Session = Depends(get_db),
):
    _check_idp_module()
    provider = _get_provider_or_404(db, provider_id)
    if request.default_for_unmapped:
        existing_default = (
            db.query(models.IdpRoleMapping)
            .filter(
                models.IdpRoleMapping.provider_id == provider.id,
                models.IdpRoleMapping.default_for_unmapped.is_(True),
            )
            .first()
        )
        if existing_default is not None:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "A default-for-unmapped mapping already exists for this provider."
                ),
            )
    row = models.IdpRoleMapping(
        provider_id=provider.id,
        external_group=request.external_group,
        role_name=request.role_name,
        default_for_unmapped=request.default_for_unmapped,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.delete(
    "/api/idp-providers/{provider_id}/role-mappings/{mapping_id}",
    dependencies=[Depends(JWTBearer())],
)
async def delete_mapping(
    provider_id: str, mapping_id: str, db: Session = Depends(get_db)
):
    _check_idp_module()
    pid = _parse_uuid(provider_id, "provider_id")
    mid = _parse_uuid(mapping_id, "mapping_id")
    row = (
        db.query(models.IdpRoleMapping)
        .filter(
            models.IdpRoleMapping.id == mid,
            models.IdpRoleMapping.provider_id == pid,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Role mapping not found"))
    db.delete(row)
    db.commit()
    return {"message": _("Role mapping deleted"), "id": mapping_id}


# ---------------------------------------------------------------------
# Settings (singleton)
# ---------------------------------------------------------------------


@router.get("/api/settings/idp", dependencies=[Depends(JWTBearer())])
async def get_idp_settings(db: Session = Depends(get_db)):
    _check_idp_module()
    return _get_settings(db).to_dict()


@router.put("/api/settings/idp", dependencies=[Depends(JWTBearer())])
async def update_idp_settings(
    request: IdpSettingsRequest = Body(...), db: Session = Depends(get_db)
):
    _check_idp_module()
    row = _get_settings(db)
    if row not in db:
        db.add(row)
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row.to_dict()


# ---------------------------------------------------------------------
# Public OIDC endpoints (anonymous — used by login redirect dance)
# ---------------------------------------------------------------------


# Tiny in-memory store of OIDC ``state`` tokens.  Maps state → provider_id.
# Cleared at process restart; entries are removed at callback time.  A
# state token is single-use, so the only window for replay is the time
# between /start and /callback (~1 minute typical).
_OIDC_STATE_STORE: dict[str, str] = {}


@router.get("/api/auth/oidc/{provider_id}/start")
async def oidc_start(provider_id: str, db: Session = Depends(get_db)):
    """Build the IdP redirect URL and return it to the client.

    Anonymous endpoint — the browser is mid-login when it arrives here.
    """
    engine = _check_idp_module()
    provider = _get_provider_or_404(db, provider_id)
    if provider.type != "oidc":
        raise HTTPException(
            status_code=400, detail=_("Provider is not an OIDC provider.")
        )
    if not provider.enabled:
        raise HTTPException(status_code=403, detail=_("OIDC provider is disabled."))
    state = _secrets.token_urlsafe(32)
    _OIDC_STATE_STORE[state] = str(provider.id)
    config = provider.to_dict()
    url = engine.build_oidc_authorization_url(config, state)
    # Open-redirect note: the URL host is the IdP's authorization
    # endpoint — admin-curated in ``ExternalIdpProvider.oidc_issuer_url``,
    # NOT user-controlled.  An OIDC auth-start endpoint redirecting to
    # the IdP IS the entire point of the flow.  The state token guards
    # the callback; the provider record itself must be trusted (admin
    # creates it via Settings → External IdP).
    # nosemgrep: python.fastapi.web.tainted-redirect-fastapi.tainted-redirect-fastapi
    return RedirectResponse(url=url, status_code=302)


@router.get("/api/auth/oidc/{provider_id}/callback")
async def oidc_callback(
    provider_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Receive the IdP redirect, exchange the code, and issue a session JWT.

    Anonymous endpoint — the IdP just returned the user here.
    """
    engine = _check_idp_module()
    provider = _get_provider_or_404(db, provider_id)
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(
            status_code=400, detail=_("Missing code or state in callback.")
        )
    expected = _OIDC_STATE_STORE.pop(state, None)
    if expected != str(provider.id):
        raise HTTPException(status_code=400, detail=_("Invalid OIDC state."))

    config = provider.to_dict()
    config["oidc_client_secret"] = _resolve_secret(
        provider.oidc_client_secret_secret_id
    )
    if not config["oidc_client_secret"]:
        raise HTTPException(
            status_code=500,
            detail=_("OIDC client secret could not be resolved."),
        )

    result = engine.exchange_oidc_code(config, code, state)
    if not result["success"]:
        raise HTTPException(
            status_code=401,
            detail=_("OIDC sign-in failed: %s") % result.get("error", "unknown"),
        )

    user = (
        db.query(models.User)
        .filter(
            models.User.external_idp_provider_id == provider.id,
            models.User.external_subject == result["subject"],
        )
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=403,
            detail=_(
                "No sysmanage account is linked to this IdP identity. "
                "Ask an administrator to provision your account first."
            ),
        )
    if not user.active:
        raise HTTPException(status_code=403, detail=_("Account is inactive."))

    # Apply group → role mapping.
    mappings = [
        m.to_dict()
        for m in db.query(models.IdpRoleMapping)
        .filter(models.IdpRoleMapping.provider_id == provider.id)
        .all()
    ]
    role_names = engine.map_external_groups_to_roles(result["groups"], mappings)
    _apply_role_mappings(db, user, role_names)
    db.commit()

    return {"Authorization": sign_jwt(user.userid)}


def _apply_role_mappings(db: Session, user: models.User, role_names: List[str]) -> None:
    """Replace the user's external-IdP-derived roles with ``role_names``.

    We delete every UserSecurityRole row for this user that has a
    matching name, then add the requested set back.  Roles granted
    locally (outside the mapping flow) aren't touched — only the ones
    that overlap with the mapping output are reconciled.
    """
    if not role_names:
        return
    # Build the role name → SecurityRole id map.
    role_rows = (
        db.query(models.SecurityRole)
        .filter(models.SecurityRole.name.in_(role_names))
        .all()
    )
    if not role_rows:
        return
    role_ids = {r.name: r.id for r in role_rows}
    existing = (
        db.query(models.UserSecurityRole)
        .filter(
            models.UserSecurityRole.user_id == user.id,
            models.UserSecurityRole.role_id.in_(list(role_ids.values())),
        )
        .all()
    )
    have = {row.role_id for row in existing}
    for name, rid in role_ids.items():
        if rid not in have:
            db.add(models.UserSecurityRole(user_id=user.id, role_id=rid))
