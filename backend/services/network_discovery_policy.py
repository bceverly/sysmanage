# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Turn agent network discovery on and off across a tenant (Phase 21.6 S2).

The operator sets ONE policy per tenant (off by default); this module makes
every capable agent match it. Reconciliation, not fire-and-forget: the policy
is desired state, ``NetworkDiscoveryDispatch`` records what each host was last
told, and a tick sends ``configure_network_discovery`` only where they differ.
That covers the cases a one-shot broadcast on save would miss -- a host
enrolled after the change, one that was offline when it was made, and one
whose agent was reinstalled and lost its saved setting.

WHO GETS THE COMMAND
--------------------
Only hosts that POSITIVELY advertise ``configure_network_discovery``. The
Phase 19 gate lets a host with unknown capabilities through (so older agents
keep working for everything else), but an older agent would answer this one
with "Unknown command type" -- noise in its history for a feature it cannot
have. So this checks ``host_supports(...) is True`` itself.

WHEN IT RESENDS
---------------
Whenever the policy differs from what was sent, and -- while enabled -- when
the agent re-advertised its capabilities AFTER we last told it: a restart or a
reinstall may have lost its saved setting. The agent treats the command as
idempotent, so a spare resend costs one small message.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from backend.licensing.module_loader import module_loader
from backend.persistence.models import (
    Host,
    NetworkDiscoveryDispatch,
    NetworkDiscoveryPolicy,
)
from backend.persistence.models.asset_discovery import (
    DEFAULT_REPORT_INTERVAL_SECONDS,
    DEFAULT_RETENTION_DAYS,
    MAX_REPORT_INTERVAL_SECONDS,
    MIN_REPORT_INTERVAL_SECONDS,
    RETENTION_CHOICES,
)
from backend.persistence.partitions import iter_host_databases
from backend.services.agent_capability_service import (
    UnsupportedCapabilityError,
    host_supports,
)
from backend.startup.leadership import singleton_task
from backend.startup.tick_runner import run_periodic

logger = logging.getLogger(__name__)

ENGINE = "asset_discovery_engine"
COMMAND = "configure_network_discovery"
TICK_INTERVAL_SECONDS = 60
ERROR_BACKOFF_SECONDS = 30
# One tick never floods the queue: a 10,000-host fleet turning discovery on
# converges over a few minutes instead of 10,000 commands in one pass.
MAX_DISPATCHES_PER_TICK = 200

