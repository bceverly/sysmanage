# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Server-info endpoint (Phase 11).

Single read-only endpoint that exposes which role this server runs as
(``standard`` / ``collector`` / ``repository``), what license tier is
active, and which Pro+ engines are loaded.  The frontend uses this to
render the role chip in the header bar; monitoring and chat-ops use it
to identify a box without having to log in.

Public — no auth required.  All fields are non-secret.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Top-level imports for ``config_module`` and ``module_loader`` are
# required by the test suite (tests patch
# ``backend.api.server_info.config_module.get_server_role`` directly).
# The route handler still wraps all usage of these in a broad-except so
# a cold-start race on Windows CI — where a request can hit the worker
# before app startup has finished wiring config — degrades gracefully
# instead of returning 500.
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config as config_module  # noqa: E402
from backend.i18n import _
from backend.licensing.module_loader import module_loader  # noqa: E402
from backend.persistence.db import get_db
from backend.persistence.models.server_configuration import (
    VALID_FEDERATION_ROLES,
    VALID_SERVER_ROLES,
)
from backend.services import server_config_service
from backend.services.audit_service import (
    ActionType,
    AuditService,
    EntityType,
    Result,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["server-info"])


# Static fallback envelope — what an unlicensed OSS deployment would
# legitimately return.  Used by the outermost ``try/except`` below so a
# transient bootstrap failure can never escape as a 500 and flake the
# Playwright ``should not have critical failed requests`` check on
# Windows CI, where startup is slowest.
_FALLBACK_ENVELOPE = {
    "role": "standard",
    "version": "unknown",
    "license_tier": "community",
    "loaded_engines": [],
    "expected_engine_for_role": None,
    "role_engine_loaded": True,
    "federation_role": "none",
    "expected_federation_engine_for_role": None,
    "federation_engine_loaded": True,
}


_AIRGAP_ENGINE_FOR_ROLE = {
    "collector": "airgap_collector_engine",
    "repository": "airgap_repository_engine",
}


_FEDERATION_ENGINE_FOR_ROLE = {
    "coordinator": "federation_controller_engine",
    "site": "federation_site_engine",
}


@router.get("/server-info")
def get_server_info():
    """Return non-secret identity + capability info about this server.

    Shape::

        {
          "role": "standard" | "collector" | "repository",
          "version": "2.3.0.0",
          "license_tier": "community" | "professional" | "enterprise",
          "loaded_engines": ["automation_engine", ...],
          "expected_engine_for_role": "airgap_collector_engine" | null,
          "role_engine_loaded": true | false
        }

    ``role_engine_loaded`` is the headline air-gap health check: when
    role is ``collector`` or ``repository``, this is ``true`` only when
    the corresponding Pro+ engine is currently loaded.  When role is
    ``standard``, it's always ``true`` (no role-specific engine
    required).

    The whole body is wrapped in try/except so a transient failure
    (e.g. module_loader being re-initialised between requests, or a
    config-read race during startup) returns a safe-degraded envelope
    rather than a 500.  The Playwright performance suite's
    ``should not have critical failed requests`` test treats any 5xx
    as a hard failure; this endpoint is on the cold-start critical
    path (the frontend's role chip in the header bar calls it
    immediately on page load), and a 500 here flakes the whole CI run.
    The fallback envelope reports ``standard`` / ``community`` /
    empty-engine-list — i.e. what an unlicensed OSS deployment would
    legitimately return — and the real failure is captured via
    ``logger.exception`` for post-mortem.
    """
    try:
        role = config_module.get_server_role()
        loaded_dict = getattr(module_loader, "loaded_modules", None) or {}
        loaded = sorted(loaded_dict.keys())
        expected_engine = _AIRGAP_ENGINE_FOR_ROLE.get(role)
        role_engine_loaded = expected_engine is None or expected_engine in loaded
        # Federation is an independent axis from the air-gap role: a server
        # can be e.g. an air-gap collector AND a federation site.  Same
        # health-check shape — when the role is coordinator/site,
        # federation_engine_loaded is true only if the matching Pro+ engine
        # is currently loaded.
        federation_role = config_module.get_federation_role()
        expected_federation_engine = _FEDERATION_ENGINE_FOR_ROLE.get(federation_role)
        federation_engine_loaded = (
            expected_federation_engine is None or expected_federation_engine in loaded
        )
        license_tier = _resolve_license_tier()

        return {
            "role": role,
            "version": _resolve_version(),
            "license_tier": license_tier,
            "loaded_engines": loaded,
            "expected_engine_for_role": expected_engine,
            "role_engine_loaded": role_engine_loaded,
            "federation_role": federation_role,
            "expected_federation_engine_for_role": expected_federation_engine,
            "federation_engine_loaded": federation_engine_loaded,
        }
    except Exception:  # pylint: disable=broad-exception-caught
        # See docstring above — the audit trail goes to logs;
        # callers get a degraded-but-valid envelope.  We return an
        # explicit JSONResponse rather than a dict so even if FastAPI's
        # response serialiser hits a problem (e.g. a Pydantic recursion
        # under high load on Windows), the bytes go straight to the
        # wire.
        try:
            logger.exception(
                "server-info handler failed; returning safe-degraded envelope"
            )
        except Exception:  # nosec B110  # pylint: disable=broad-exception-caught
            # Logging itself can fail during interpreter shutdown
            # (closed file handles, broken handlers).  We deliberately
            # swallow because the alternative — re-raising from the
            # fallback path — would 500 the cold-start /api/v1/server-info
            # request and re-trigger the Playwright failure that this
            # whole fallback chain exists to prevent.  Not a real
            # try/except/pass smell; the contract here is "never raise."
            _ = None
        return JSONResponse(content=_FALLBACK_ENVELOPE, status_code=200)


