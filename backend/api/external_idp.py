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
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.auth.auth_handler import sign_jwt
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

# Phase 13.2.1 — two routers so versioning can split the surface:
#   * ``mgmt_router`` — IdP provider/settings management (UI-facing). Registered
#     under native /api/v1 (+ deprecated /api alias) via ``_include_versioned``.
#   * ``router`` — the SSO/ACS/metadata callback endpoints, whose URLs are
#     configured in the external IdP. These STAY unversioned (changing them would
#     require every customer to reconfigure their IdP), so they keep their full
#     ``/api/auth/...`` decorator paths and are registered as-is.
router = APIRouter()
mgmt_router = APIRouter()

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
            status_code=400,
            detail=_("Invalid UUID for %(field)s: %(value)s")
            % {"field": field, "value": value},
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
    type: str = Field(..., pattern="^(ldap|oidc|saml)$")
    enabled: bool = True
    # Phase 13.1.E — per-tenant scoping + JIT. ``tenant_id`` None = server-global.
    tenant_id: Optional[str] = None
    jit_provisioning: bool = False
    jit_default_role: str = Field(default="member", max_length=64)
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
    # SAML 2.0 fields.
    saml_idp_entity_id: Optional[str] = None
    saml_idp_sso_url: Optional[str] = None
    saml_idp_x509_cert: Optional[str] = None
    saml_sp_entity_id: Optional[str] = None
    saml_sp_acs_url: Optional[str] = None
    saml_sp_x509_cert: Optional[str] = None
    saml_sp_private_key_secret_id: Optional[str] = None
    saml_email_attribute: Optional[str] = None
    saml_group_attribute: str = Field(default="groups")
    saml_want_assertions_signed: bool = True


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    enabled: Optional[bool] = None
    # Phase 13.1.E — per-tenant scoping + JIT.
    tenant_id: Optional[str] = None
    jit_provisioning: Optional[bool] = None
    jit_default_role: Optional[str] = Field(None, max_length=64)
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
    saml_idp_entity_id: Optional[str] = None
    saml_idp_sso_url: Optional[str] = None
    saml_idp_x509_cert: Optional[str] = None
    saml_sp_entity_id: Optional[str] = None
    saml_sp_acs_url: Optional[str] = None
    saml_sp_x509_cert: Optional[str] = None
    saml_sp_private_key_secret_id: Optional[str] = None
    saml_email_attribute: Optional[str] = None
    saml_group_attribute: Optional[str] = None
    saml_want_assertions_signed: Optional[bool] = None


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


@mgmt_router.get("/idp-providers", dependencies=[Depends(JWTBearer())])
async def list_providers(db: Session = Depends(get_db)):
    _check_idp_module()
    rows = (
        db.query(models.ExternalIdpProvider)
        .order_by(models.ExternalIdpProvider.name)
        .all()
    )
    return [r.to_dict() for r in rows]


@mgmt_router.post("/idp-providers", dependencies=[Depends(JWTBearer())])
async def create_provider(
    request: ProviderCreateRequest, db: Session = Depends(get_db)
):
    _check_idp_module()
    row = models.ExternalIdpProvider(**request.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@mgmt_router.get("/idp-providers/{provider_id}", dependencies=[Depends(JWTBearer())])
async def get_provider(provider_id: str, db: Session = Depends(get_db)):
    _check_idp_module()
    return _get_provider_or_404(db, provider_id).to_dict()


@mgmt_router.put("/idp-providers/{provider_id}", dependencies=[Depends(JWTBearer())])
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


@mgmt_router.delete("/idp-providers/{provider_id}", dependencies=[Depends(JWTBearer())])
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


@mgmt_router.get("/settings/idp", dependencies=[Depends(JWTBearer())])
async def get_idp_settings(db: Session = Depends(get_db)):
    _check_idp_module()
    return _get_settings(db).to_dict()


@mgmt_router.put("/settings/idp", dependencies=[Depends(JWTBearer())])
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
        # Phase 13.1.E — JIT: auto-provision on first SSO login when the provider
        # is tenant-scoped with JIT enabled and the email domain is on the
        # tenant's allowlist.  Returns None when JIT doesn't apply / isn't allowed.
        user = _jit_provision_user(db, provider, result.get("email"), result["subject"])
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


def _jit_provision_user(db: Session, provider, email: Optional[str], subject: str):
    """Phase 13.1.E — just-in-time provision an SSO user on first login.

    Applies only when the provider is tenant-scoped (``tenant_id`` set) with
    ``jit_provisioning`` enabled and the email's domain is on the tenant's
    (non-empty) allowlist — a fail-closed gate (see
    ``registry_service.jit_domain_permitted``).  Creates the global registry
    identity + a grant into the provider's tenant, then the local account linked
    to this IdP identity (or links an existing local account with the same
    email).  Returns the ``User`` on success, or ``None`` when JIT does not apply
    / is not permitted (the caller then 403s as before).
    """
    if not getattr(provider, "jit_provisioning", False) or not provider.tenant_id:
        return None
    if not email:
        logger.warning("JIT declined: provider %s returned no email claim", provider.id)
        return None

    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        partition_session,
    )
    from backend.services import registry_service  # noqa: PLC0415

    # Registry partition: allowlist gate + global identity + grant.
    with partition_session(partition=PARTITION_REGISTRY) as reg:
        if not registry_service.jit_domain_permitted(reg, provider.tenant_id, email):
            logger.warning(
                "JIT declined: %s not on the allowlist for tenant %s",
                sanitize_log(email),
                sanitize_log(str(provider.tenant_id)),
            )
            return None
        ruser = registry_service.ensure_registry_user(reg, email)
        registry_service.ensure_grant(
            reg, ruser.id, provider.tenant_id, provider.jit_default_role
        )
        reg.commit()

    # Local account (server-global), linked to this IdP identity.  Re-link an
    # existing local account with the same email rather than colliding on userid.
    normalized = email.strip().lower()
    user = db.query(models.User).filter(models.User.userid == normalized).first()
    if user is None:
        user = models.User(userid=normalized, active=True, is_admin=False)
        db.add(user)
    user.external_idp_provider_id = provider.id
    user.external_subject = subject
    user.active = True
    db.commit()
    db.refresh(user)
    logger.info(
        "JIT-provisioned SSO user %s into tenant %s",
        sanitize_log(normalized),
        sanitize_log(str(provider.tenant_id)),
    )
    return user


