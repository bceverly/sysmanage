# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content Lifecycle Management — version diff API (Phase 16, Slice 8).

"What changed between v{n} and v{n-1}": publish stores no per-file manifest, so
the diff is agent-computed -- an agent lists the package basenames of both
version stores on the mirror host, and the result handler compares the two
stdouts server-side and stores the added/removed sets on the newer version's
``manifest["diff_from_prev"]`` (no new table).  Read-only: it never mutates the
immutable stores.

Split out of ``backend.api.content_lifecycle`` (line-count cap); mounts its own
router and reuses that module's gate + lookup helpers.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.content_lifecycle import (
    _check_clm_module,
    _get_cv_or_404,
    _resolve_cv_serving_host,
)
from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import models
from backend.persistence.models.content_lifecycle import CVV_PUBLISHED
from backend.persistence.partitions import get_shared_db, get_tenant_db

logger = logging.getLogger(__name__)

router = APIRouter()


def _published_version(shared_db: Session, cv, version: int):
    return (
        shared_db.query(models.SharedContentViewVersion)
        .filter(models.SharedContentViewVersion.content_view_id == cv.id)
        .filter(models.SharedContentViewVersion.version == version)
        .filter(models.SharedContentViewVersion.status == CVV_PUBLISHED)
        .first()
    )


def _prev_published(shared_db: Session, cv, version: int):
    """The published version immediately below ``version`` (the diff baseline)."""
    return (
        shared_db.query(models.SharedContentViewVersion)
        .filter(models.SharedContentViewVersion.content_view_id == cv.id)
        .filter(models.SharedContentViewVersion.version < version)
        .filter(models.SharedContentViewVersion.status == CVV_PUBLISHED)
        .order_by(models.SharedContentViewVersion.version.desc())
        .first()
    )


@router.post(
    "/content-lifecycle/content-views/{cv_id}/versions/{version}/diff",
    dependencies=[Depends(JWTBearer())],
)
async def compute_version_diff(
    cv_id: str,
    version: int,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
):
    """Kick off a package diff of ``version`` against the previous published
    version; the result lands on the newer version's manifest (GET to read)."""
    engine = _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    cur = _published_version(shared_db, cv, version)
    if cur is None or not cur.store_path:
        raise HTTPException(
            status_code=400, detail=_("No published version %s to diff") % version
        )
    prev = _prev_published(shared_db, cv, version)
    if prev is None or not prev.store_path:
        raise HTTPException(
            status_code=400,
            detail=_("No earlier published version to diff against"),
        )
    host_id = _resolve_cv_serving_host(cv, shared_db, tenant_db)[0]
    plan = engine.build_version_diff_plan(prev.store_path, cur.store_path)

    from backend.services.proplus_dispatch import (  # noqa: PLC0415
        enqueue_apply_plan,
        register_content_lifecycle_correlation,
    )

    msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=1800)
    register_content_lifecycle_correlation(msg_id, "cv_diff", str(host_id), str(cur.id))
    return {
        "status": "computing",
        "from_version": prev.version,
        "to_version": version,
    }


@router.get(
    "/content-lifecycle/content-views/{cv_id}/versions/{version}/diff",
    dependencies=[Depends(JWTBearer())],
)
async def get_version_diff(
    cv_id: str,
    version: int,
    shared_db: Session = Depends(get_shared_db),
):
    """The stored diff for ``version`` (``{added, removed, from_version, at}``),
    or ``{"status": "none"}`` if not computed yet."""
    _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    cur = _published_version(shared_db, cv, version)
    if cur is None:
        raise HTTPException(
            status_code=404, detail=_("No published version %s") % version
        )
    diff = (cur.manifest or {}).get("diff_from_prev")
    return diff if diff else {"status": "none"}
