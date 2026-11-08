# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Settings for agent mutual TLS (ROADMAP 25.10).

``GET /api/agent-certificates`` -- the rollout mode (off / optional /
enforced) and where the fleet stands: how many approved hosts present a
certificate, which do not yet, and how many are expiring or expired.

``PUT /api/agent-certificates`` -- change the mode.  Per tenant when
multi-tenancy is on and a tenant is active, else server-wide.  Turning on
enforcement while approved hosts are not yet presenting a certificate would
cut them off, so it is refused with their count unless ``force`` is set --
the rollout is off -> optional -> enforced, and the Hosts list (or this
endpoint) shows who is not ready.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config, settings_service
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import request_sessionmaker
from backend.persistence.tenant_context import get_active_tenant
from backend.security import agent_mtls
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.agent_mtls_settings")

router = APIRouter()

# How many hosts not yet presenting are named in the response.
LISTED = 50


class HostRef(BaseModel):
    id: str
    fqdn: str
    status: str


class FleetStatus(BaseModel):
    approved: int
    presenting: int
    not_presenting: int
    expiring: int
    expired: int
    not_ready: List[HostRef]


class MtlsSettings(BaseModel):
    mode: str
    modes: List[str]
    fleet: FleetStatus


class MtlsUpdate(BaseModel):
    mode: str
    force: bool = False


def _tenant() -> Optional[str]:
    return get_active_tenant() if config.is_multitenancy_enabled() else None


def _mode() -> str:
    tenant_id = _tenant()
    if tenant_id:
        value = agent_mtls._normalize(  # pylint: disable=protected-access
            settings_service.get_tenant_setting(tenant_id, agent_mtls.MODE_SETTING)
        )
        if value:
            return value
    return (
        agent_mtls._normalize(  # pylint: disable=protected-access
            settings_service.get_setting(agent_mtls.MODE_SETTING)
        )
        or agent_mtls.DEFAULT_MODE
    )


_NOT_READY = (
    agent_mtls.STATUS_NONE,
    agent_mtls.STATUS_NOT_PRESENTED,
    agent_mtls.STATUS_EXPIRED,
)


def _fleet() -> FleetStatus:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with request_sessionmaker(_tenant())() as session:
        hosts = (
            session.query(models.Host)
            .filter(
                models.Host.approval_status == "approved",
                models.Host.active.is_(True),
            )
            .all()
        )
        statuses = [(h, agent_mtls.certificate_status(h, now)) for h in hosts]
    counts = {}
    for _host, status in statuses:
        counts[status] = counts.get(status, 0) + 1
    not_ready = [
        HostRef(id=str(h.id), fqdn=h.fqdn, status=status)
        for h, status in statuses
        if status in _NOT_READY
    ]
    return FleetStatus(
        approved=len(statuses),
        presenting=counts.get(agent_mtls.STATUS_PRESENTING, 0)
        + counts.get(agent_mtls.STATUS_EXPIRING, 0),
        not_presenting=len(not_ready),
        expiring=counts.get(agent_mtls.STATUS_EXPIRING, 0),
        expired=counts.get(agent_mtls.STATUS_EXPIRED, 0),
        not_ready=not_ready[:LISTED],
    )


def _current() -> MtlsSettings:
    return MtlsSettings(mode=_mode(), modes=list(agent_mtls.MODES), fleet=_fleet())


@router.get("/agent-certificates", dependencies=[Depends(JWTBearer())])
async def get_agent_certificates(
    _user: str = Depends(get_current_user),
) -> MtlsSettings:
    """The rollout mode and the fleet's certificate status."""
    return _current()


@router.put("/agent-certificates", dependencies=[Depends(JWTBearer())])
async def update_agent_certificates(
    payload: MtlsUpdate,
    user: str = Depends(get_current_user),
) -> MtlsSettings:
    """Change the rollout mode."""
    mode = agent_mtls._normalize(payload.mode)  # pylint: disable=protected-access
    if mode is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "mode_invalid",
                "message": _("The mode must be off, optional or enforced"),
            },
        )
    if mode == agent_mtls.MODE_ENFORCED and not payload.force:
        fleet = _fleet()
        if fleet.not_presenting:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "hosts_not_presenting",
                    "count": fleet.not_presenting,
                    "message": _(
                        "%d approved host(s) have not presented a valid client "
                        "certificate in the last 24 hours; enforcing now would "
                        "refuse them. Update their agents, or confirm to enforce "
                        "anyway."
                    )
                    % fleet.not_presenting,
                },
            )
    tenant_id = _tenant()
    if tenant_id:
        settings_service.set_tenant_setting(tenant_id, agent_mtls.MODE_SETTING, mode)
    else:
        settings_service.set_setting(agent_mtls.MODE_SETTING, mode)
    logger.info("Agent certificate mode set to %s by %s", mode, user)
    return _current()
