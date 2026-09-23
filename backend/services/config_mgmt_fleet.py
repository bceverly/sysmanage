# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Inventories and fleet job persistence helpers (Phase 20.1).

Sits between HTTP and the Pro+ engine, exactly as
``config_mgmt_profile_service`` does for profiles, and for the same stated
reason: every RULE is asked of the engine and this module only resolves,
serializes and persists.

WHY RESOLUTION HAPPENS HERE AND THE POLICY HAPPENS THERE
--------------------------------------------------------
The engine says WHAT an inventory selects -- host ids, tag ids, site ids, or
everything -- and this module turns that into a query. The split is not
arbitrary tidiness: a licensed module holding a database session would make
the module a hard dependency of every query rather than of the rules, and an
unlicensed server could then not even read its own tables.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.persistence import models
from backend.persistence.models.config_fleet import (
    JOB_CANCELED,
    JOB_PENDING,
    TARGET_IN_FLIGHT,
    TARGET_PENDING,
)
from backend.services import config_mgmt_spec_shim as shim

logger = logging.getLogger(__name__)

# Returned when the engine is absent. The routers are gated on the module
# being loaded, so this is unreachable in practice; failing closed keeps it
# that way if the gate is ever relaxed.
_NO_ENGINE = "configuration management engine is not available"

# Fallbacks for the clamps when the engine is absent. Deliberately the
# conservative end of each range rather than the engine's default: if we are
# guessing, guess in the direction that cannot flood a queue.
_FALLBACK_CONCURRENCY = 1


def _engine():
    """The Pro+ module, or None when it is not loaded."""
    return shim.engine_module()


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """Stamp naive-UTC row values as UTC.

    Rows are stored naive; handing a naive datetime to a browser renders it as
    LOCAL time, which on a job list means a run that finished ten minutes ago
    can appear to finish in the future.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def now_naive() -> datetime:
    """The timestamp convention every row in this feature uses."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --- engine-owned rules ------------------------------------------------------


def validate_inventory(name: str, all_hosts: bool, member_count: int) -> Optional[str]:
    """Ask the engine whether an inventory is acceptable."""
    module = _engine()
    if module is None:
        return _NO_ENGINE
    return module.validate_inventory(name, all_hosts, member_count)


def validate_inventory_member(
    host_id: Optional[str], tag_id: Optional[str], site_id: Optional[str]
) -> Optional[str]:
    """Ask the engine whether an inventory member is acceptable."""
    module = _engine()
    if module is None:
        return _NO_ENGINE
    return module.validate_inventory_member(host_id, tag_id, site_id)


def validate_job_template(
    name: str,
    profile_id: Optional[str],
    inventory_id: Optional[str],
    schedule: Optional[str] = None,
) -> Optional[str]:
    """Ask the engine whether a job template is acceptable."""
    module = _engine()
    if module is None:
        return _NO_ENGINE
    return module.validate_job_template(name, profile_id, inventory_id, schedule)


def clamp_concurrency(value: Any) -> int:
    """The concurrency the engine will allow, or the safe floor without it."""
    module = _engine()
    if module is None:
        return _FALLBACK_CONCURRENCY
    return int(module.clamp_concurrency(value))


def clamp_timeout(value: Any) -> Optional[int]:
    """The per-target timeout the engine will allow."""
    module = _engine()
    if module is None:
        return None
    return module.clamp_timeout(value)


def next_batch_size(concurrency: int, in_flight: int, pending: int) -> int:
    """How many more targets a job may release right now.

    Without the engine the answer is zero, not "all of them": a server that
    has lost its license mid-job must stop dispatching rather than fall back
    to the unbounded behavior fleet jobs exist to replace.
    """
    module = _engine()
    if module is None:
        return 0
    return int(module.next_batch_size(concurrency, in_flight, pending))


def job_status_after(
    succeeded: int,
    failed: int,
    skipped: int,
    in_flight: int,
    pending: int,
    started=True,
) -> str:
    """The status a job should now carry."""
    module = _engine()
    if module is None:
        return JOB_PENDING
    return module.job_status_after(
        succeeded, failed, skipped, in_flight, pending, started
    )


def job_is_terminal(status: str) -> bool:
    """Whether a job has stopped moving.

    Falls back to a local comparison rather than to False: the runner uses
    this to decide whether to keep advancing a job, and answering "not
    terminal" without the engine would have it re-walk finished jobs forever.
    """
    module = _engine()
    if module is None:
        return status in ("completed", "failed", JOB_CANCELED)
    return bool(module.job_is_terminal(status))


# --- inventory resolution ----------------------------------------------------


