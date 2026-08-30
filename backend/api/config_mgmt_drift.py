# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Configuration drift: findings, dashboard and remediation (Phase 20.2).

Licence-gated at the ROUTER, like the profiles router and for the same reason:
a new endpoint added here is gated by default, which is the safe direction to
fail.

REMEDIATION IS JUST AN APPLY
----------------------------
"Remediate to baseline" is re-applying the profile the host drifted from, with
``check_mode`` off. It goes through the same ``config_mgmt_dispatch`` builder
the manual apply and the assignment tick use, so a remediation cannot diverge
from what a normal apply would have done.

It also inherits two guards without asking for them, and must NOT re-implement
either: ``enqueue_message`` refuses a command a host has not advertised support
for (Phase 19), and ``outbound_processor`` holds delivery outside a maintenance
window (Phase 14.2). A second copy of either check here could only disagree
with the real one.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import config_mgmt_dispatch as dispatch
from backend.services import config_mgmt_baseline as baseline
from backend.services import config_mgmt_drift as drift
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.CONFIG_MANAGEMENT_ENGINE)),
    ]
)


class DriftFindingResponse(BaseModel):
    """One divergence between a host and a profile."""

    id: str
    host_id: str
    host_fqdn: Optional[str] = None
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    task_name: str
    detail: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    last_run_id: Optional[str] = None


class DriftHostSummary(BaseModel):
    """One drifting host, for the fleet view."""

    host_id: str
    host_fqdn: Optional[str] = None
    finding_count: int
    profile_names: List[str]
    # The oldest unresolved finding on this host: "drifting since".
    drifting_since: Optional[datetime] = None


class RemediateRequest(BaseModel):
    """Re-apply a profile to a host to bring it back to baseline."""

    host_id: str
    profile_id: str


class RemediateResponse(BaseModel):
    """Result of queuing a remediation."""

    host_id: str
    profile_id: str
    queued: bool
    message: str


def _as_uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


@router.get("/config-management/drift", response_model=List[DriftHostSummary])
async def list_drifting_hosts(db_session: Session = Depends(get_tenant_db)):
    """Every host with unresolved drift, longest-drifting first.

    Ordered by how long the drift has stood rather than by hostname: a host
    that has been diverging for three weeks is a different problem from one
    that diverged an hour ago, and alphabetical order buries that distinction.
    """
    rows = (
        db_session.query(models.ConfigDriftFinding)
        .filter(models.ConfigDriftFinding.resolved_at.is_(None))
        .all()
    )

    by_host = {}
    for row in rows:
        entry = by_host.setdefault(
            str(row.host_id),
            {"count": 0, "profiles": set(), "since": row.first_seen_at},
        )
        entry["count"] += 1
        if row.profile_name:
            entry["profiles"].add(row.profile_name)
        if row.first_seen_at and (
            entry["since"] is None or row.first_seen_at < entry["since"]
        ):
            entry["since"] = row.first_seen_at

    fqdns = {}
    if by_host:
        for host in (
            db_session.query(models.Host)
            .filter(models.Host.id.in_([uuid.UUID(h) for h in by_host]))
            .all()
        ):
            fqdns[str(host.id)] = host.fqdn

    summaries = [
        DriftHostSummary(
            host_id=host_id,
            host_fqdn=fqdns.get(host_id),
            finding_count=entry["count"],
            profile_names=sorted(entry["profiles"]),
            drifting_since=drift.as_utc(entry["since"]),
        )
        for host_id, entry in by_host.items()
    ]
    summaries.sort(key=lambda s: (s.drifting_since is None, s.drifting_since))
    return summaries


@router.get(
    "/hosts/{host_id}/config-management/drift",
    response_model=List[DriftFindingResponse],
)
async def list_host_drift(
    host_id: str,
    db_session: Session = Depends(get_tenant_db),
):
    """Unresolved findings for one host, longest-standing first."""
    wanted = _as_uuid(host_id, _("Invalid host ID format"))
    host = db_session.query(models.Host).filter(models.Host.id == wanted).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    return [
        DriftFindingResponse(**drift.finding_to_dict(row, host_fqdn=host.fqdn))
        for row in drift.open_findings_for_host(db_session, wanted)
    ]