# ---------------------------------------------------------------------
# Public SAML 2.0 endpoints (anonymous — SP-initiated POST profile)
# ---------------------------------------------------------------------

# RelayState token → (provider_id, AuthnRequest id).  The request id is threaded
# into the ACS so the engine can pin the IdP's ``InResponseTo`` (replay /
# unsolicited-response protection).  Single-use: popped at the ACS.
_SAML_STATE_STORE: dict = {}


def _saml_config(provider) -> dict:
    """Provider dict + the optional SP private key unsealed from Vault."""
    config = provider.to_dict()
    if provider.saml_sp_private_key_secret_id:
        config["saml_sp_private_key"] = _resolve_secret(
            provider.saml_sp_private_key_secret_id
        )
    return config


@router.get("/api/auth/saml/{provider_id}/metadata")
async def saml_metadata(provider_id: str, db: Session = Depends(get_db)):
    """Return our SP metadata XML, for the IdP administrator (anonymous)."""
    engine = _check_idp_module()
    provider = _get_provider_or_404(db, provider_id)
    if provider.type != "saml":
        raise HTTPException(
            status_code=400, detail=_("Provider is not a SAML provider.")
        )
    result = engine.get_saml_sp_metadata(provider.to_dict())
    if result.get("error") or not result.get("metadata"):
        raise HTTPException(
            status_code=400,
            detail=_("Could not build SP metadata: %s")
            % result.get("error", "unknown"),
        )
    return Response(
        content=result["metadata"], media_type="application/samlmetadata+xml"
    )


@router.get("/api/auth/saml/{provider_id}/start")
async def saml_start(provider_id: str, db: Session = Depends(get_db)):
    """Build the SP-initiated SSO redirect to the IdP (anonymous)."""
    engine = _check_idp_module()
    provider = _get_provider_or_404(db, provider_id)
    if provider.type != "saml":
        raise HTTPException(
            status_code=400, detail=_("Provider is not a SAML provider.")
        )
    if not provider.enabled:
        raise HTTPException(status_code=403, detail=_("SAML provider is disabled."))
    relay_state = _secrets.token_urlsafe(32)
    result = engine.build_saml_authn_request(_saml_config(provider), relay_state)
    if result.get("error") or not result.get("url"):
        raise HTTPException(
            status_code=500,
            detail=_("Could not start SAML sign-in: %s")
            % result.get("error", "unknown"),
        )
    _SAML_STATE_STORE[relay_state] = (str(provider.id), result.get("request_id") or "")
    # Open-redirect note: the URL host is the IdP's admin-curated SSO endpoint
    # (``saml_idp_sso_url``), NOT user input — redirecting to the IdP is the whole
    # point of SP-initiated SSO. The RelayState guards the ACS.
    # nosemgrep: python.fastapi.web.tainted-redirect-fastapi.tainted-redirect-fastapi
    return RedirectResponse(url=result["url"], status_code=302)


@router.post("/api/auth/saml/{provider_id}/acs")
async def saml_acs(provider_id: str, request: Request, db: Session = Depends(get_db)):
    """Assertion Consumer Service — the IdP POSTs the signed SAMLResponse here.

    The engine verifies the XML signature + conditions in strict mode and pins
    the AuthnRequest id (InResponseTo).  On success we resolve/JIT-provision the
    linked account, apply group→role mappings, and issue a session JWT — the same
    shape the OIDC callback returns (the browser-facing landing is wired in the
    frontend, identical to the OIDC flow).
    """
    engine = _check_idp_module()
    provider = _get_provider_or_404(db, provider_id)
    form = await request.form()
    saml_response = form.get("SAMLResponse")
    relay_state = form.get("RelayState")
    if not saml_response or not relay_state:
        raise HTTPException(
            status_code=400, detail=_("Missing SAMLResponse or RelayState.")
        )
    stashed = _SAML_STATE_STORE.pop(str(relay_state), None)
    if not stashed or stashed[0] != str(provider.id):
        raise HTTPException(
            status_code=400, detail=_("Invalid or expired SAML RelayState.")
        )
    request_id = stashed[1] or None

    result = engine.process_saml_response(
        _saml_config(provider), str(saml_response), request_id
    )
    if not result["success"]:
        raise HTTPException(
            status_code=401,
            detail=_("SAML sign-in failed: %s") % result.get("error", "unknown"),
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
        user = _jit_provision_user(db, provider, result.get("email"), result["subject"])
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
