# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Spot resynchronization of host clocks, released in waves (Phase 23.3 S5).

``request`` records one ``clock_resync`` row per host (one button, or every
host out of bounds at once).  ``release`` sends the next wave: never more than
``WAVE_SIZE`` in flight per database, paced by results rather than the clock,
so resyncing a thousand clocks does not hit one internal NTP pair all at once.
A sent resync with no result in ``SENT_TIMEOUT`` is ``timed_out`` -- the host
went away -- and frees its slot.

The agent steps the clock through the host's own time service and reports the
service's state afterwards (``record_result``).  On success the server forgets
its offset samples for that host: they measured a clock that no longer exists,
and the next heartbeats give the new figure within a minute.

The SERVER's own verified reference is sent along, so the host is pulled to
the clock it is judged against.  A server whose clock is off sends none: the
host falls back to its own configured source rather than to a wrong clock.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.persistence import models
from backend.services import clock_tracking, server_clock

logger = logging.getLogger(__name__)

WAVE_SIZE = 25
SENT_TIMEOUT = timedelta(minutes=10)
TICK_SECONDS = 10.0
ERROR_BACKOFF_SECONDS = 60.0

QUEUED = "queued"
SENT = "sent"
SUCCEEDED = "succeeded"
FAILED = "failed"
UNSUPPORTED = "unsupported"
TIMED_OUT = "timed_out"
ACTIVE = (QUEUED, SENT)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _finish(row, status: str, error: Optional[str] = None, now=None) -> None:
    row.status = status
    row.error = error
    row.finished_at = now or _now()


def _uuid(value) -> Any:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def request(
    db, hosts: Iterable, user: Optional[str], batch_id=None
) -> Tuple[List[Any], List[Any]]:
    """Queue a resync for each host.  Returns ``(queued_rows, skipped_hosts)``:
    a host with a resync already queued or in flight is skipped, not doubled.
    A host whose agent is not privileged is recorded as unsupported at once --
    stepping a clock needs root -- so the operator sees why, in the list."""
    hosts = list(hosts)
    busy = {
        str(host_id)
        for (host_id,) in db.query(models.ClockResync.host_id).filter(
            models.ClockResync.host_id.in_([h.id for h in hosts]),
            models.ClockResync.status.in_(ACTIVE),
        )
    }
    now = _now()
    rows, skipped = [], []
    for host in hosts:
        if str(host.id) in busy:
            skipped.append(host)
            continue
        row = models.ClockResync(
            id=uuid.uuid4(),
            host_id=host.id,
            batch_id=batch_id,
            status=QUEUED,
            requested_by=user,
            requested_at=now,
            offset_before_ms=host.clock_offset_ms,
        )
        if not host.is_agent_privileged:
            _finish(row, UNSUPPORTED, "not_privileged", now)
        db.add(row)
        rows.append(row)
    db.commit()
    return rows, skipped


def _reference() -> Optional[str]:
    status = server_clock.status()
    return status.get("reference") if status.get("verified") else None


def _dispatch(db, row, host, reference, now) -> None:
    # pylint: disable=import-outside-toplevel
    from backend.services.agent_capability_service import (  # noqa: PLC0415
        UnsupportedCapabilityError,
    )
    from backend.services.config_mgmt_dispatch import queue_command  # noqa: PLC0415
    from backend.websocket.messages import CommandType  # noqa: PLC0415

    try:
        row.command_id = queue_command(
            db, host.id, CommandType.RESYNC_CLOCK, {"server": reference}
        )
    except UnsupportedCapabilityError:
        _finish(row, UNSUPPORTED, "agent_too_old", now)
        return
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Clock resync: could not queue the command for host %s", host.id
        )
        _finish(row, FAILED, "dispatch_failed", now)
        return
    row.status, row.sent_at = SENT, now


def release(db, now: Optional[datetime] = None) -> Dict[str, int]:
    """Time out stale sends, then send the next wave.  Commits."""
    now = now or _now()
    summary = {"released": 0, "timed_out": 0, "failed": 0}
    for row in db.query(models.ClockResync).filter(
        models.ClockResync.status == SENT,
        models.ClockResync.sent_at < now - SENT_TIMEOUT,
    ):
        _finish(row, TIMED_OUT, "no_result", now)
        summary["timed_out"] += 1
    in_flight = (
        db.query(models.ClockResync).filter(models.ClockResync.status == SENT).count()
    )
    slots = WAVE_SIZE - in_flight
    if slots > 0:
        queued = (
            db.query(models.ClockResync)
            .filter(models.ClockResync.status == QUEUED)
            .order_by(models.ClockResync.requested_at)
            .limit(slots)
            .all()
        )
        reference = _reference() if queued else None
        for row in queued:
            host = db.get(models.Host, row.host_id)
            if host is None:
                _finish(row, FAILED, "host_gone", now)
                summary["failed"] += 1
                continue
            _dispatch(db, row, host, reference, now)
            summary["released" if row.status == SENT else "failed"] += 1
    db.commit()
    return summary


