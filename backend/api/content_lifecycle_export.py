# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content Lifecycle Management — air-gap media export API (Phase 16, Slice 7a).

Export a published content-view version to a signed, immutable ISO by reusing
the air-gap COLLECTOR engine's ISO builders (``build_iso_plan`` + the collector's
manifest signing).  The CVV's store is already a frozen, materialized tree on the
mirror host, so this is a single agent job: sign a manifest describing the
version server-side, then ``xorriso`` the store into an ISO with that manifest
embedded.  The air-gap REPOSITORY server ingests + serves the result unchanged.

Split out of ``backend.api.content_lifecycle`` (line-count cap); mounts its own
router and reuses that module's gate + lookup helpers.
"""

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.content_lifecycle import (
    _check_clm_module,
    _get_cv_or_404,
    _resolve_cv_serving_host,
)
from backend.auth.auth_bearer import JWTBearer, require_authenticated_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.models.content_lifecycle import (
    CVV_PUBLISHED,
    EXPORT_BUILDING_ISO,
    EXPORT_QUEUED,
)
from backend.persistence.partitions import get_shared_db, get_tenant_db

logger = logging.getLogger(__name__)

router = APIRouter()

_ISO_OUTPUT_DIR = "/var/lib/sysmanage/airgap-iso"


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _check_collector_module():
    """402 unless the air-gap collector engine (which builds/signs ISOs) loaded."""
    engine = module_loader.get_module("airgap_collector_engine")
    if engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Air-gap media export requires the air-gap collector engine "
                "(Enterprise). Please upgrade to access this feature."
            ),
        )
    return engine


def _iso_label(cv_name: str, version: int) -> str:
    """A filesystem/ISO-safe label like ``clm-rhel9-base-v3``."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (cv_name or "cv").strip().lower()).strip("-")
    return f"clm-{slug or 'cv'}-v{int(version)}"[:80]


def _published_version_or_400(shared_db, cv, version: int):
    cvv = (
        shared_db.query(models.SharedContentViewVersion)
        .filter(models.SharedContentViewVersion.content_view_id == cv.id)
        .filter(models.SharedContentViewVersion.version == version)
        .filter(models.SharedContentViewVersion.status == CVV_PUBLISHED)
        .first()
    )
    if cvv is None or not cvv.store_path:
        raise HTTPException(
            status_code=400,
            detail=_("No published version %s to export") % version,
        )
    return cvv


@router.post(
    "/content-lifecycle/content-views/{cv_id}/versions/{version}/export",
    dependencies=[Depends(JWTBearer())],
)
async def export_version_to_media(
    cv_id: str,
    version: int,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
    current_user=Depends(require_authenticated_user),
):
    """Build a signed air-gap ISO of a published content-view version and track
    the job.  Returns the export run at status ``BUILDING_ISO``; the result
    handler flips it to ``COMPLETE`` / ``FAILED`` when the mirror host finishes."""
    _check_clm_module()
    collector = _check_collector_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    cvv = _published_version_or_400(shared_db, cv, version)
    host_id = _resolve_cv_serving_host(cv, shared_db, tenant_db)[0]

    label = _iso_label(cv.name, version)
    run = models.ContentViewExportRun(
        content_view_id=cv.id,
        content_view_version_id=cvv.id,
        version=version,
        iso_label=label,
        status=EXPORT_QUEUED,
        created_by=current_user.id,
    )
    tenant_db.add(run)
    tenant_db.flush()  # assign run.id before dispatch/correlation

    manifest = {
        "format_version": 1,
        "iso_label": label,
        "kind": "content_view_version",
        "content_view_id": str(cv.id),
        "content_view": cv.name,
        "version": version,
    }
    from backend.services.airgap_run_tick import _sign_manifest_or_raw  # noqa: PLC0415

    signed = _sign_manifest_or_raw(collector, manifest)
    output_iso = f"{_ISO_OUTPUT_DIR}/cvexport-{run.id}.iso"
    plan = collector.build_iso_plan(
        staging_dir=cvv.store_path,
        output_iso=output_iso,
        manifest_dict=signed,
        iso_label=label,
    )
    # build_iso_plan writes into _ISO_OUTPUT_DIR but never creates it, and
    # xorriso won't -- prepend a mkdir (the collector tick does the same).
    if isinstance(plan, dict) and isinstance(plan.get("commands"), list):
        plan["commands"].insert(
            0,
            {
                "argv": ["sudo", "mkdir", "-p", _ISO_OUTPUT_DIR],
                "description": _("ensure ISO output dir exists"),
            },
        )

    from backend.services.proplus_dispatch import (  # noqa: PLC0415
        enqueue_apply_plan,
        register_content_lifecycle_correlation,
    )

    msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=7200)
    register_content_lifecycle_correlation(
        msg_id, "cv_export", str(host_id), str(run.id)
    )
    run.iso_path = output_iso
    run.worker_message_id = msg_id
    run.status = EXPORT_BUILDING_ISO
    run.started_at = _now_naive()
    tenant_db.commit()
    tenant_db.refresh(run)
    return run.to_dict()


@router.get(
    "/content-lifecycle/content-views/{cv_id}/exports",
    dependencies=[Depends(JWTBearer())],
)
async def list_exports(
    cv_id: str,
    shared_db: Session = Depends(get_shared_db),
    tenant_db: Session = Depends(get_tenant_db),
):
    """The air-gap export runs for a content view, newest first."""
    _check_clm_module()
    cv = _get_cv_or_404(shared_db, cv_id)
    rows = (
        tenant_db.query(models.ContentViewExportRun)
        .filter(models.ContentViewExportRun.content_view_id == cv.id)
        .order_by(models.ContentViewExportRun.created_at.desc())
        .limit(100)
        .all()
    )
    return [r.to_dict() for r in rows]
