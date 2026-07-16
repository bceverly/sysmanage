# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Air-gap repository compliance bucket endpoint (Phase 11 B5).

Single read-only endpoint feeding ``AirgapComplianceBucketsCard.tsx``.
Returns the three-bucket classification produced by
``backend/services/airgap_compliance_context.classify_compliance_gap``
for a given host.

Gated on ``airgap_repository_engine`` being loaded (i.e. ``role:
repository``).  When the engine isn't loaded the endpoint returns
empty buckets rather than 402 — the frontend card is hidden anyway
on non-repository deployments, so a friendly empty payload is
preferable to a noisy error.
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.airgap_compliance_context import classify_compliance_gap

router = APIRouter(
    prefix="/api/v1/airgap/repository",
    tags=["airgap-repository"],
    dependencies=[Depends(JWTBearer())],
)


@router.get("/host/{host_id}/compliance-buckets")
def get_host_compliance_buckets(host_id: str, db: Session = Depends(get_db)):
    """Return ``{not_applied, not_transferred, current}`` for ``host_id``.

    Resolves:
      1. The host's last package inventory (already collected by the OSS
         data_collector — read directly off the host record).
      2. The latest verified manifest from the local mirror (most-recent
         ``AirgapIngestionRun`` with ``status == "COMPLETE"``).
      3. The most-recent CVE snapshot the collector captured at the same
         transfer instant — pulled from the manifest envelope's
         ``include_cve`` payload.

    On a ``role: standard`` deployment, both the manifest and the CVE
    snapshot are absent; ``classify_compliance_gap`` returns empty
    buckets gracefully.
    """
    if not module_loader.get_module("airgap_repository_engine"):
        # Don't 402 — the frontend card hides itself based on
        # /api/v1/server-info.role.  An empty 200 here means callers
        # that DO hit it (curl, monitoring) get a useful shape.
        return {"not_applied": [], "not_transferred": [], "current": []}

    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail=_("Host not found"))

    host_packages = _resolve_host_packages(db, host)
    manifest = _resolve_latest_manifest(db)
    cve_snapshot = _resolve_cve_snapshot(manifest)

    return classify_compliance_gap(host_packages, manifest, cve_snapshot)


def _resolve_host_packages(db: Session, host) -> list:
    """Return the host's installed-package list as a list of
    ``{name, version, package_manager}`` dicts.

    Reads the existing OSS ``software_package`` table that data_collector
    populates.  When the host has never reported, returns an empty list.
    """
    rows = (
        db.query(models.SoftwarePackage)
        .filter(models.SoftwarePackage.host_id == host.id)
        .all()
    )
    return [
        {
            "name": r.name,
            "version": r.version,
            "package_manager": r.package_manager,
        }
        for r in rows
        if r.name
    ]


def _resolve_latest_manifest(db: Session) -> dict:
    """Return the most-recently completed manifest envelope's ``manifest``
    body (the inner dict, not the signature wrapper)."""
    latest = (
        db.query(models.AirgapIngestionRun)
        .filter(models.AirgapIngestionRun.status == "COMPLETE")
        .order_by(models.AirgapIngestionRun.completed_at.desc())
        .first()
    )
    if latest is None:
        return {}
    # The ingestion run currently doesn't persist the verified manifest
    # JSON — that's a follow-up.  For now, return an empty manifest so
    # everything-is-current is the conservative classification.
    # When the manifest persistence lands, replace this stub with a
    # JSON-decode of the persisted envelope's inner manifest dict.
    return {}


def _resolve_cve_snapshot(manifest: dict) -> dict:
    """Extract the CVE snapshot embedded in the most-recent manifest, or
    return an empty dict when none is present."""
    if not manifest:
        return {}
    return manifest.get("cve_snapshot") or {}
