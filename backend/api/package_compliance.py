"""
Package compliance API (Phase 8.3).

CRUD on PackageProfile + per-profile constraints; per-host scan endpoint
that evaluates the host's installed-package list against a profile and
records the result in HostPackageComplianceStatus.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.persistence.models.package_compliance import (
    CONSTRAINT_TYPES,
    STATUS_VALUES,
    VERSION_OPS,
)
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.services.package_compliance import evaluate_host_against_profile
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()


router = APIRouter(
    prefix="/api/package-profiles",
    tags=["package-profiles"],
    dependencies=[Depends(JWTBearer())],
)


# Reused 404 detail string — extracted so the wording can't drift
# between handlers and so SonarQube's duplication scanner is happy.
_ERR_PACKAGE_PROFILE_NOT_FOUND = "Package profile not found"


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------


class ConstraintSpec(BaseModel):
    package_name: str = Field(..., min_length=1, max_length=255)
    package_manager: Optional[str] = None
    constraint_type: str = "REQUIRED"
    version_op: Optional[str] = None
    version: Optional[str] = None

    @field_validator("constraint_type")
    @classmethod
    def _ct(cls, v):
        if v not in CONSTRAINT_TYPES:
            raise ValueError(
                f"constraint_type must be one of {CONSTRAINT_TYPES}; got {v}"
            )
        return v

    @field_validator("version_op")
    @classmethod
    def _op(cls, v):
        if v is None:
            return None
        if v not in VERSION_OPS:
            raise ValueError(f"version_op must be one of {VERSION_OPS}; got {v}")
        return v


class PackageProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    enabled: bool = True
    constraints: List[ConstraintSpec] = []


class PackageProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    enabled: Optional[bool] = None
    constraints: Optional[List[ConstraintSpec]] = None


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _get_user(db: Session, current_user: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _parse_uuid_or_400(value: Optional[str], field: str) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=_("Invalid UUID for %s: %s") % (field, value)
        ) from exc


def _replace_constraints(db: Session, profile, specs: List[ConstraintSpec]):
    """Drop the profile's existing constraints, then add the new spec list.
    Used by both create and update — semantics are "set-this-list" not
    "append-or-merge"."""
    db.query(models.PackageProfileConstraint).filter(
        models.PackageProfileConstraint.profile_id == profile.id
    ).delete(synchronize_session=False)
    for spec in specs:
        db.add(
            models.PackageProfileConstraint(
                profile_id=profile.id,
                package_name=spec.package_name,
                package_manager=spec.package_manager,
                constraint_type=spec.constraint_type,
                version_op=spec.version_op,
                version=spec.version,
            )
        )


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------


@router.get("")
async def list_profiles(db: Session = Depends(get_db)):
    rows = db.query(models.PackageProfile).order_by(models.PackageProfile.name).all()
    return [r.to_dict() for r in rows]


@router.post("")
async def create_profile(
    request: PackageProfileCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    profile = models.PackageProfile(
        name=request.name,
        description=request.description,
        enabled=request.enabled,
        created_by=user.id,
    )
    db.add(profile)
    db.flush()  # need profile.id for constraint inserts
    _replace_constraints(db, profile, request.constraints)
    db.commit()
    db.refresh(profile)

    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Created package profile '%s'") % profile.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return profile.to_dict(include_constraints=True)


@router.get("/{profile_id}")
async def get_profile(profile_id: str, db: Session = Depends(get_db)):
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.PackageProfile).filter(models.PackageProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_PACKAGE_PROFILE_NOT_FOUND))
    return profile.to_dict(include_constraints=True)


@router.put("/{profile_id}")
async def update_profile(
    profile_id: str,
    request: PackageProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.PackageProfile).filter(models.PackageProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_PACKAGE_PROFILE_NOT_FOUND))

    if request.name is not None:
        profile.name = request.name
    if request.description is not None:
        profile.description = request.description
    if request.enabled is not None:
        profile.enabled = request.enabled
    if request.constraints is not None:
        _replace_constraints(db, profile, request.constraints)

    db.commit()
    db.refresh(profile)
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Updated package profile '%s'") % profile.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return profile.to_dict(include_constraints=True)


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    profile = (
        db.query(models.PackageProfile).filter(models.PackageProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_PACKAGE_PROFILE_NOT_FOUND))
    name = profile.name
    db.delete(profile)
    db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(pid),
        entity_name=name,
        description=_("Deleted package profile '%s'") % name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return {"message": _("Package profile deleted"), "id": str(pid)}


@router.post("/{profile_id}/scan/{host_id}")
async def scan_host_against_profile(
    profile_id: str,
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Evaluate the host's installed-package inventory against the
    profile's constraints; persist the result in
    HostPackageComplianceStatus and return it.

    Pulls the host's installed packages from ``software_package`` rows
    so this endpoint works against the existing inventory pipeline; the
    agent does not need to do any extra work."""
    user = _get_user(db, current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    hid = _parse_uuid_or_400(host_id, "host_id")

    profile = (
        db.query(models.PackageProfile).filter(models.PackageProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_PACKAGE_PROFILE_NOT_FOUND))

    host = db.query(models.Host).filter(models.Host.id == hid).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    # Pull the host's currently-installed packages.  The
    # SoftwarePackage table is populated by the inventory pipeline.
    pkg_rows = (
        db.query(models.SoftwarePackage)
        .filter(models.SoftwarePackage.host_id == hid)
        .all()
    )
    installed = [
        {
            "name": p.package_name,
            "version": p.package_version or "",
            "manager": getattr(p, "package_manager", None),
        }
        for p in pkg_rows
    ]

    constraints = list(profile.constraints)
    status, violations = evaluate_host_against_profile(installed, constraints)

    # Upsert the per-(host, profile) status row.
    existing = (
        db.query(models.HostPackageComplianceStatus)
        .filter(
            models.HostPackageComplianceStatus.host_id == hid,
            models.HostPackageComplianceStatus.profile_id == pid,
        )
        .first()
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if existing is None:
        existing = models.HostPackageComplianceStatus(host_id=hid, profile_id=pid)
        db.add(existing)
    existing.status = status
    existing.violations = violations
    existing.last_scan_at = now
    db.commit()
    db.refresh(existing)

    AuditService.log(
        db=db,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.SETTING,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Scanned host '%s' against profile '%s': %s (%d violation(s))")
        % (host.fqdn, profile.name, status, len(violations)),
        user_id=user.id,
        username=current_user,
        result=(Result.SUCCESS if status == "COMPLIANT" else Result.FAILURE),
        details={
            "violation_count": len(violations),
            "host_id": str(hid),
            "profile_id": str(pid),
        },
    )

    return existing.to_dict()


@router.get("/status/host/{host_id}")
async def list_host_statuses(host_id: str, db: Session = Depends(get_db)):
    """Latest compliance status for one host across all profiles."""
    hid = _parse_uuid_or_400(host_id, "host_id")
    rows = (
        db.query(models.HostPackageComplianceStatus)
        .filter(models.HostPackageComplianceStatus.host_id == hid)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post("/{profile_id}/dispatch/{host_id}")
async def dispatch_compliance_check_to_agent(
    profile_id: str,
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Phase 8.3 wire-up:  ask the AGENT to evaluate compliance against
    its live local inventory and report back via the existing
    command-result WS channel.

    Differs from ``/{profile_id}/scan/{host_id}``:
      - That endpoint runs the evaluation on the SERVER against the
        cached ``software_package`` inventory.  Fast, but only as
        fresh as the most recent inventory upload.
      - This endpoint dispatches the constraints to the AGENT, which
        evaluates against its current live package state.  Slower
        round-trip but always-current; needed when an operator wants
        to confirm a compliance fix without waiting for the next
        inventory cycle.
    """
    user = _get_user(db, current_user)
    pid = _parse_uuid_or_400(profile_id, "profile_id")
    hid = _parse_uuid_or_400(host_id, "host_id")

    profile = (
        db.query(models.PackageProfile).filter(models.PackageProfile.id == pid).first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_(_ERR_PACKAGE_PROFILE_NOT_FOUND))

    host = db.query(models.Host).filter(models.Host.id == hid).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    # Serialize the profile's constraints as the agent expects them.
    constraints_payload = [
        {
            "id": str(c.id),
            "package_name": c.package_name,
            "package_manager": c.package_manager,
            "constraint_type": c.constraint_type,
            "version_op": c.version_op,
            "version": c.version,
        }
        for c in profile.constraints
    ]

    command_message = create_command_message(
        "evaluate_package_compliance",
        {
            "profile_id": str(profile.id),
            "profile_name": profile.name,
            "constraints": constraints_payload,
        },
    )
    queue_ops.enqueue_message(
        message_type="command",
        message_data=command_message,
        direction=QueueDirection.OUTBOUND,
        host_id=hid,
        db=db,
    )

    # Mark the existing status row as PENDING — when the agent's reply
    # comes back via the WS handler, it'll upsert with the actual
    # status + violations.
    existing = (
        db.query(models.HostPackageComplianceStatus)
        .filter(
            models.HostPackageComplianceStatus.host_id == hid,
            models.HostPackageComplianceStatus.profile_id == pid,
        )
        .first()
    )
    if existing is None:
        existing = models.HostPackageComplianceStatus(
            host_id=hid, profile_id=pid, status="PENDING"
        )
        db.add(existing)
    else:
        existing.status = "PENDING"
    db.commit()

    AuditService.log(
        db=db,
        action_type=ActionType.AGENT_MESSAGE,
        entity_type=EntityType.SETTING,
        entity_id=str(profile.id),
        entity_name=profile.name,
        description=_("Dispatched compliance check to agent '%s' for profile '%s'")
        % (host.fqdn, profile.name),
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
        details={"host_id": str(hid), "profile_id": str(pid)},
    )

    return {
        "status": "dispatched",
        "host_id": str(hid),
        "profile_id": str(pid),
        "constraint_count": len(constraints_payload),
    }
