"""Site metadata reporting (Phase 12.2).

A subordinate site periodically tells its coordinator who it is: what
SysManage version it runs, how many hosts it manages (and their OS
breakdown), which Pro+ engine modules it has loaded, and its own view of
its uplink health (online / degraded / offline — i.e. whether it is
currently operating in local autonomy mode).

Like every other upstream report in the federation design, this does NOT
call the coordinator directly — it ENQUEUES a ``site_metadata`` payload
onto ``federation_sync_queue`` and the outbound tick worker ships it on
the next cycle.  That keeps metadata reporting resilient to network
outages: a site that's been cut off still records fresh metadata locally
and replays it on reconnect.

The queue entry uses a fixed ``dedup_key`` so only the LATEST metadata is
ever pending — there's no value in shipping a backlog of stale snapshots,
the coordinator only wants the current picture.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.persistence.models.core import Host
from backend.services import (
    federation_coordinator_service as coord_svc,
    federation_sync_queue_service as sync_svc,
)

# Single pending metadata row at a time — re-collecting replaces it.
SITE_METADATA_PAYLOAD_TYPE = "site_metadata"
SITE_METADATA_DEDUP_KEY = "site_metadata:self"


def _resolve_version() -> str:
    """Best-effort SysManage version string; never raises."""
    try:
        # backend/__init__.py is generated at build time with __version__;
        # pylint can't see it statically, hence the disable.
        from backend import (  # type: ignore  # noqa: PLC0415  # pylint: disable=no-name-in-module
            __version__,
        )

        return str(__version__)
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"


def _loaded_capabilities() -> list:
    """Sorted list of loaded Pro+ engine module codes this site advertises.

    Best-effort — if the module loader can't be imported (e.g. in a unit
    test that doesn't stand up the licensing stack) we report an empty
    capability set rather than failing metadata collection.
    """
    try:
        from backend.licensing.module_loader import (  # noqa: PLC0415
            module_loader,
        )

        # ``loaded_modules`` is a @property returning a dict, not a method.
        return sorted(module_loader.loaded_modules.keys())
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _host_stats(session: Session) -> Dict[str, Any]:
    """Active-host count + per-platform breakdown for the metadata report."""
    host_count = (
        session.execute(
            select(func.count())  # pylint: disable=not-callable
            .select_from(Host)
            .where(Host.active.is_(True))
        ).scalar()
        or 0
    )
    rows = session.execute(
        select(Host.platform, func.count())  # pylint: disable=not-callable
        .select_from(Host)
        .where(Host.active.is_(True))
        .group_by(Host.platform)
    ).all()
    os_breakdown = {(platform or "unknown"): count for platform, count in rows}
    return {"host_count": int(host_count), "os_breakdown": os_breakdown}


def collect_site_metadata(session: Session) -> Dict[str, Any]:
    """Build the current site-metadata snapshot (does not enqueue).

    Pure read — safe to call from a health endpoint as well as the tick.
    """
    health = coord_svc.connection_health(session)
    stats = _host_stats(session)
    return {
        "sysmanage_version": _resolve_version(),
        "host_count": stats["host_count"],
        "os_breakdown": stats["os_breakdown"],
        "capabilities": _loaded_capabilities(),
        "connection_state": health["state"],
        "autonomous": health["autonomous"],
        "queue_depth": sync_svc.queue_depth(session),
    }


def enqueue_site_metadata(session: Session) -> Optional[Any]:
    """Collect the current metadata and enqueue it for the next sync tick.

    No-op (returns ``None``) when the site isn't enrolled — there's no
    coordinator to report to, so we don't grow the queue.  Otherwise
    returns the queued ``FederationSyncQueue`` row.  Caller commits.
    """
    if not coord_svc.is_enrolled(session):
        return None
    payload = collect_site_metadata(session)
    return sync_svc.enqueue(
        session,
        payload_type=SITE_METADATA_PAYLOAD_TYPE,
        payload=payload,
        dedup_key=SITE_METADATA_DEDUP_KEY,
    )
