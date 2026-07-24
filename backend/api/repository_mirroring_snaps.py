# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Snap-content endpoints for the Repository Mirroring API (Phase 17.1, Slice 3).

Track + capture snaps into a mirror.  Extracted from
``backend.api.repository_mirroring`` to keep that module under the line-count
cap; these routes register on the SAME ``router`` object, so the public API is
unchanged.  Gated on the Pro+ ``snap_proxy_engine`` (402 when unlicensed).
"""

from datetime import datetime, timezone
from typing import List

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.repository_mirroring import router
from backend.api.repository_mirroring_helpers import (
    _MIRROR_NOT_FOUND,
    _check_snap_proxy_module,
    _dispatch_plan,
    _get_settings,
    _parse_uuid,
)
from backend.api.repository_mirroring_schemas import SnapTrackRequest
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db


def _mirror_or_404(db: Session, mirror_id: str) -> models.MirrorRepository:
    pid = _parse_uuid(mirror_id, "mirror_id")
    row = (
        db.query(models.MirrorRepository)
        .filter(models.MirrorRepository.id == pid)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=_(_MIRROR_NOT_FOUND))
    return row


@router.get(
    "/mirror-repositories/{mirror_id}/snaps", dependencies=[Depends(JWTBearer())]
)
async def list_tracked_snaps(mirror_id: str, db: Session = Depends(get_tenant_db)):
    _check_snap_proxy_module()
    row = _mirror_or_404(db, mirror_id)
    rows = (
        db.query(models.MirrorSnapContent)
        .filter(models.MirrorSnapContent.repository_id == row.id)
        .order_by(models.MirrorSnapContent.snap_name)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post(
    "/mirror-repositories/{mirror_id}/snaps", dependencies=[Depends(JWTBearer())]
)
async def track_snap(
    mirror_id: str,
    request: SnapTrackRequest,
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_snap_proxy_module()
    row = _mirror_or_404(db, mirror_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    existing = (
        db.query(models.MirrorSnapContent)
        .filter(
            models.MirrorSnapContent.repository_id == row.id,
            models.MirrorSnapContent.snap_name == request.snap_name,
        )
        .first()
    )
    if existing:
        # Idempotent: re-tracking updates the channel and resets to TRACKED.
        existing.channel = request.channel
        existing.capture_status = "TRACKED"
        existing.updated_at = now
        db.commit()
        return existing.to_dict()
    snap = models.MirrorSnapContent(
        repository_id=row.id,
        snap_name=request.snap_name,
        channel=request.channel,
        capture_status="TRACKED",
        created_at=now,
        updated_at=now,
    )
    db.add(snap)
    db.commit()
    return snap.to_dict()


@router.delete(
    "/mirror-repositories/{mirror_id}/snaps/{snap_content_id}",
    dependencies=[Depends(JWTBearer())],
)
async def untrack_snap(
    mirror_id: str, snap_content_id: str, db: Session = Depends(get_tenant_db)
):
    _check_snap_proxy_module()
    row = _mirror_or_404(db, mirror_id)
    sid = _parse_uuid(snap_content_id, "snap_content_id")
    snap = (
        db.query(models.MirrorSnapContent)
        .filter(
            models.MirrorSnapContent.id == sid,
            models.MirrorSnapContent.repository_id == row.id,
        )
        .first()
    )
    if not snap:
        raise HTTPException(status_code=404, detail=_("Tracked snap not found"))
    db.delete(snap)
    db.commit()
    return {"message": _("Snap untracked"), "id": snap_content_id}


@router.post(
    "/mirror-repositories/{mirror_id}/capture-snaps",
    dependencies=[Depends(JWTBearer())],
)
async def capture_snaps(mirror_id: str, db: Session = Depends(get_tenant_db)):
    engine = _check_snap_proxy_module()
    row = _mirror_or_404(db, mirror_id)
    settings = _get_settings(db)
    tracked = (
        db.query(models.MirrorSnapContent)
        .filter(models.MirrorSnapContent.repository_id == row.id)
        .all()
    )
    if not tracked:
        raise HTTPException(
            status_code=400, detail=_("No snaps are tracked for this mirror")
        )

    # build_snap_capture_plan captures a list of snaps at ONE channel, so group
    # tracked snaps by channel and merge the per-channel command groups into a
    # single dispatched plan (one message / one correlation).
    by_channel: dict = {}
    for tracked_snap in tracked:
        by_channel.setdefault(tracked_snap.channel, []).append(tracked_snap.snap_name)

    commands: List[dict] = []
    try:
        for channel, names in by_channel.items():
            plan = engine.build_snap_capture_plan(
                settings.mirror_root_path, row.name, names, channel
            )
            commands.extend(plan.get("commands", []))
    except engine.SnapProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    combined_plan = {
        "engine": "snap_proxy_engine",
        "action": "snap_capture",
        "files": [],
        "commands": commands,
    }
    msg_id = _dispatch_plan(
        combined_plan, row.host_id, action="snap_capture", mirror_id=str(row.id)
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for tracked_snap in tracked:
        tracked_snap.capture_status = "DISPATCHED"
        tracked_snap.last_capture_message_id = msg_id
        tracked_snap.updated_at = now
    db.commit()
    return {
        "message": _("Snap capture dispatched"),
        "mirror_id": mirror_id,
        "message_id": msg_id,
        "snap_count": len(tracked),
    }
