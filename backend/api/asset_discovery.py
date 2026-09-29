# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Unenrolled asset discovery API (Phase 21.6).

S2: the tenant's discovery POLICY -- are agents listening to their networks,
and how often do they report. Off by default; turning it on is gated on its
own role (``Manage Network Discovery``) because it makes every capable agent
in the tenant listen to its segments, and every change is audited.

The whole router requires ``asset_discovery_engine``: without it nothing a
report says can be stored, so a policy switch would only make agents send
reports the server throws away.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.feature_gate import require_module_loaded
from backend.licensing.features import ModuleCode
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import asset_discovery_review as review
from backend.services import network_discovery_policy as policy_svc
from backend.services import network_sweep
from backend.services.audit_service import AuditService, EntityType

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.ASSET_DISCOVERY_ENGINE)),
    ]
)


class ExcludeRequest(BaseModel):
    """Devices an operator says are known and fine, and why."""

    asset_ids: List[str]
    category: str
    reason: str


class RevokeRequest(BaseModel):
    """Why an exclusion is being withdrawn."""

    reason: str


class PolicyRequest(BaseModel):
    """The tenant's discovery policy. Omitted interval keeps the current one."""

    enabled: bool
    report_interval_seconds: Optional[int] = None
    # S4: omitted keeps the current setting.
    sweep_enabled: Optional[bool] = None
    # S5: 7 / 30 / 90 / 365; omitted keeps the current setting.
    retention_days: Optional[int] = None


class AddressExclusionRequest(BaseModel):
    """A STATIC address (VIP, load balancer) registered as known."""

    address: str
    category: str
    reason: str


class SweepRequest(BaseModel):
    """One active sweep of an on-link IPv4 network."""

    cidr: str
    rate: Optional[int] = None


def _require_role(user, role) -> None:
    if not user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