def _forget_samples(host_id) -> None:
    """Best effort, this worker's sockets only: a connection on another
    worker keeps its samples, and the step check drops any that span it."""
    # pylint: disable=import-outside-toplevel
    from backend.websocket.connection_manager import (  # noqa: PLC0415
        connection_manager,
    )

    for conn in getattr(connection_manager, "active_connections", {}).values():
        if str(getattr(conn, "host_id", "")) == str(host_id):
            clock_tracking.reset(conn)


def _apply_outcome(row, message_data: Dict[str, Any]) -> None:
    """Finish ``row`` as succeeded or failed per the agent's answer."""
    error = message_data.get("error")
    success = bool(message_data.get("success")) and not error
    if success:
        _finish(row, SUCCEEDED)
        return
    # A code from a current agent; an older one says "Unknown command".
    code = error if isinstance(error, str) and len(error) <= 32 else None
    _finish(row, FAILED, code or "agent_error")
    if code is None and error:
        row.detail = str(error)[:500]


def _apply_result_fields(row, result: Dict[str, Any]) -> None:
    """Copy the service, method and detail the agent reported onto ``row``."""
    row.service = (str(result.get("service"))[:16]) if result.get("service") else None
    row.method = (str(result.get("method"))[:64]) if result.get("method") else None
    if result.get("detail"):
        row.detail = str(result["detail"])[:500]


def _apply_status_after(db, row, after: Dict[str, Any]) -> None:
    """Record the time service's state after the step, on the host and row."""
    from backend.api.handlers.time_status_handlers import (  # noqa: PLC0415
        apply_claim,
    )

    host = db.get(models.Host, _uuid(row.host_id))
    if host is not None:
        apply_claim(host, after)
    offset = after.get("reported_offset_ms")
    if isinstance(offset, (int, float)) and not isinstance(offset, bool):
        row.reported_after_ms = float(offset)


def record_result(db, message_data: Dict[str, Any]) -> Optional[Any]:
    """Close the resync this result answers; None when it answers none."""
    command_id = message_data.get("command_id")
    if not command_id:
        return None
    row = (
        db.query(models.ClockResync)
        .filter(models.ClockResync.command_id == str(command_id))
        .first()
    )
    if row is None or row.status != SENT:
        return None
    result = message_data.get("result")
    result = result if isinstance(result, dict) else {}
    _apply_outcome(row, message_data)
    _apply_result_fields(row, result)
    after = result.get("status_after")
    if isinstance(after, dict):
        _apply_status_after(db, row, after)
    db.commit()
    if row.status == SUCCEEDED:
        _forget_samples(row.host_id)
    return row


def as_dict(row) -> Dict[str, Any]:
    def iso(value):
        return value.isoformat() if value else None

    return {
        "id": str(row.id),
        "host_id": str(row.host_id),
        "batch_id": str(row.batch_id) if row.batch_id else None,
        "status": row.status,
        "requested_by": row.requested_by,
        "requested_at": iso(row.requested_at),
        "sent_at": iso(row.sent_at),
        "finished_at": iso(row.finished_at),
        "offset_before_ms": row.offset_before_ms,
        "reported_after_ms": row.reported_after_ms,
        "service": row.service,
        "method": row.method,
        "error": row.error,
        "detail": row.detail,
    }


def run_one_tick() -> Dict[str, int]:
    """Release a wave in every host database.  Never raises."""
    from backend.persistence.partitions import (  # noqa: PLC0415
        iter_host_databases,
    )

    total = {"released": 0, "timed_out": 0, "failed": 0}
    for label, _tenant, db_session in iter_host_databases():
        try:
            for key, value in release(db_session).items():
                total[key] += value
        except Exception:  # pylint: disable=broad-exception-caught
            db_session.rollback()
            logger.exception("Clock resync tick failed for database %s", label)
        finally:
            db_session.close()
    return total


async def clock_resync_tick_service() -> None:
    """Background service: one wave every ``TICK_SECONDS``."""
    from backend.startup.tick_runner import run_periodic  # noqa: PLC0415

    def _report(summary):
        if any(summary.values()):
            logger.info(
                "Clock resync tick: released=%d timed_out=%d failed=%d",
                summary["released"],
                summary["timed_out"],
                summary["failed"],
            )

    await run_periodic(
        "Clock resync tick",
        run_one_tick,
        TICK_SECONDS,
        ERROR_BACKOFF_SECONDS,
        on_result=_report,
        logger=logger,
    )
