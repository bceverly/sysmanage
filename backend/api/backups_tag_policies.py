# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup policies by tag (Pro+ backup_engine, ROADMAP 24.6).

``/backups/tag-policies``: list, create, change and remove the templates
that give every host carrying a tag its backup settings; ``.../apply``
brings the hosts in line now rather than on the next scheduler pass.  The
lowest priority wins where several cover a host, and a host's own policy
(Configure) beats them all -- see ``services/backup_tag_policies``.  402
without the engine; Manage Backups for every change.
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api import backups_retention as retention
from backend.api.backups import PolicyBody, _host_or_404, _require, _validate_policy
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import backup_jobs as jobs
from backend.services import backup_tag_policies as tag_policies
from backend.services import backup_tick
from backend.services.audit_service import ActionType, AuditService, EntityType

router = APIRouter(dependencies=[Depends(JWTBearer())])

MAX_PRIORITY = 1000


class TagPolicyBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tag_id: str = Field(min_length=1, max_length=64)
    priority: int = 100
    enabled: bool = True
    settings: PolicyBody = Field(default_factory=PolicyBody)


def _engine_or_402() -> None:
    if not tag_policies.engine_loaded():
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                "backup_engine",
                _("Backup policies by tag need the Professional+ backup engine"),
            ),
        )


def _uuid(value: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=message) from exc


def _tag_or_422(db: Session, tag_id: str) -> models.Tag:
    tag = (
        db.query(models.Tag)
        .filter(models.Tag.id == _uuid(tag_id, _("Tag not found")))
        .first()
    )
    if tag is None:
        raise HTTPException(status_code=422, detail=_("Tag not found"))
    return tag


def _row_or_404(db: Session, policy_id: str) -> models.BackupTagPolicy:
    message = _("Tag policy not found")
    row = (
        db.query(models.BackupTagPolicy)
        .filter(models.BackupTagPolicy.id == _uuid(policy_id, message))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=message)
    return row


def _checked_settings(db: Session, body: TagPolicyBody) -> Dict[str, Any]:
    """The settings to store, checked as a host's own policy is."""
    if not 0 <= body.priority <= MAX_PRIORITY:
        raise HTTPException(
            status_code=422,
            detail=_("%(field)s must be a whole number from 0 to %(max)d")
            % {"field": "priority", "max": MAX_PRIORITY},
        )
    _validate_policy(body.settings)
    values = retention.gfs_values(body.settings)
    target = jobs.the_target(db)
    abilities = jobs.target_storage_abilities(db, target.id) if target else None
    retention.check_yearly(None, values, abilities)
    retention.check_verify_change(None, body.settings)
    return body.settings.model_dump()


def _host_count(db: Session, row: models.BackupTagPolicy) -> int:
    return db.query(models.HostTag).filter(models.HostTag.tag_id == row.tag_id).count()


def _applied_count(db: Session, row: models.BackupTagPolicy) -> int:
    return (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.tag_policy_id == row.id)
        .count()
    )


