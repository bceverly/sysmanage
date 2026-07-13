"""
Logging-settings API (Phase 13.3).

Manage the DB-stored logging configuration: the server's own logging and the
per-OS-family agent defaults.  Saving applies the server's native handler live
and pushes the resolved config to agents (connected now, offline on reconnect).
DB settings win over the yaml file.
"""

import platform
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.config import config
from backend.i18n import _
from backend.licensing.features import FeatureCode
from backend.licensing.license_service import license_service
from backend.persistence import db as db_module
from backend.persistence.models.logging_config import (
    NATIVE_TARGETS,
    OS_FAMILIES,
    SCOPE_AGENT,
    SCOPE_SERVER,
    SYSLOG_PROTOCOLS,
)
from backend.services import logging_config_service as svc

router = APIRouter()

_VALID_TARGETS_ALL = set(NATIVE_TARGETS)


def _sessionmaker():
    return sessionmaker(autocommit=False, autoflush=False, bind=db_module.get_engine())


class LoggingConfig(BaseModel):
    """One logging configuration (server or an agent OS family)."""

    native_enabled: bool = False
    native_target: str = "auto"
    native_identifier: Optional[str] = None
    log_level: Optional[str] = None
    verbosity: Optional[str] = None
    # Remote-syslog forwarding (Phase 14.5) — only for native_target=syslog_remote.
    syslog_host: Optional[str] = None
    syslog_port: Optional[int] = None
    syslog_facility: Optional[str] = None
    syslog_protocol: Optional[str] = None


class UpdateLoggingSettingsRequest(BaseModel):
    """Partial update: server config and/or some agent OS families."""

    server: Optional[LoggingConfig] = None
    agents: Optional[Dict[str, LoggingConfig]] = None


def _require_admin(current_user):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: administrator required"),
        )


def _server_family() -> str:
    return svc.os_family_for_system(platform.system())


def _build_response(session: Session) -> dict:
    yaml_logging = config.get_config().get("logging", {})
    server_family = _server_family()
    agents = {}
    for family in OS_FAMILIES:
        stored = svc.resolve_agent_logging(session, family)
        agents[family] = stored  # None when unset (agent uses its yaml)
    return {
        "server": svc.resolve_server_logging(session, yaml_logging),
        "server_os_family": server_family,
        "server_valid_targets": svc.valid_targets_for_family(server_family),
        "agents": agents,
        "agent_valid_targets": {
            family: svc.valid_targets_for_family(family) for family in OS_FAMILIES
        },
        # Phase 14.5: the UI offers the syslog_remote target but disables it with a
        # "Professional" hint unless this is True; the PUT also rejects it (below).
        "log_routing_licensed": license_service.has_feature(FeatureCode.LOG_ROUTING),
    }


@router.get("/logging-settings", dependencies=[Depends(JWTBearer())])
async def get_logging_settings(current_user=Depends(require_authenticated_user)):
    """Return server + per-OS agent logging settings, plus valid targets."""
    _require_admin(current_user)
    with _sessionmaker()() as session:
        return _build_response(session)


def _validate_target(family: str, target: str) -> None:
    if target not in _VALID_TARGETS_ALL:
        raise HTTPException(
            status_code=400, detail=_("Invalid native log target: %s") % target
        )
    if target not in svc.valid_targets_for_family(family):
        raise HTTPException(
            status_code=400,
            detail=_("Target '%(t)s' is not valid for %(f)s")
            % {"t": target, "f": family},
        )


def _validate_syslog_remote(cfg: "LoggingConfig") -> None:
    """License-gate + validate the remote-syslog fields (Phase 14.5).

    Local sinks stay OSS; only ``syslog_remote`` requires the Professional
    ``LOG_ROUTING`` feature.  Rejecting it here is the server-side defence in
    depth behind the UI's disabled-with-a-hint option.
    """
    if cfg.native_target != "syslog_remote":
        return
    if not license_service.has_feature(FeatureCode.LOG_ROUTING):
        raise HTTPException(
            status_code=402,
            detail=_(
                "Remote syslog forwarding requires a Professional license "
                "(LOG_ROUTING)."
            ),
        )
    if not (cfg.syslog_host or "").strip():
        raise HTTPException(
            status_code=400,
            detail=_("A syslog host is required for the remote-syslog target."),
        )
    if cfg.syslog_port is not None and not 1 <= int(cfg.syslog_port) <= 65535:
        raise HTTPException(
            status_code=400, detail=_("syslog port must be between 1 and 65535.")
        )
    if cfg.syslog_protocol and cfg.syslog_protocol.lower() not in SYSLOG_PROTOCOLS:
        raise HTTPException(
            status_code=400, detail=_("syslog protocol must be 'udp' or 'tcp'.")
        )


@router.put("/logging-settings", dependencies=[Depends(JWTBearer())])
async def update_logging_settings(
    body: UpdateLoggingSettingsRequest,
    current_user=Depends(require_authenticated_user),
):
    """Upsert settings, apply the server handler live, and push to agents."""
    _require_admin(current_user)

    reverted_families: list = []
    with _sessionmaker()() as session:
        if body.server is not None:
            _validate_target(_server_family(), body.server.native_target)
            _validate_syslog_remote(body.server)
            svc.upsert_setting(session, SCOPE_SERVER, None, body.server.model_dump())

        # ``agents`` is None => not managing agents this save (server-only);
        # a dict (possibly empty) => the caller sent the full override set, so
        # any family NOT present had its override turned off and must revert.
        if body.agents is not None:
            for family, cfg in body.agents.items():
                if family not in OS_FAMILIES:
                    raise HTTPException(
                        status_code=400,
                        detail=_("Unknown OS family: %s") % family,
                    )
                _validate_target(family, cfg.native_target)
                _validate_syslog_remote(cfg)
                svc.upsert_setting(session, SCOPE_AGENT, family, cfg.model_dump())
            for family in OS_FAMILIES:
                if family not in body.agents and svc.delete_agent_setting(
                    session, family
                ):
                    reverted_families.append(family)
        session.commit()

        # Apply the server's own native handler live (DB wins over yaml).
        yaml_logging = config.get_config().get("logging", {})
        svc.apply_server_native_logging(
            svc.resolve_server_logging(session, yaml_logging)
        )

        # Push resolved per-OS config to agents (connected now, offline later).
        # Families whose override was just removed get an empty override so their
        # agents revert to yaml live.  Manages its own per-partition sessions.
        svc.push_logging_to_all_agents(revert_families=reverted_families)

        return _build_response(session)
