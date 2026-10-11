# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Asset tags and the naming scheme (Phase 23.2 S3).

The tag belongs to the MACHINE (``models.Machine.asset_tag``), so every OS on a
multi-boot machine shows the same one and an OS reinstall keeps it.  The scheme
is one row per tenant database.  Reasons a tag or scheme is refused travel as
codes; the UI renders them in the user's language.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.models.machine import ASSET_TAG_SCHEME_ID
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import asset_tag_scheme as schemes
from backend.services.audit_service import ActionType, AuditService, EntityType

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(JWTBearer())])

_FIELDS = ("mode", "prefix", "separator", "digits", "suffix", "pattern", "enforce")


class SchemeBody(BaseModel):
    mode: str = schemes.MODE_BUILDER
    prefix: str = ""
    separator: str = "-"
    digits: int = 6
    suffix: str = ""
    pattern: str = ""
    enforce: bool = False


class TagBody(BaseModel):
    """``None`` (or "") clears the tag."""

    asset_tag: Optional[str] = None


def _require_role(current_user) -> None:
    if not current_user.has_role(SecurityRoles.MANAGE_ASSET_TAGS):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: %s role required")
            % SecurityRoles.MANAGE_ASSET_TAGS.value,
        )


def load_scheme(db: Session) -> schemes.Scheme:
    """The tenant's scheme; the defaults (nothing enforced) when never saved."""
    row = db.get(models.AssetTagScheme, ASSET_TAG_SCHEME_ID)
    if row is None:
        return schemes.Scheme()
    return schemes.Scheme.from_dict({f: getattr(row, f) for f in _FIELDS})


def _tags(db: Session) -> List[str]:
    return [
        t
        for (t,) in db.query(models.Machine.asset_tag)
        .filter(models.Machine.asset_tag.isnot(None))
        .all()
    ]


def _report(db: Session, scheme: schemes.Scheme) -> Dict[str, Any]:
    tags = _tags(db)
    nonconforming = schemes.nonconforming(scheme, tags)
    return {
        "scheme": scheme.to_dict(),
        "preview": (
            schemes.render(scheme, 42) if scheme.mode == schemes.MODE_BUILDER else None
        ),
        "examples": schemes.examples(scheme),
        "next_free": schemes.next_free(scheme, tags),
        "tagged": len(tags),
        "nonconforming": nonconforming,
    }


def _scheme_or_422(body: SchemeBody) -> schemes.Scheme:
    scheme = schemes.Scheme.from_dict(body.model_dump())
    problems = schemes.scheme_problems(scheme)
    if problems:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_scheme", "fields": problems}
        )
    return scheme


@router.get("/asset-tags/scheme")
async def get_scheme(db: Session = Depends(get_tenant_db)) -> Dict[str, Any]:
    """The scheme, a preview, examples, the next free tag and the tags that do
    not conform to it."""
    return _report(db, load_scheme(db))


@router.post("/asset-tags/scheme/preview")
async def preview_scheme(
    body: SchemeBody, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """What a DRAFT scheme would do -- the builder's live preview.  Saves
    nothing."""
    return _report(db, _scheme_or_422(body))


@router.put("/asset-tags/scheme")
async def save_scheme(
    body: SchemeBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Save the scheme.  Existing tags are reported, never rewritten."""
    _require_role(current_user)
    scheme = _scheme_or_422(body)
    row = db.get(models.AssetTagScheme, ASSET_TAG_SCHEME_ID)
    if row is None:
        row = models.AssetTagScheme(id=ASSET_TAG_SCHEME_ID)
        db.add(row)
    for field in _FIELDS:
        setattr(row, field, getattr(scheme, field))
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.updated_by = current_user.userid
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.SETTING,
        entity_name="asset_tag_scheme",
        description=_("Asset tag naming scheme changed"),
        user_id=current_user.id,
        username=current_user.userid,
        details=scheme.to_dict(),
        commit=False,
    )
    db.commit()
    return _report(db, scheme)


def _duplicate(db: Session, tag: str, machine_id: Optional[str] = None) -> bool:
    """Tags are unique ignoring case: GDR-0042 and gdr-0042 are one label."""
    query = db.query(models.Machine.id).filter(
        func.lower(models.Machine.asset_tag) == tag.lower()
    )
    if machine_id is not None:
        query = query.filter(models.Machine.id != machine_id)
    return query.first() is not None


@router.get("/asset-tags/check")
async def check_tag(
    tag: str, machine_id: Optional[str] = None, db: Session = Depends(get_tenant_db)
) -> Dict[str, Any]:
    """Entry-time feedback: does ``tag`` fit the scheme, and is it free?"""
    reason = schemes.check(load_scheme(db), tag)
    if reason is None and _duplicate(db, tag.strip(), machine_id):
        reason = "duplicate"
    return {"ok": reason is None, "reason": reason}


@router.put("/machine/{machine_id}/asset-tag")
async def set_machine_tag(
    machine_id: str,
    body: TagBody,
    db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Set, change or clear the machine's tag -- checked against the scheme
    and for uniqueness, and audited."""
    _require_role(current_user)
    machine = db.query(models.Machine).filter(models.Machine.id == machine_id).first()
    if machine is None:
        raise HTTPException(status_code=404, detail={"code": "machine_not_found"})
    tag = (body.asset_tag or "").strip() or None
    if tag is not None:
        reason = schemes.check(load_scheme(db), tag)
        if reason is None and _duplicate(db, tag, machine_id):
            reason = "duplicate"
        if reason is not None:
            raise HTTPException(status_code=422, detail={"code": reason})
    previous = machine.asset_tag
    machine.asset_tag = tag
    machine.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=str(machine.id),
        entity_name=tag or previous or str(machine.id),
        description=(_("Asset tag set to %s") % tag if tag else _("Asset tag cleared")),
        user_id=current_user.id,
        username=current_user.userid,
        details={"machine_id": str(machine.id), "from": previous, "to": tag},
        commit=False,
    )
    db.commit()
    return {"machine_id": str(machine.id), "asset_tag": machine.asset_tag}
