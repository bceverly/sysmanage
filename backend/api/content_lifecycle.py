# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content Lifecycle Management API (Phase 16, Enterprise).

Satellite-style content views + lifecycle environments + gated promotion.  Like
repository mirroring, the OSS layer owns the API and the content lives on the
mirror-hosting agents; the Enterprise ``content_lifecycle_engine`` supplies the
plan-builders (materialize / serve / repoint).  When that engine isn't loaded
EVERY endpoint returns a clean HTTP 402 (never a 500) so the frontend can render
a license-upgrade prompt.

Slice 0 exposes read-only stubs (list environments / content views) — enough to
prove the gate and drive the plugin shell.  CRUD, publish, and promotion arrive
in later slices.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.partitions import get_shared_db

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_clm_module():
    """402 unless the Enterprise ``content_lifecycle_engine`` is loaded."""
    engine = module_loader.get_module("content_lifecycle_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Content lifecycle management requires a SysManage Professional+ "
                "(Enterprise) license. Please upgrade to access this feature."
            ),
        )
    return engine


@router.get("/content-lifecycle/environments", dependencies=[Depends(JWTBearer())])
async def list_environments(db: Session = Depends(get_shared_db)):
    """List the lifecycle environments along the ordered path."""
    _check_clm_module()
    rows = (
        db.query(models.SharedLifecycleEnvironment)
        .order_by(models.SharedLifecycleEnvironment.position)
        .all()
    )
    return [r.to_dict() for r in rows]


@router.get("/content-lifecycle/content-views", dependencies=[Depends(JWTBearer())])
async def list_content_views(db: Session = Depends(get_shared_db)):
    """List the content views."""
    _check_clm_module()
    rows = (
        db.query(models.SharedContentView).order_by(models.SharedContentView.name).all()
    )
    return [r.to_dict() for r in rows]
