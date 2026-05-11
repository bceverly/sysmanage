"""
Air-gap repository list + freshness endpoints (Phase 11 B6).

Feeds the ``AirgapRepositories.tsx`` dashboard component and the
``RepositoryFreshnessCard.tsx`` component.  Both endpoints share the
``role: repository`` gate convention used by ``airgap_repository_buckets``:
when the engine isn't loaded they return empty payloads instead of 402,
because the frontend already hides these surfaces on non-repository
deployments (`/api/v1/server-info.role`) and a friendly empty 200 is
nicer for curl / monitoring callers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.airgap_compliance_context import get_repository_freshness

router = APIRouter(
    prefix="/api/v1/airgap/repository",
    tags=["airgap-repository"],
    dependencies=[Depends(JWTBearer())],
)


@router.get("/repositories")
def list_repositories(db: Session = Depends(get_db)):
    """List every ``AirgapLocalRepository`` row with its per-repo
    package_count + freshness fields, plus a single aggregate header."""
    if not module_loader.get_module("airgap_repository_engine"):
        return {"repositories": [], "aggregate": _empty_aggregate()}

    rows = db.query(models.AirgapLocalRepository).all()
    repositories = [_serialize_repository(db, row) for row in rows]
    return {
        "repositories": repositories,
        "aggregate": _aggregate(repositories),
    }


@router.get("/freshness")
def get_freshness(db: Session = Depends(get_db)):
    """Return the global air-gap mirror freshness label.  Thin wrapper
    around ``get_repository_freshness`` so the frontend can call it
    without going through a service module."""
    return get_repository_freshness(db)


def _serialize_repository(db: Session, row) -> dict:
    ingest = None
    signer_fingerprint = None
    if row.last_ingest_run_id is not None:
        ingest = (
            db.query(models.AirgapIngestionRun)
            .filter(models.AirgapIngestionRun.id == row.last_ingest_run_id)
            .first()
        )
        if ingest is not None:
            signer_fingerprint = ingest.signer_fingerprint

    repo_engine = module_loader.get_module("airgap_repository_engine")
    days, label = (None, "never")
    if repo_engine is not None and row.last_ingest_at is not None:
        days, label = repo_engine.compute_freshness(row.last_ingest_at)

    return {
        "id": str(row.id),
        "distro": row.distro,
        "version": row.version,
        "repo_url": row.repo_url,
        "package_count": row.package_count,
        "last_ingest_at": (
            row.last_ingest_at.isoformat() if row.last_ingest_at else None
        ),
        "days_since_ingest": days,
        "freshness_label": label,
        "signer_fingerprint": signer_fingerprint,
    }


def _aggregate(repositories: list) -> dict:
    if not repositories:
        return _empty_aggregate()

    total_packages = sum(r["package_count"] or 0 for r in repositories)
    days_seen = [
        r["days_since_ingest"]
        for r in repositories
        if r["days_since_ingest"] is not None
    ]
    oldest = max(days_seen) if days_seen else None
    stale_count = sum(1 for d in days_seen if d is not None and d >= _STALE_DAYS)
    return {
        "total_repositories": len(repositories),
        "total_packages": total_packages,
        "oldest_days_since_ingest": oldest,
        "stale_repository_count": stale_count,
        "stale_threshold_days": _STALE_DAYS,
    }


def _empty_aggregate() -> dict:
    return {
        "total_repositories": 0,
        "total_packages": 0,
        "oldest_days_since_ingest": None,
        "stale_repository_count": 0,
        "stale_threshold_days": _STALE_DAYS,
    }


# Mirror of ``DEFAULT_STALE_DAYS`` in ``AirgapRepositories.tsx``.  Kept
# in sync manually; if you change one, change the other.
_STALE_DAYS = 7