@router.get("/asset-discovery/policy")
async def get_policy(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Whether this tenant's agents listen, and how often they report."""
    _require_role(current_user, SecurityRoles.VIEW_HOST_DETAILS)
    return policy_svc.get_policy(db)


@router.put("/asset-discovery/policy")
async def put_policy(
    request: PolicyRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Turn discovery on or off. Applied to capable agents immediately, and
    kept applied by the reconcile tick (new hosts, offline hosts, reinstalls)."""
    _require_role(current_user, SecurityRoles.MANAGE_NETWORK_DISCOVERY)
    interval = request.report_interval_seconds
    if interval is None:
        interval = policy_svc.get_policy(db)["report_interval_seconds"]
    try:
        change = policy_svc.set_policy(
            db,
            request.enabled,
            interval,
            current_user.userid,
            request.sweep_enabled,
            request.retention_days,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400, detail=_("Unsupported retention period")
        ) from error
    AuditService.log_update(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        entity_type=EntityType.SETTING,
        entity_name="network_discovery_policy",
        details=change,
    )
    summary = policy_svc.reconcile(db)
    db.commit()
    logger.info(
        "network discovery policy set to %s by %s in %s; %s",
        change["after"],
        current_user.userid,
        db.get_bind().url.database,
        summary,
    )
    return {**change["after"], "dispatch": summary}


# ---------------------------------------------------------------------------
# review (S3)
# ---------------------------------------------------------------------------


def _bad_request(error: review.ReviewError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


def _uuids(values: List[str]) -> List[uuid.UUID]:
    try:
        return [uuid.UUID(str(v)) for v in values]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_("Invalid device id")) from exc


@router.get("/asset-discovery/summary")
async def get_summary(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Counts, unmanaged devices per network, and every blind spot."""
    _require_role(current_user, SecurityRoles.VIEW_HOST_DETAILS)
    return review.summary(db)


@router.get("/asset-discovery/devices")
async def get_devices(  # pylint: disable=too-many-positional-arguments
    status: str = "unmanaged",
    network: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """One page of devices with their evidence and where they were seen."""
    _require_role(current_user, SecurityRoles.VIEW_HOST_DETAILS)
    try:
        return review.list_devices(db, status, network, search, limit, offset)
    except review.ReviewError as error:
        raise _bad_request(error) from error


@router.get("/asset-discovery/exclusions")
async def get_exclusions(
    include_revoked: bool = False,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Who decided which devices are fine, and why."""
    _require_role(current_user, SecurityRoles.VIEW_HOST_DETAILS)
    return {"exclusions": review.list_exclusions(db, include_revoked)}


@router.post("/asset-discovery/exclusions")
async def post_exclusions(
    request: ExcludeRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Permanently exclude devices (keyed by MAC, so DHCP cannot undo it)."""
    _require_role(current_user, SecurityRoles.MANAGE_NETWORK_DISCOVERY)
    try:
        result = review.exclude(
            db, _uuids(request.asset_ids), request.category, request.reason,
            current_user.userid,
        )  # fmt: skip
    except review.ReviewError as error:
        raise _bad_request(error) from error
    for exclusion in result["exclusions"]:
        AuditService.log_create(
            db=db,
            user_id=current_user.id,
            username=current_user.userid,
            entity_type=EntityType.DISCOVERED_ASSET,
            entity_id=exclusion["id"],
            entity_name=exclusion["identity"],
            details={"category": exclusion["category"], "reason": exclusion["reason"]},
        )
    db.commit()
    return result


@router.post("/asset-discovery/exclusions/address")
async def post_address_exclusion(
    request: AddressExclusionRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Register a static address (VIP / load balancer) as known -- S5."""
    _require_role(current_user, SecurityRoles.MANAGE_NETWORK_DISCOVERY)
    try:
        row = review.exclude_address(
            db, request.address, request.category, request.reason,
            current_user.userid,
        )  # fmt: skip
    except review.ReviewError as error:
        raise _bad_request(error) from error
    AuditService.log_create(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        entity_type=EntityType.DISCOVERED_ASSET,
        entity_id=row["id"],
        entity_name=row["identity"],
        details={"category": row["category"], "reason": row["reason"], "static": True},
    )
    db.commit()
    return row


@router.post("/asset-discovery/exclusions/{exclusion_id}/revoke")
async def post_revoke(
    exclusion_id: str,
    request: RevokeRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Withdraw an exclusion; the device shows as unmanaged again."""
    _require_role(current_user, SecurityRoles.MANAGE_NETWORK_DISCOVERY)
    (target,) = _uuids([exclusion_id])
    try:
        row = review.revoke(db, target, request.reason, current_user.userid)
    except review.ReviewError as error:
        raise _bad_request(error) from error
    AuditService.log_update(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        entity_type=EntityType.DISCOVERED_ASSET,
        entity_id=row["id"],
        entity_name=row["identity"],
        details={"revoked": True, "reason": row["revoke_reason"]},
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# active sweeps (S4)
# ---------------------------------------------------------------------------


@router.get("/asset-discovery/sweeps")
async def get_sweeps(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Every sweep requested in this tenant, newest first, whatever its outcome."""
    _require_role(current_user, SecurityRoles.VIEW_HOST_DETAILS)
    return {"sweeps": network_sweep.list_runs(db)}


@router.post("/asset-discovery/sweeps")
async def post_sweep(
    request: SweepRequest,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Sweep one on-link network now. Audited with its range and rate."""
    _require_role(current_user, SecurityRoles.MANAGE_NETWORK_DISCOVERY)
    try:
        run = network_sweep.request_sweep(
            db, request.cidr, request.rate, current_user.userid
        )
    except network_sweep.SweepError as error:
        status = 409 if error.code == "busy" else 400
        raise HTTPException(
            status_code=status, detail={"code": error.code, "message": str(error)}
        ) from error
    AuditService.log_create(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        entity_type=EntityType.NETWORK_SWEEP,
        entity_id=run["id"],
        entity_name=run["cidr"],
        details={
            "cidr": run["cidr"],
            "rate": run["rate"],
            "addresses": run["addresses"],
            "agent_host_id": run["agent_host_id"],
        },
    )
    db.commit()
    return run
