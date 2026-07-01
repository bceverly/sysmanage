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
from backend.persistence import db as db_module
from backend.persistence.models.logging_config import (
    OS_FAMILIES,
    SCOPE_AGENT,
    SCOPE_SERVER,
)
from backend.services import logging_config_service as svc

router = APIRouter()

_VALID_TARGETS_ALL = {"auto", "journald", "syslog", "eventlog", "none"}


def _sessionmaker():
    return sessionmaker(autocommit=False, autoflush=False, bind=db_module.get_engine())


class LoggingConfig(BaseModel):
    """One logging configuration (server or an agent OS family)."""

    native_enabled: bool = False
    native_target: str = "auto"
    native_identifier: Optional[str] = None
    log_level: Optional[str] = None
    verbosity: Optional[str] = None


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
