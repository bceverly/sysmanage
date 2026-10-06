# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Federation site-side host-directory producer (Phase 12 actuation).

Builds the directory-tier snapshot of THIS site's hosts -- just the columns the
coordinator's cross-site search needs (name, IP, OS, status, geo) -- and
enqueues it for the outbound sync tick, mirroring
``federation_site_metadata_service``.  The coordinator upserts each entry into
its host-directory table via ``POST /sites/{id}/host-directory``, which then
backs the "Cross-Site Hosts" page.

Deltas, not snapshots (Phase 22.5).  Every tick used to ship the whole
directory -- 6.4 MB at 20,000 hosts, every 5 minutes, per site -- and the
coordinator upserted every row each time.  Now a tick ships only the entries
that changed since the last one it queued (new hosts included), and the whole
directory once a day (``FULL_RESEND_AFTER``) and after a restart or a change
of leader, which this process cannot remember past -- that also repairs
anything a dead-lettered queue entry lost.  The coordinator's ingest is an
upsert and never deletes, so a partial batch is exactly what it expects.  One
``host_directory`` entry is pending at a time (dedup); a new delta MERGES
into a pending one instead of replacing it, or the older changes would be
lost.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models.core import Host
from backend.services import federation_coordinator_service as coord_svc
from backend.services import federation_sync_queue_service as sync_svc

HOST_DIRECTORY_PAYLOAD_TYPE = "host_directory"
HOST_DIRECTORY_DEDUP_KEY = "host_directory:self"
FULL_RESEND_AFTER = timedelta(hours=24)

# Per database (its engine URL): {host_id: digest} of what was last queued,
# and when the last full directory was queued.  Process memory on purpose:
# the sync worker is a singleton, and an empty memory just means one full
# directory -- the safe direction.
_SENT: Dict[str, Dict[str, str]] = {}
_FULL_AT: Dict[str, datetime] = {}


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


def _digest(entry: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(entry, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _database_key(session: Session) -> str:
    return str(session.get_bind().url)


def _pending_entries(session: Session) -> Dict[str, Dict[str, Any]]:
    """Entries of the host_directory payload still waiting to be sent."""
    # pylint: disable-next=import-outside-toplevel
    from backend.persistence.models.federation import FederationSyncQueue

    pending = session.execute(
        select(FederationSyncQueue).where(
            FederationSyncQueue.dedup_key == HOST_DIRECTORY_DEDUP_KEY
        )
    ).scalar_one_or_none()
    if pending is None:
        return {}
    try:
        entries = json.loads(pending.payload_json).get("entries") or []
    except (ValueError, AttributeError):
        return {}
    return {
        e["host_id"]: e for e in entries if isinstance(e, dict) and e.get("host_id")
    }


def enqueue_host_directory(
    session: Session, now: Optional[datetime] = None
) -> Optional[Any]:
    """Queue the directory entries that changed since the last tick (all of
    them when a full resend is due) for the next sync.

    Returns the queued ``FederationSyncQueue`` row, or ``None`` when the
    site is not enrolled or nothing changed.  Caller commits.
    """
    if not coord_svc.is_enrolled(session):
        return None
    now = now or datetime.now(timezone.utc)
    key = _database_key(session)
    entries = collect_host_directory(session)
    digests = {e["host_id"]: _digest(e) for e in entries}
    sent = _SENT.get(key)
    full = sent is None or now - _FULL_AT.get(key, now) >= FULL_RESEND_AFTER
    if full:
        changed = entries
    else:
        changed = [
            e for e in entries if sent.get(e["host_id"]) != digests[e["host_id"]]
        ]
    if not changed:
        return None
    merged = _pending_entries(session)
    merged.update({e["host_id"]: e for e in changed})
    row = sync_svc.enqueue(
        session,
        payload_type=HOST_DIRECTORY_PAYLOAD_TYPE,
        payload={"entries": list(merged.values())},
        dedup_key=HOST_DIRECTORY_DEDUP_KEY,
    )
    _SENT[key] = digests
    if full:
        _FULL_AT[key] = now
    return row