def resolve_hosts(db_session: Session, inventory) -> List[Any]:
    """The active hosts an inventory currently selects.

    Resolved at launch, never stored. An inventory that named a tag and then
    copied out the matching hosts would be wrong the moment a host joined that
    tag -- and wrong silently, because a job that simply misses machines looks
    exactly like a job that succeeded.

    Inactive hosts are excluded, matching the assignment tick: queuing for one
    buries the work in a queue that may never drain while the operator sees it
    as dispatched.
    """
    module = _engine()
    if module is None:
        return []

    members = (
        db_session.query(models.ConfigInventoryMember)
        .filter(models.ConfigInventoryMember.inventory_id == inventory.id)
        .all()
    )
    selectors = module.inventory_selectors(inventory, members)

    query = db_session.query(models.Host).filter(models.Host.active.is_(True))
    if selectors.get("all_hosts"):
        return query.all()

    host_ids = selectors.get("host_ids") or []
    tag_ids = selectors.get("tag_ids") or []
    site_ids = selectors.get("site_ids") or []
    if not (host_ids or tag_ids or site_ids):
        return []

    clauses = []
    if host_ids:
        clauses.append(models.Host.id.in_(host_ids))
    if site_ids:
        clauses.append(models.Host.site_id.in_(site_ids))
    if tag_ids:
        # A subquery rather than a join: joining HostTag multiplies a host by
        # its matching tags, so a host carrying two of the selected tags would
        # become two targets and be dispatched to twice.
        tagged = (
            db_session.query(models.HostTag.host_id)
            .filter(models.HostTag.tag_id.in_(tag_ids))
            .subquery()
        )
        clauses.append(models.Host.id.in_(db_session.query(tagged.c.host_id)))

    return query.filter(or_(*clauses)).all()


def inventory_host_count(db_session: Session, inventory) -> int:
    """How many hosts an inventory selects right now.

    A count rather than a cached column: the number changes whenever a host is
    tagged, retired or added, and a stale "targets 412 hosts" on the launch
    screen is the kind of wrong that people only notice afterwards.
    """
    return len(resolve_hosts(db_session, inventory))


# --- serialization -----------------------------------------------------------


def inventory_to_dict(row, host_count: Optional[int] = None) -> Dict[str, Any]:
    """Serialise an inventory for the API."""
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "all_hosts": bool(row.all_hosts),
        "host_count": host_count,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": _utc(row.created_at),
        "updated_at": _utc(row.updated_at),
    }


def member_to_dict(row) -> Dict[str, Any]:
    """Serialise an inventory member for the API."""
    return {
        "id": str(row.id),
        "inventory_id": str(row.inventory_id),
        "host_id": str(row.host_id) if row.host_id else None,
        "tag_id": str(row.tag_id) if row.tag_id else None,
        "site_id": str(row.site_id) if row.site_id else None,
        "created_at": _utc(row.created_at),
    }


def template_to_dict(row) -> Dict[str, Any]:
    """Serialise a job template for the API."""
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "profile_id": str(row.profile_id),
        "inventory_id": str(row.inventory_id),
        "check_mode": bool(row.check_mode),
        "concurrency": row.concurrency,
        "timeout_seconds": row.timeout_seconds,
        "schedule": row.schedule,
        "enabled": bool(row.enabled),
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": _utc(row.created_at),
        "updated_at": _utc(row.updated_at),
        "last_launched_at": _utc(row.last_launched_at),
    }


def job_to_dict(row) -> Dict[str, Any]:
    """Serialise a job for the API.

    ``pending_count`` is derived rather than stored: it is the only counter
    that can be computed exactly from the others, and a fifth column to keep
    in step during dispatch is a fifth column to get wrong.
    """
    done = (
        (row.succeeded_count or 0) + (row.failed_count or 0) + (row.skipped_count or 0)
    )
    return {
        "id": str(row.id),
        "template_id": str(row.template_id) if row.template_id else None,
        "template_name": row.template_name,
        "profile_id": str(row.profile_id) if row.profile_id else None,
        "profile_name": row.profile_name,
        "inventory_name": row.inventory_name,
        "status": row.status,
        "check_mode": bool(row.check_mode),
        "concurrency": row.concurrency,
        "total_targets": row.total_targets or 0,
        "succeeded_count": row.succeeded_count or 0,
        "failed_count": row.failed_count or 0,
        "skipped_count": row.skipped_count or 0,
        "outstanding_count": max(0, (row.total_targets or 0) - done),
        "requested_by": row.requested_by,
        "detail": row.detail,
        "created_at": _utc(row.created_at),
        "started_at": _utc(row.started_at),
        "finished_at": _utc(row.finished_at),
    }


def target_to_dict(row) -> Dict[str, Any]:
    """Serialise one host within a job."""
    return {
        "id": str(row.id),
        "job_id": str(row.job_id),
        "host_id": str(row.host_id) if row.host_id else None,
        "host_fqdn": row.host_fqdn,
        "status": row.status,
        "command_id": row.command_id,
        "run_id": str(row.run_id) if row.run_id else None,
        "detail": row.detail,
        "queued_at": _utc(row.queued_at),
        "finished_at": _utc(row.finished_at),
    }


# --- counters ----------------------------------------------------------------


def target_counts(db_session: Session, job_id) -> Dict[str, int]:
    """Live pending / in-flight counts for one job.

    Queried rather than taken from the job row because these two are the ones
    the release decision depends on, and a stale answer here either stalls a
    job or lets it exceed its own concurrency.
    """
    rows = (
        db_session.query(models.ConfigJobTarget.status)
        .filter(models.ConfigJobTarget.job_id == job_id)
        .all()
    )
    statuses = [r[0] for r in rows]
    return {
        "pending": sum(1 for s in statuses if s == TARGET_PENDING),
        "in_flight": sum(1 for s in statuses if s in TARGET_IN_FLIGHT),
    }
