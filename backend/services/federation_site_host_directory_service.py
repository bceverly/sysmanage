"""Federation site-side host-directory producer (Phase 12 actuation).

Builds the directory-tier snapshot of THIS site's hosts — just the columns the
coordinator's cross-site search needs (name, IP, OS, status, geo) — and
enqueues it for the outbound sync tick, mirroring
``federation_site_metadata_service``.  The coordinator upserts each entry into
its host-directory table via ``POST /sites/{id}/host-directory``, which then
backs the "Cross-Site Hosts" page.

Full-snapshot per tick (one ``host_directory`` payload, dedup'd so only one is
ever pending): fine for the fleet sizes a single site holds, and the
coordinator ingest is upsert-based so re-sending is idempotent.  Delta-only
shipping is a later scale optimization.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models.core import Host
from backend.services import (
    federation_coordinator_service as coord_svc,
    federation_sync_queue_service as sync_svc,
)

HOST_DIRECTORY_PAYLOAD_TYPE = "host_directory"
HOST_DIRECTORY_DEDUP_KEY = "host_directory:self"


def _host_to_entry(host: Host) -> Dict[str, Any]:
    """Map a local Host row to the coordinator's host-directory entry shape."""
    return {
        "host_id": str(host.id),
        "fqdn": host.fqdn,
        "ipv4": host.ipv4,
        "ipv6": host.ipv6,
        "public_ip": host.public_ip,
        # The local model carries a single ``platform`` (e.g. "Linux") plus
        # ``platform_release``; map them onto the coordinator's os_family /
        # os_version / platform trio.
        "os_family": host.platform,
        "os_version": host.platform_release,
        "platform": host.platform,
        "status": host.status,
        "geo_country_code": host.geo_country_code,
        "geo_subdivision_code": host.geo_subdivision_code,
        "geo_city": host.geo_city,
    }


def collect_host_directory(session: Session) -> List[Dict[str, Any]]:
    """Snapshot this site's active hosts as directory entries (pure read)."""
    rows = session.execute(select(Host).where(Host.active.is_(True))).scalars().all()
    return [_host_to_entry(h) for h in rows if h.fqdn]


def enqueue_host_directory(session: Session) -> Optional[Any]:
    """Collect the host directory and enqueue it for the next sync tick.

    No-op (returns ``None``) when the site isn't enrolled.  Otherwise returns
    the queued ``FederationSyncQueue`` row.  Caller commits.
    """
    if not coord_svc.is_enrolled(session):
        return None
    entries = collect_host_directory(session)
    return sync_svc.enqueue(
        session,
        payload_type=HOST_DIRECTORY_PAYLOAD_TYPE,
        payload={"entries": entries},
        dedup_key=HOST_DIRECTORY_DEDUP_KEY,
    )