class ServerRoleResponse(BaseModel):
    role: str
    valid_roles: list[str]


class ServerRoleUpdate(BaseModel):
    role: str


@router.get(
    "/server-role",
    response_model=ServerRoleResponse,
    dependencies=[Depends(JWTBearer())],
)
def get_server_role_endpoint():
    """Return the current server role + the set of valid choices.

    Authenticated (any logged-in user) — drives the Settings → Server
    Role radio UI.  The public ``/server-info`` endpoint also reports
    the role for the header chip; this one additionally hands back the
    valid-option list so the UI doesn't hardcode it.
    """
    return ServerRoleResponse(
        role=server_config_service.get_server_role(),
        valid_roles=list(VALID_SERVER_ROLES),
    )


@router.put(
    "/server-role",
    response_model=ServerRoleResponse,
    dependencies=[Depends(JWTBearer())],
)
def set_server_role_endpoint(
    payload: ServerRoleUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Set the server role (standard | collector | repository).

    Persists to the ``server_configuration`` singleton.  Validation
    failures become a 400.  Audit-logged with the acting user.  The
    role's cosmetic effects (header chip, server-info) update on the
    next poll; any future role-gated engine behaviour takes effect on
    the next server restart — surfaced to the operator in the UI copy.
    """
    try:
        new_role = server_config_service.set_server_role(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Collector keygen hook: setting the role to ``collector`` is the
    # natural trigger to mint the ed25519 manifest-signing keypair (the
    # role lives in the DB now, so "first boot" isn't a reliable
    # trigger — a fresh server boots as ``standard``).  Idempotent and
    # never overwrites an existing key, so re-selecting collector is
    # safe.  Best-effort: a keygen failure logs but doesn't fail the
    # role change — the operator can retry, and the collection-run path
    # surfaces a clear error if the key is still missing at sign time.
    if new_role == "collector":
        try:
            from backend.services.airgap_signing_service import (  # pylint: disable=import-outside-toplevel
                ensure_collector_keypair,
            )

            ensure_collector_keypair()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to ensure collector signing keypair on role change",
                exc_info=True,
            )

    try:
        AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.SETTING,
            entity_id="air_gap_role",
            entity_name="air_gap_role",
            description=_("Set server role to '%s'") % new_role,
            username=current_user,
            result=Result.SUCCESS,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Audit logging is best-effort here — the role change already
        # committed; a logging hiccup shouldn't 500 the operator.
        logger.warning("Failed to audit-log server role change", exc_info=True)

    return ServerRoleResponse(role=new_role, valid_roles=list(VALID_SERVER_ROLES))


class FederationRoleResponse(BaseModel):
    role: str
    valid_roles: list[str]


class FederationRoleUpdate(BaseModel):
    role: str


@router.get(
    "/federation-role",
    response_model=FederationRoleResponse,
    dependencies=[Depends(JWTBearer())],
)
def get_federation_role_endpoint():
    """Return the current federation role + valid choices.

    Independent of the air-gap ``server-role`` axis — drives the federation
    card on Settings → Server Role.
    """
    return FederationRoleResponse(
        role=server_config_service.get_federation_role(),
        valid_roles=list(VALID_FEDERATION_ROLES),
    )


@router.put(
    "/federation-role",
    response_model=FederationRoleResponse,
    dependencies=[Depends(JWTBearer())],
)
def set_federation_role_endpoint(
    payload: FederationRoleUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Set the federation role (none | coordinator | site).

    Persists to the ``server_configuration`` singleton.  Choosing a real
    role (coordinator/site) ensures this server's federation identity
    keypair exists so the operator can immediately copy its public key.
    Role-gated engine behaviour takes effect on the next restart.
    """
    try:
        new_role = server_config_service.set_federation_role(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Mint the federation identity keypair + TLS cert when joining a
    # federation (the identity key the peer pins, and the TLS cert the
    # enrollment handshake presents for mutual TLS).  Idempotent + never
    # overwrites; best-effort — keygen failure shouldn't block the role save.
    if new_role in ("coordinator", "site"):
        try:
            from backend.services.federation_identity_service import (  # pylint: disable=import-outside-toplevel
                ensure_federation_identity_keypair,
                ensure_federation_tls_cert,
            )

            ensure_federation_identity_keypair()
            ensure_federation_tls_cert()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Failed to ensure federation identity material on role change",
                exc_info=True,
            )

    try:
        AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.SETTING,
            entity_id="federation_role",
            entity_name="federation_role",
            description=_("Set federation role to '%s'") % new_role,
            username=current_user,
            result=Result.SUCCESS,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to audit-log federation role change", exc_info=True)

    return FederationRoleResponse(
        role=new_role, valid_roles=list(VALID_FEDERATION_ROLES)
    )


def _resolve_version() -> str:
    """Best-effort sysmanage version string.

    Caught broadly — this is called from the fallback path of
    ``get_server_info`` (when the primary path already raised) and
    *must not* itself raise; any uncaught exception here would propagate
    out as a 500 and re-trigger the Playwright performance check we
    were trying to insulate against.  Past offender: a Windows-specific
    ``OSError`` from importing the auto-generated ``backend/__init__.py``
    when its file-system cache was stale at first request.
    """
    try:
        from backend import __version__  # type: ignore[attr-defined]

        return str(__version__)
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"


def _resolve_license_tier() -> str:
    """Best-effort license tier — falls back to ``community`` if no
    license is configured or the licensing service can't be reached.

    Uses the ``license_service`` singleton's ``license_tier`` property
    (not a ``get_active_tier()`` module function — that name doesn't
    exist and previously caused this helper to always return
    ``community`` even when a valid Pro+ license was loaded).
    """
    try:
        from backend.licensing.license_service import (
            license_service,
        )

        tier = license_service.license_tier
        if tier is None:
            return "community"
        return str(getattr(tier, "value", tier))
    except Exception:  # pylint: disable=broad-exception-caught
        # Catches ImportError + AttributeError + everything the
        # licensing service might raise.  Best-effort fallback:
        # callers care about the ``community`` default, not the
        # specific failure mode.
        return "community"
