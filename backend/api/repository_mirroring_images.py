# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Container-image endpoints for the Repository Mirroring API (Phase 17.2, Slice 3).

Track + capture OCI/container images into a mirror.  Extracted from
``backend.api.repository_mirroring`` to keep that module under the line-count
cap; these routes register on the SAME ``router`` object, so the public API is
unchanged.  Gated on the Pro+ ``oci_proxy_engine`` (402 when unlicensed).
"""

from datetime import datetime, timezone
from typing import List

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.repository_mirroring import router
from backend.api.repository_mirroring_helpers import (
    _MIRROR_NOT_FOUND,
    _check_oci_proxy_module,
    _dispatch_plan,
    _get_settings,
    _parse_uuid,
)
from backend.api.repository_mirroring_schemas import ImageTrackRequest
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.partitions import get_tenant_db


def _image_mirror_or_404(db: Session, mirror_id: str) -> models.MirrorRepository:
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
    "/mirror-repositories/{mirror_id}/images", dependencies=[Depends(JWTBearer())]
)
async def list_tracked_images(mirror_id: str, db: Session = Depends(get_tenant_db)):
    _check_oci_proxy_module()
    row = _image_mirror_or_404(db, mirror_id)
    rows = (
        db.query(models.MirrorImageContent)
        .filter(models.MirrorImageContent.repository_id == row.id)
        .order_by(models.MirrorImageContent.repository, models.MirrorImageContent.tag)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post(
    "/mirror-repositories/{mirror_id}/images", dependencies=[Depends(JWTBearer())]
)
async def track_image(
    mirror_id: str,
    request: ImageTrackRequest,
    db: Session = Depends(get_tenant_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    _check_oci_proxy_module()
    row = _image_mirror_or_404(db, mirror_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    existing = (
        db.query(models.MirrorImageContent)
        .filter(
            models.MirrorImageContent.repository_id == row.id,
            models.MirrorImageContent.registry == request.registry,
            models.MirrorImageContent.repository == request.repository,
            models.MirrorImageContent.tag == request.tag,
        )
        .first()
    )
    if existing:
        # Idempotent: re-tracking the same ref just resets it to TRACKED.
        existing.capture_status = "TRACKED"
        existing.updated_at = now
        db.commit()
        return existing.to_dict()
    image = models.MirrorImageContent(
        repository_id=row.id,
        registry=request.registry,
        repository=request.repository,
        tag=request.tag,
        capture_status="TRACKED",
        created_at=now,
        updated_at=now,
    )
    db.add(image)
    db.commit()
    return image.to_dict()


@router.delete(
    "/mirror-repositories/{mirror_id}/images/{image_content_id}",
    dependencies=[Depends(JWTBearer())],
)
async def untrack_image(
    mirror_id: str, image_content_id: str, db: Session = Depends(get_tenant_db)
):
    _check_oci_proxy_module()
    row = _image_mirror_or_404(db, mirror_id)
    iid = _parse_uuid(image_content_id, "image_content_id")
    image = (
        db.query(models.MirrorImageContent)
        .filter(
            models.MirrorImageContent.id == iid,
            models.MirrorImageContent.repository_id == row.id,
        )
        .first()
    )
    if not image:
        raise HTTPException(status_code=404, detail=_("Tracked image not found"))
    db.delete(image)
    db.commit()
    return {"message": _("Image untracked"), "id": image_content_id}


@router.post(
    "/mirror-repositories/{mirror_id}/capture-images",
    dependencies=[Depends(JWTBearer())],
)
async def capture_images(mirror_id: str, db: Session = Depends(get_tenant_db)):
    engine = _check_oci_proxy_module()
    row = _image_mirror_or_404(db, mirror_id)
    settings = _get_settings(db)
    tracked = (
        db.query(models.MirrorImageContent)
        .filter(models.MirrorImageContent.repository_id == row.id)
        .all()
    )
    if not tracked:
        raise HTTPException(
            status_code=400, detail=_("No images are tracked for this mirror")
        )

    images: List[dict] = [
        {"registry": t.registry, "repository": t.repository, "tag": t.tag}
        for t in tracked
    ]
    try:
        plan = engine.build_image_capture_plan(
            settings.mirror_root_path, row.name, images
        )
    except engine.OciProxyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    msg_id = _dispatch_plan(
        plan, row.host_id, action="image_capture", mirror_id=str(row.id)
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for tracked_image in tracked:
        tracked_image.capture_status = "DISPATCHED"
        tracked_image.last_capture_message_id = msg_id
        tracked_image.updated_at = now
    db.commit()
    return {
        "message": _("Image capture dispatched"),
        "mirror_id": mirror_id,
        "message_id": msg_id,
        "image_count": len(tracked),
    }