_TASK: Optional[asyncio.Task] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clamp_interval(value: Any) -> int:
    """The agent enforces the same bounds; clamping here keeps them in step."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_REPORT_INTERVAL_SECONDS
    return max(MIN_REPORT_INTERVAL_SECONDS, min(MAX_REPORT_INTERVAL_SECONDS, seconds))


def _row(db) -> Optional[NetworkDiscoveryPolicy]:
    return db.query(NetworkDiscoveryPolicy).first()


def get_policy(db) -> Dict[str, Any]:
    """The tenant's policy; OFF when none was ever saved."""
    row = _row(db)
    if row is None:
        return {
            "enabled": False,
            "report_interval_seconds": DEFAULT_REPORT_INTERVAL_SECONDS,
            "sweep_enabled": False,
            "retention_days": DEFAULT_RETENTION_DAYS,
            "updated_by": None,
            "updated_at": None,
        }
    return {
        "enabled": bool(row.enabled),
        "report_interval_seconds": row.report_interval_seconds,
        "sweep_enabled": bool(row.sweep_enabled),
        "retention_days": row.retention_days or DEFAULT_RETENTION_DAYS,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def set_policy(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db,
    enabled: bool,
    interval: Any,
    actor: str,
    sweep_enabled: Optional[bool] = None,
    retention_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Save the policy; returns ``{"before", "after"}`` for the audit record.

    Never commits: the caller commits it together with its audit entry.
    """
    before = get_policy(db)
    row = _row(db)
    if row is None:
        row = NetworkDiscoveryPolicy()
        db.add(row)
    row.enabled = bool(enabled)
    row.report_interval_seconds = clamp_interval(interval)
    if sweep_enabled is not None:
        row.sweep_enabled = bool(sweep_enabled)
    elif row.sweep_enabled is None:
        row.sweep_enabled = False
    if retention_days is not None:
        if retention_days not in RETENTION_CHOICES:
            raise ValueError(f"retention_days must be one of {RETENTION_CHOICES}")
        row.retention_days = retention_days
    elif row.retention_days is None:
        row.retention_days = DEFAULT_RETENTION_DAYS
    row.updated_by = actor
    row.updated_at = _utcnow()
    db.flush()
    return {"before": before, "after": get_policy(db)}


# ---------------------------------------------------------------------------
# reconciliation
# ---------------------------------------------------------------------------


def needs_send(host, sent: Optional[NetworkDiscoveryDispatch], policy) -> bool:
    """Does this host have to be told (again)?"""
    if sent is None:
        # Never told: the agent's own default is OFF, so only "on" is news.
        return policy["enabled"]
    if (bool(sent.enabled), sent.report_interval_seconds) != (
        policy["enabled"],
        policy["report_interval_seconds"],
    ):
        return True
    readvertised = getattr(host, "agent_capabilities_updated_at", None)
    return bool(policy["enabled"] and readvertised and readvertised > sent.sent_at)


def _enqueue(db, host, policy) -> str:
    """Queue one command; ONE id for the envelope and the queue row (the
    agent echoes the envelope's id back as ``command_id``)."""
    # Imported here: the queue package pulls in the websocket stack, and this
    # module is imported by the tick, which must stay importable in a unit test.
    from backend.websocket.messages import (  # noqa: PLC0415
        CommandType,
        Message,
        MessageType,
    )
    from backend.websocket.queue_enums import QueueDirection  # noqa: PLC0415
    from backend.websocket.queue_operations import QueueOperations  # noqa: PLC0415

    command_id = str(uuid.uuid4())
    command = Message(
        message_id=command_id,
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.CONFIGURE_NETWORK_DISCOVERY,
            "parameters": {
                "enabled": policy["enabled"],
                "report_interval_seconds": policy["report_interval_seconds"],
            },
        },
    )
    QueueOperations().enqueue_message(
        message_type="command",
        message_id=command_id,
        message_data=command.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=str(host.id),
        db=db,
    )
    return command_id


def reconcile(db, summary: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """Bring every capable host in THIS database in line with the policy."""
    summary = summary if summary is not None else _empty_summary()
    policy = get_policy(db)
    sent = {row.host_id: row for row in db.query(NetworkDiscoveryDispatch)}
    hosts = (
        db.query(Host)
        .filter(Host.active.is_(True), Host.approval_status == "approved")
        .all()
    )
    now = _utcnow()
    for host in hosts:
        if host_supports(host, COMMAND) is not True:
            summary["not_equipped"] += 1
            continue
        row = sent.get(host.id)
        if not needs_send(host, row, policy):
            continue
        if summary["queued"] >= MAX_DISPATCHES_PER_TICK:
            summary["deferred"] += 1
            continue
        try:
            command_id = _enqueue(db, host, policy)
        except UnsupportedCapabilityError:
            summary["not_equipped"] += 1
            continue
        if row is None:
            row = NetworkDiscoveryDispatch(host_id=host.id)
            db.add(row)
        row.enabled = policy["enabled"]
        row.report_interval_seconds = policy["report_interval_seconds"]
        row.command_id = command_id
        row.sent_at = now
        summary["queued"] += 1
    db.flush()
    return summary


def _empty_summary() -> Dict[str, int]:
    return {"queued": 0, "not_equipped": 0, "deferred": 0}


def prune_devices(db, now: Optional[datetime] = None) -> int:
    """Forget devices unseen for the tenant's retention window (S5).

    Their exclusions are kept -- keyed by identity, they still apply if the
    device ever comes back. Returns how many devices were forgotten.
    """
    from backend.persistence.models import (  # noqa: PLC0415
        DiscoveredAsset,
        DiscoveredAssetSighting,
    )

    days = get_policy(db)["retention_days"]
    cutoff = (now or _utcnow()) - timedelta(days=days)
    ids = [
        row.id
        for row in db.query(DiscoveredAsset.id).filter(
            DiscoveredAsset.last_seen_at < cutoff
        )
    ]
    if not ids:
        return 0
    # Sightings explicitly: the FK cascades on PostgreSQL, but SQLite enforces
    # foreign keys only when asked, and orphans would inflate every count.
    db.query(DiscoveredAssetSighting).filter(
        DiscoveredAssetSighting.asset_id.in_(ids)
    ).delete(synchronize_session=False)
    db.query(DiscoveredAsset).filter(DiscoveredAsset.id.in_(ids)).delete(
        synchronize_session=False
    )
    return len(ids)


def _expire_sweeps(db, label) -> None:
    from backend.services import network_sweep  # noqa: PLC0415 - import cycle

    expired = network_sweep.expire_stale(db)
    if expired:
        logger.warning(
            "%d network sweep(s) in %s timed out without an answer from the agent",
            expired,
            label,
        )


def run_one_tick() -> Dict[str, int]:
    """Reconcile every host database once. Never raises."""
    summary = _empty_summary()
    if module_loader.get_module(ENGINE) is None:
        return summary
    # EVERY database: policies and hosts live in each tenant's own database,
    # so a tick reading only the bootstrap one would never reach a tenant.
    for label, _tenant, db in iter_host_databases():
        try:
            here = reconcile(db)
            _expire_sweeps(db, label)
            forgotten = prune_devices(db)
            if forgotten:
                logger.info(
                    "Network discovery (%s): forgot %d device(s) past retention",
                    label,
                    forgotten,
                )
            db.commit()
            if here["queued"] or here["deferred"]:
                # Named per database: a tenant-less total made "which tenant
                # did this go to?" unanswerable from the log (21.6 S3 test).
                logger.info("Network discovery reconcile (%s): %s", label, here)
            for key, value in here.items():
                summary[key] += value
        except Exception:  # pylint: disable=broad-except
            logger.exception("network discovery reconcile failed for %s", label)
            db.rollback()
        finally:
            db.close()
    return summary


async def network_discovery_tick_service() -> None:
    """Background service: one reconcile pass every ``TICK_INTERVAL_SECONDS``."""

    def _report(summary):
        if summary["queued"] or summary["deferred"]:
            logger.info("Network discovery reconcile: %s", summary)

    await run_periodic(
        "Network discovery tick",
        run_one_tick,
        TICK_INTERVAL_SECONDS,
        ERROR_BACKOFF_SECONDS,
        on_result=_report,
        logger=logger,
    )


def start_if_licensed():
    """Start the tick when the engine is loaded; the task or None. Never fatal."""
    global _TASK  # pylint: disable=global-statement
    if module_loader.get_module(ENGINE) is None:
        return None
    if _TASK is not None and not _TASK.done():
        return _TASK
    try:
        _TASK = singleton_task(network_discovery_tick_service())
        logger.info("Network discovery reconcile tick started")
        return _TASK
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Network discovery tick did not start: %s", exc)
        return None
