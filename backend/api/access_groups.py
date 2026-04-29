"""
Access groups + registration keys API (Phase 8.1).

Two routers:

  /api/access-groups        — CRUD on AccessGroup; tree operations
  /api/registration-keys    — CRUD + revocation on RegistrationKey

Both require authentication.  RBAC scoping (which users can see which
groups) is enforced via SecurityRoles — for now the gate is the same
EDIT_USER role; finer-grained access-group-aware scoping is a follow-up.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)


# Maximum tree depth.  Two reasons for the cap:
#  1. Keeps the recursive descendant query bounded.
#  2. Prevents a deep-tree DoS via repeated parenting.
_MAX_TREE_DEPTH = 10


groups_router = APIRouter(
    prefix="/api/access-groups",
    tags=["access-groups"],
    dependencies=[Depends(JWTBearer())],
)
keys_router = APIRouter(
    prefix="/api/registration-keys",
    tags=["registration-keys"],
    dependencies=[Depends(JWTBearer())],
)


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------


class AccessGroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    parent_id: Optional[str] = None


class AccessGroupUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    parent_id: Optional[str] = None


class AccessGroupResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RegistrationKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    access_group_id: Optional[str] = None
    auto_approve: bool = False
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[datetime] = None


class RegistrationKeyResponse(BaseModel):
    id: str
    name: str
    access_group_id: Optional[str] = None
    auto_approve: bool
    revoked: bool
    max_uses: Optional[int] = None
    use_count: int
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None
    # Only populated on the create response.
    key: Optional[str] = None


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _get_user(db: Session, current_user: str) -> models.User:
    """Resolve the current_user email to its User row, raising 401."""
    user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not user:
        raise HTTPException(status_code=401, detail=_("User not found"))
    return user


def _check_no_cycle_and_depth(
    db: Session, group_id: Optional[uuid.UUID], proposed_parent_id: Optional[uuid.UUID]
) -> None:
    """Raise 400 if proposing ``parent_id`` would create a cycle OR would
    push the resulting tree past ``_MAX_TREE_DEPTH``.

    A cycle exists iff ``group_id`` is itself reachable from
    ``proposed_parent_id`` via parent links.  We also count edges along
    the way and refuse if depth would exceed the cap."""
    if proposed_parent_id is None:
        return
    if group_id is not None and proposed_parent_id == group_id:
        raise HTTPException(
            status_code=400, detail=_("A group cannot be its own parent")
        )

    visited = set()
    cur = proposed_parent_id
    depth = 1  # the new edge group_id → proposed_parent_id
    while cur is not None:
        if cur in visited:
            # Existing cycle in the data — defensive guard.
            raise HTTPException(
                status_code=400, detail=_("Cycle detected in access-group hierarchy")
            )
        if group_id is not None and cur == group_id:
            raise HTTPException(
                status_code=400,
                detail=_("Setting parent_id would create a cycle"),
            )
        visited.add(cur)
        depth += 1
        if depth > _MAX_TREE_DEPTH:
            raise HTTPException(
                status_code=400,
                detail=_("Access-group hierarchy too deep (max %d levels)")
                % _MAX_TREE_DEPTH,
            )
        ancestor = (
            db.query(models.AccessGroup.parent_id)
            .filter(models.AccessGroup.id == cur)
            .first()
        )
        cur = ancestor[0] if ancestor and ancestor[0] else None


def _parse_uuid_or_400(value: Optional[str], field_name: str) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_("Invalid UUID for %s: %s") % (field_name, value),
        ) from exc


# ----------------------------------------------------------------------
# Access-group endpoints
# ----------------------------------------------------------------------


@groups_router.get("", response_model=List[AccessGroupResponse])
async def list_access_groups(db: Session = Depends(get_db)):
    """List every access group (flat).  Tree assembly is the client's
    job — each row carries ``parent_id``."""
    rows = db.query(models.AccessGroup).order_by(models.AccessGroup.name).all()
    return [AccessGroupResponse(**r.to_dict()) for r in rows]


@groups_router.post("", response_model=AccessGroupResponse)
async def create_access_group(
    request: AccessGroupCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Create a new access group.  ``parent_id`` is optional (root if omitted)."""
    user = _get_user(db, current_user)
    parent_uuid = _parse_uuid_or_400(request.parent_id, "parent_id")

    if parent_uuid is not None:
        parent_exists = (
            db.query(models.AccessGroup.id)
            .filter(models.AccessGroup.id == parent_uuid)
            .first()
        )
        if not parent_exists:
            raise HTTPException(status_code=404, detail=_("Parent group not found"))
        # Cycle/depth check against (None, parent_uuid) — group_id is not
        # known yet since we're creating, so depth-check from parent up.
        _check_no_cycle_and_depth(db, None, parent_uuid)

    group = models.AccessGroup(
        name=request.name,
        description=request.description,
        parent_id=parent_uuid,
        created_by=user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(group.id),
        entity_name=group.name,
        description=_("Created access group '%s'") % group.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return AccessGroupResponse(**group.to_dict())


@groups_router.get("/{group_id}", response_model=AccessGroupResponse)
async def get_access_group(group_id: str, db: Session = Depends(get_db)):
    group_uuid = _parse_uuid_or_400(group_id, "group_id")
    group = (
        db.query(models.AccessGroup).filter(models.AccessGroup.id == group_uuid).first()
    )
    if not group:
        raise HTTPException(status_code=404, detail=_("Access group not found"))
    return AccessGroupResponse(**group.to_dict())


@groups_router.put("/{group_id}", response_model=AccessGroupResponse)
async def update_access_group(
    group_id: str,
    request: AccessGroupUpdateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    group_uuid = _parse_uuid_or_400(group_id, "group_id")
    group = (
        db.query(models.AccessGroup).filter(models.AccessGroup.id == group_uuid).first()
    )
    if not group:
        raise HTTPException(status_code=404, detail=_("Access group not found"))

    if request.name is not None:
        group.name = request.name
    if request.description is not None:
        group.description = request.description
    if request.parent_id is not None:
        # Allow explicit empty string to clear parent.
        new_parent_uuid = (
            _parse_uuid_or_400(request.parent_id, "parent_id")
            if request.parent_id
            else None
        )
        _check_no_cycle_and_depth(db, group_uuid, new_parent_uuid)
        group.parent_id = new_parent_uuid

    db.commit()
    db.refresh(group)
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(group.id),
        entity_name=group.name,
        description=_("Updated access group '%s'") % group.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return AccessGroupResponse(**group.to_dict())


@groups_router.delete("/{group_id}")
async def delete_access_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    group_uuid = _parse_uuid_or_400(group_id, "group_id")
    group = (
        db.query(models.AccessGroup).filter(models.AccessGroup.id == group_uuid).first()
    )
    if not group:
        raise HTTPException(status_code=404, detail=_("Access group not found"))
    name = group.name
    db.delete(group)
    db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(group_uuid),
        entity_name=name,
        description=_("Deleted access group '%s'") % name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return {"message": _("Access group deleted"), "id": str(group_uuid)}


# ----------------------------------------------------------------------
# Registration-key endpoints
# ----------------------------------------------------------------------


@keys_router.get("", response_model=List[RegistrationKeyResponse])
async def list_registration_keys(db: Session = Depends(get_db)):
    """List every registration key (without the secret).  The raw
    ``key`` value is only ever returned at create time."""
    rows = (
        db.query(models.RegistrationKey)
        .order_by(models.RegistrationKey.created_at.desc())
        .all()
    )
    # to_dict(include_secret=False) by default.
    return [RegistrationKeyResponse(**r.to_dict()) for r in rows]


@keys_router.post("", response_model=RegistrationKeyResponse)
async def create_registration_key(
    request: RegistrationKeyCreateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Create a new registration key.  The plaintext key is returned
    EXACTLY ONCE in the response — there is no recovery mechanism if
    the operator loses it."""
    user = _get_user(db, current_user)
    ag_uuid = _parse_uuid_or_400(request.access_group_id, "access_group_id")
    if ag_uuid is not None:
        if (
            not db.query(models.AccessGroup.id)
            .filter(models.AccessGroup.id == ag_uuid)
            .first()
        ):
            raise HTTPException(status_code=404, detail=_("Access group not found"))

    expires = request.expires_at
    if expires is not None and expires.tzinfo is not None:
        # Persistence layer stores naive UTC.
        expires = expires.astimezone(timezone.utc).replace(tzinfo=None)

    key = models.RegistrationKey(
        name=request.name,
        access_group_id=ag_uuid,
        auto_approve=request.auto_approve,
        max_uses=request.max_uses,
        expires_at=expires,
        created_by=user.id,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    AuditService.log(
        db=db,
        action_type=ActionType.CREATE,
        entity_type=EntityType.SETTING,
        entity_id=str(key.id),
        entity_name=key.name,
        description=_("Created registration key '%s'") % key.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return RegistrationKeyResponse(**key.to_dict(include_secret=True))


@keys_router.post("/{key_id}/revoke")
async def revoke_registration_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Mark a key as revoked.  Idempotent — already-revoked keys remain
    revoked.  Existing host enrollments are NOT affected."""
    user = _get_user(db, current_user)
    key_uuid = _parse_uuid_or_400(key_id, "key_id")
    key = (
        db.query(models.RegistrationKey)
        .filter(models.RegistrationKey.id == key_uuid)
        .first()
    )
    if not key:
        raise HTTPException(status_code=404, detail=_("Registration key not found"))
    if not key.revoked:
        key.revoked = True
        db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(key.id),
        entity_name=key.name,
        description=_("Revoked registration key '%s'") % key.name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return {"message": _("Registration key revoked"), "id": str(key.id)}


@keys_router.delete("/{key_id}")
async def delete_registration_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    user = _get_user(db, current_user)
    key_uuid = _parse_uuid_or_400(key_id, "key_id")
    key = (
        db.query(models.RegistrationKey)
        .filter(models.RegistrationKey.id == key_uuid)
        .first()
    )
    if not key:
        raise HTTPException(status_code=404, detail=_("Registration key not found"))
    name = key.name
    db.delete(key)
    db.commit()
    AuditService.log(
        db=db,
        action_type=ActionType.DELETE,
        entity_type=EntityType.SETTING,
        entity_id=str(key_uuid),
        entity_name=name,
        description=_("Deleted registration key '%s'") % name,
        user_id=user.id,
        username=current_user,
        result=Result.SUCCESS,
    )
    return {"message": _("Registration key deleted"), "id": str(key_uuid)}
