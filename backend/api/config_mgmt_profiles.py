# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Configuration profile CRUD and assignments (Phase 20.1).

WHY THE WHOLE ROUTER IS LICENCE-GATED
-------------------------------------
Ad-hoc single-host apply is open-source; naming, storing, versioning and
ASSIGNING profiles is the Enterprise half (decided 2026-08-27). So the gate is
on the router rather than sprinkled per-route: a new endpoint added here is
gated by default, which is the safe direction to fail.

WHY THE RULES LIVE IN THE ENGINE
--------------------------------
Validation, version numbering and snapshot semantics come from the Pro+
module -- see ``config_mgmt_spec_shim``. This file owns HTTP, persistence and
authorisation; it deliberately does not re-implement any rule the engine
already owns, because two copies of a rule is how they start disagreeing.

ROLES
-----
Reuses the SCRIPT roles rather than inventing profile-specific ones. A stored
profile is the same class of object as a saved script -- executable content,
authored once and run against hosts -- so the same entitlement should govern
both, and a parallel set would need seeding into ``security_roles`` for no
behavioural gain. Overridable if that turns out to be the wrong call.
"""

import logging
import uuid
from datetime import datetime, timezone
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
from backend.services import config_mgmt_profile_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(JWTBearer()),
        Depends(require_module_loaded(ModuleCode.CONFIG_MANAGEMENT_ENGINE)),
    ]
)


class ProfileCreateRequest(BaseModel):
    """A new profile."""

    name: str
    engine: str
    content: str
    description: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    """Fields to change. Omitted fields are left alone."""

    name: Optional[str] = None
    engine: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ProfileResponse(BaseModel):
    """A stored profile."""

    id: str
    name: str
    description: Optional[str] = None
    engine: str
    content: str
    version: int
    is_active: bool
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProfileVersionResponse(BaseModel):
    """A prior body of a profile."""

    id: str
    profile_id: str
    version: int
    engine: str
    content: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


class AssignmentCreateRequest(BaseModel):
    """Where a profile applies. Exactly one target."""

    host_id: Optional[str] = None
    tag_id: Optional[str] = None
    site_id: Optional[str] = None
    schedule: Optional[str] = None
    check_mode: bool = False
    enabled: bool = True


class AssignmentResponse(BaseModel):
    """A profile assignment."""

    id: str
    profile_id: str
    host_id: Optional[str] = None
    tag_id: Optional[str] = None
    site_id: Optional[str] = None
    enabled: bool
    schedule: Optional[str] = None
    check_mode: bool
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_applied_at: Optional[datetime] = None


def _require_role(user, role) -> None:
    if not user.has_role(role):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required") % role.value,
        )


def _as_uuid(value: str, message: str) -> uuid.UUID:
    """Parse an ID, or 400 with a fully-spelled message.

    The message is passed in already translated rather than built from an
    interpolated noun: ``_("Invalid %s ID format") % "host"`` would ship the
    noun in English inside an otherwise translated sentence, and assumes an
    adjective-noun word order that not every language has.
    """
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=message) from exc


def _load_profile(db_session: Session, profile_id: str) -> models.ConfigProfile:
    profile = (
        db_session.query(models.ConfigProfile)
        .filter(
            models.ConfigProfile.id
            == _as_uuid(profile_id, _("Invalid profile ID format"))
        )
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail=_("Profile not found"))
    return profile


@router.get("/config-management/profiles", response_model=List[ProfileResponse])
async def list_profiles(
    engine: Optional[str] = None,
    db_session: Session = Depends(get_tenant_db),
):
    """Every stored profile, newest first, optionally filtered by engine."""
    query = db_session.query(models.ConfigProfile)
    if engine:
        query = query.filter(models.ConfigProfile.engine == engine.strip().lower())
    rows = query.order_by(models.ConfigProfile.updated_at.desc()).all()
    return [ProfileResponse(**svc.profile_to_dict(row)) for row in rows]


@router.post("/config-management/profiles", response_model=ProfileResponse)
async def create_profile(
    request: ProfileCreateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Store a new profile."""
    _require_role(current_user, SecurityRoles.ADD_SCRIPT)

    problem = svc.validate_profile(request.name, request.engine, request.content)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if svc.name_taken(db_session, request.name):
        # The column is unique; catching it here turns a 500 into a message
        # naming the actual conflict.
        raise HTTPException(
            status_code=409,
            detail=_("A profile named '%s' already exists") % request.name,
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    profile = models.ConfigProfile(
        name=request.name.strip(),
        description=request.description,
        engine=request.engine.strip().lower(),
        content=request.content,
        version=1,
        is_active=True,
        created_by=current_user.userid,
        updated_by=current_user.userid,
        created_at=now,
        updated_at=now,
    )
    db_session.add(profile)
    db_session.commit()
    logger.info("Config profile created: %s (%s)", profile.name, profile.engine)
    return ProfileResponse(**svc.profile_to_dict(profile))


@router.get("/config-management/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    db_session: Session = Depends(get_tenant_db),
):
    """One profile."""
    return ProfileResponse(**svc.profile_to_dict(_load_profile(db_session, profile_id)))


@router.put("/config-management/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    request: ProfileUpdateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Change a profile, snapshotting the outgoing body if it changed."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    profile = _load_profile(db_session, profile_id)

    changes = request.model_dump(exclude_unset=True)
    problem = svc.validate_update(profile, changes)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if "name" in changes and svc.name_taken(
        db_session, changes["name"], exclude_id=profile.id
    ):
        raise HTTPException(
            status_code=409,
            detail=_("A profile named '%s' already exists") % changes["name"],
        )

    svc.apply_update(db_session, profile, changes, current_user.userid)
    db_session.commit()
    return ProfileResponse(**svc.profile_to_dict(profile))


@router.delete("/config-management/profiles/{profile_id}")
async def delete_profile(
    profile_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Delete a profile, its versions and its assignments.

    Run HISTORY survives: ``config_profile_run.profile_id`` is ON DELETE SET
    NULL precisely so deleting a profile cannot erase the record that it ran.
    """
    _require_role(current_user, SecurityRoles.DELETE_SCRIPT)
    profile = _load_profile(db_session, profile_id)
    name = profile.name
    db_session.delete(profile)
    db_session.commit()
    logger.info("Config profile deleted: %s", name)
    return {"success": True, "message": _("Profile deleted")}


@router.get(
    "/config-management/profiles/{profile_id}/versions",
    response_model=List[ProfileVersionResponse],
)
async def list_profile_versions(
    profile_id: str,
    db_session: Session = Depends(get_tenant_db),
):
    """Prior bodies of a profile, newest version first."""
    profile = _load_profile(db_session, profile_id)
    rows = (
        db_session.query(models.ConfigProfileVersion)
        .filter(models.ConfigProfileVersion.profile_id == profile.id)
        .order_by(models.ConfigProfileVersion.version.desc())
        .all()
    )
    return [ProfileVersionResponse(**svc.version_to_dict(row)) for row in rows]


@router.get(
    "/config-management/profiles/{profile_id}/assignments",
    response_model=List[AssignmentResponse],
)
async def list_assignments(
    profile_id: str,
    db_session: Session = Depends(get_tenant_db),
):
    """Where this profile applies."""
    profile = _load_profile(db_session, profile_id)
    rows = (
        db_session.query(models.ConfigProfileAssignment)
        .filter(models.ConfigProfileAssignment.profile_id == profile.id)
        .all()
    )
    return [AssignmentResponse(**svc.assignment_to_dict(row)) for row in rows]


@router.post(
    "/config-management/profiles/{profile_id}/assignments",
    response_model=AssignmentResponse,
)
async def create_assignment(
    profile_id: str,
    request: AssignmentCreateRequest,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Assign a profile to a host, a tag or a site."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    profile = _load_profile(db_session, profile_id)

    problem = svc.validate_assignment(
        request.host_id, request.tag_id, request.site_id, request.schedule
    )
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assignment = models.ConfigProfileAssignment(
        profile_id=profile.id,
        host_id=(
            _as_uuid(request.host_id, _("Invalid host ID format"))
            if request.host_id
            else None
        ),
        tag_id=(
            _as_uuid(request.tag_id, _("Invalid tag ID format"))
            if request.tag_id
            else None
        ),
        site_id=(
            _as_uuid(request.site_id, _("Invalid site ID format"))
            if request.site_id
            else None
        ),
        enabled=request.enabled,
        schedule=(request.schedule or "").strip() or None,
        check_mode=request.check_mode,
        created_by=current_user.userid,
        created_at=now,
    )
    db_session.add(assignment)
    db_session.commit()
    return AssignmentResponse(**svc.assignment_to_dict(assignment))


@router.delete("/config-management/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: str,
    db_session: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Remove an assignment. The profile and its history are untouched."""
    _require_role(current_user, SecurityRoles.EDIT_SCRIPT)
    row = (
        db_session.query(models.ConfigProfileAssignment)
        .filter(
            models.ConfigProfileAssignment.id
            == _as_uuid(assignment_id, _("Invalid assignment ID format"))
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_("Assignment not found"))
    db_session.delete(row)
    db_session.commit()
    return {"success": True, "message": _("Assignment removed")}