@router.post("/config-management/drift/remediate", response_model=RemediateResponse)
async def remediate_drift(
    request: RemediateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Re-apply a profile to bring one host back to its baseline.

    Gated on RUN_SCRIPT, matching ad-hoc apply: this runs the profile for
    real, so the blast radius is identical and a softer permission for the
    same capability would be an escalation path dressed up as a feature.
    """
    if not current_user.has_role(SecurityRoles.RUN_SCRIPT):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.RUN_SCRIPT.value,
        )

    host = (
        db_session.query(models.Host)
        .filter(
            models.Host.id == _as_uuid(request.host_id, _("Invalid host ID format"))
        )
        .first()
    )
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))
    if not host.active:
        raise HTTPException(status_code=400, detail=_("Host is not active"))

    profile = (
        db_session.query(models.ConfigProfile)
        .filter(
            models.ConfigProfile.id
            == _as_uuid(request.profile_id, _("Invalid profile ID format"))
        )
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_("Profile not found"))
    if not profile.is_active:
        # Remediating to a profile somebody deliberately retired would undo a
        # decision rather than enforce one.
        raise HTTPException(status_code=400, detail=_("This profile is not active"))

    try:
        parameters = dispatch.parameters_for(profile, check_mode=False)
    except dispatch.DispatchError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc

    # ONE id for both the envelope and the queue row, matching what
    # proplus_dispatch does. The agent echoes the ENVELOPE's message_id back as
    # `command_id`, so if the queue row carries a different id (which is what
    # enqueue_message generates when you don't pass one) the result cannot be
    # correlated to the command that produced it -- and config-profile results
    # were silently dropped for exactly that reason. Found 2026-08-28 by a
    # real round-trip.
    command_id = str(uuid.uuid4())
    command = Message(
        message_id=command_id,
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.APPLY_CONFIG_PROFILE,
            "parameters": parameters,
        },
    )
    QueueOperations().enqueue_message(
        message_type="command",
        message_id=command_id,
        message_data=command.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db_session,
    )
    db_session.commit()

    logger.info(
        "Drift remediation queued for host %s against profile %s",
        host.fqdn,
        profile.name,
    )
    return RemediateResponse(
        host_id=str(host.id),
        profile_id=str(profile.id),
        queued=True,
        # Findings are NOT cleared here. They resolve when the next check-mode
        # run observes the host is back in line -- claiming success before the
        # agent has reported would be a dashboard that lies.
        message=_("Remediation was queued for this host"),
    )


class BaselineCategoryCounts(BaseModel):
    """Exact totals, even when the item lists below are capped."""

    missing: int
    extra: int
    different: int
    reference_total: int
    target_total: int


class BaselineCategoryResult(BaseModel):
    """One inventory category compared between two hosts."""

    missing: List[dict]
    extra: List[dict]
    different: List[dict]
    counts: BaselineCategoryCounts
    truncated: bool


class BaselineDiffResponse(BaseModel):
    """How a target host differs from a reference host."""

    reference_host_id: str
    reference_fqdn: Optional[str] = None
    host_id: str
    host_fqdn: Optional[str] = None
    categories: dict
    total_differences: int
    identical: bool


@router.get(
    "/hosts/{host_id}/config-management/baseline-diff",
    response_model=BaselineDiffResponse,
)
async def compare_against_baseline(
    host_id: str,
    reference_host_id: str,
    categories: Optional[str] = None,
    db_session: Session = Depends(get_tenant_db),
):
    """How this host differs from a reference ("golden") host.

    The other kind of drift: ``/drift`` answers "does this host match its
    assigned profile", this answers "does this host match that host" -- which is
    what an operator reaches for when there is no profile yet and staging works
    while production does not.

    ``categories`` is an optional comma-separated subset; omit it to compare
    every category. Bounded to inventory the agent already reports, so it needs
    no new collection -- see ``config_mgmt_baseline`` for why that boundary is
    deliberate.
    """
    wanted = categories.split(",") if categories else None
    try:
        return baseline.compare_hosts(
            db_session, reference_host_id, host_id, categories=wanted
        )
    except baseline.BaselineError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


@router.get("/config-management/baseline-categories", response_model=List[str])
async def list_baseline_categories():
    """The comparison categories this server supports.

    Served rather than hard-coded in the UI so a category added server-side
    appears without a frontend release, and so the UI cannot offer one the
    server would refuse.
    """
    return list(baseline.CATEGORIES)