def _dict(db: Session, row: models.BackupTagPolicy) -> Dict[str, Any]:
    tag = db.query(models.Tag).filter(models.Tag.id == row.tag_id).first()
    return {
        "id": str(row.id),
        "name": row.name,
        "tag_id": str(row.tag_id),
        "tag_name": tag.name if tag else None,
        "priority": row.priority,
        "enabled": bool(row.enabled),
        "settings": tag_policies.settings_of(row),
        "hosts_tagged": _host_count(db, row),
        "hosts_applied": _applied_count(db, row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "created_by": row.created_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _audit(db, current_user, row, text: str, details) -> None:
    AuditService.log(
        db=db,
        user_id=current_user.id,
        username=current_user.userid,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_id=str(row.id),
        entity_name=row.name,
        description=text,
        details=details,
        commit=False,
    )


def _name_taken(db: Session, name: str, keep: Optional[uuid.UUID] = None) -> bool:
    query = db.query(models.BackupTagPolicy).filter(models.BackupTagPolicy.name == name)
    if keep is not None:
        query = query.filter(models.BackupTagPolicy.id != keep)
    return query.first() is not None


def _apply_now(db: Session, current_user) -> Dict[str, Any]:
    outcome = tag_policies.resolve(db, current_user)
    if outcome.changed():
        backup_tick.configure_now(db)
    return outcome.as_dict()


@router.get("/backups/tag-policies")
async def list_tag_policies(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, List[Dict[str, Any]]]:
    _engine_or_402()
    rows = (
        db.query(models.BackupTagPolicy)
        .order_by(models.BackupTagPolicy.priority, models.BackupTagPolicy.name)
        .all()
    )
    return {"tag_policies": [_dict(db, row) for row in rows]}


@router.post("/backups/tag-policies")
async def create_tag_policy(
    body: TagPolicyBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _engine_or_402()
    if jobs.the_target(db) is None:
        raise HTTPException(status_code=409, detail=_("Set up the backup target first"))
    tag = _tag_or_422(db, body.tag_id)
    name = body.name.strip()
    if _name_taken(db, name):
        raise HTTPException(status_code=409, detail=_("A tag policy has that name"))
    settings = _checked_settings(db, body)
    row = models.BackupTagPolicy(
        name=name,
        tag_id=tag.id,
        priority=body.priority,
        enabled=body.enabled,
        settings=json.dumps(settings),
        created_at=jobs.now(),
        created_by=current_user.userid,
        updated_at=jobs.now(),
    )
    db.add(row)
    db.flush()
    _audit(db, current_user, row, "Backup tag policy created",
           {"tag": tag.name, "priority": row.priority, "settings": settings})  # fmt: skip
    result = _apply_now(db, current_user)
    db.commit()
    return {"tag_policy": _dict(db, row), "applied": result}


@router.put("/backups/tag-policies/{policy_id}")
async def update_tag_policy(
    policy_id: str,
    body: TagPolicyBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _engine_or_402()
    row = _row_or_404(db, policy_id)
    tag = _tag_or_422(db, body.tag_id)
    name = body.name.strip()
    if _name_taken(db, name, keep=row.id):
        raise HTTPException(status_code=409, detail=_("A tag policy has that name"))
    settings = _checked_settings(db, body)
    row.name, row.tag_id, row.priority, row.enabled = (
        name,
        tag.id,
        body.priority,
        body.enabled,
    )
    row.settings = json.dumps(settings)
    row.updated_at = jobs.now()
    _audit(db, current_user, row, "Backup tag policy changed",
           {"tag": tag.name, "priority": row.priority, "settings": settings})  # fmt: skip
    result = _apply_now(db, current_user)
    db.commit()
    return {"tag_policy": _dict(db, row), "applied": result}


@router.delete("/backups/tag-policies/{policy_id}")
async def delete_tag_policy(
    policy_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """The hosts it covered move to the next tag policy that covers them, or
    keep what it gave them as their own policy, paused; never deleted."""
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _engine_or_402()
    row = _row_or_404(db, policy_id)
    _audit(db, current_user, row, "Backup tag policy removed", {})
    db.delete(row)
    db.flush()
    result = _apply_now(db, current_user)
    db.commit()
    return {"deleted": True, "applied": result}


@router.post("/backups/tag-policies/apply")
async def apply_tag_policies(
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    _engine_or_402()
    result = _apply_now(db, current_user)
    db.commit()
    return result


def _handover_refusal(refused: tag_policies.HandoverRefused) -> HTTPException:
    messages = {
        "no_policy": _("This host has no backup policy"),
        "already_tag": _("This host already follows its tag policy"),
        "not_covered": _(
            "No tag policy covers this host; there is nothing to switch to"
        ),
    }
    return HTTPException(
        status_code=409, detail=messages.get(refused.code, str(refused))
    )


@router.get("/backups/host/{host_id}/use-tag-policy")
async def preview_use_tag_policy(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Which tag policy would govern this host, and which of its own
    settings it would replace -- for the confirmation."""
    _engine_or_402()
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, host_id)
    try:
        return tag_policies.handover_preview(db, host)
    except tag_policies.HandoverRefused as refused:
        raise _handover_refusal(refused) from refused


@router.post("/backups/host/{host_id}/use-tag-policy")
async def use_tag_policy(
    host_id: str,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Hand a host on its own policy back to its tag policy, keeping its
    policy row -- and with it the repository, encryption keys, snapshots
    and history.  Configure makes it the host's own again."""
    _engine_or_402()
    _require(current_user, SecurityRoles.MANAGE_BACKUPS)
    host = _host_or_404(db, host_id)
    try:
        result = tag_policies.use_tag_policy(db, host, current_user)
    except tag_policies.HandoverRefused as refused:
        raise _handover_refusal(refused) from refused
    backup_tick.configure_now(db)
    db.commit()
    return result
