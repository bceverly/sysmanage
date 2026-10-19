# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The commands a maintenance window is holding, listed and cancelable.

A held command used to be invisible: the Ubuntu Pro Attach button said
"requested" and then nothing happened until the window opened, so it looked
broken (production, 2026-10-16).  The Maintenance Windows page lists every
held command in the tenant with what it is, when it was queued and which
window releases it; an administrator can cancel one.

What a command *is* is described from its payload, never shown raw: payloads
carry secrets (an Ubuntu Pro token) and whole files (a deployment plan's
config content).  ``describe`` keeps only a short, known-safe summary.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import maintenance_window_service as mw
from backend.websocket.queue_enums import QueueDirection, QueueStatus

# Any parameter whose NAME looks like this is never returned, at any depth.
_SECRET_KEY = re.compile(
    r"token|key|password|passwd|secret|credential|content|private|cert", re.I
)
_MAX_NAMES = 5
CANCELED_PREFIX = "canceled by "


def _names(items) -> Dict[str, Any]:
    """``{"names": first few, "count": n}`` for a list of names or rows."""
    names = []
    for item in items or []:
        if isinstance(item, dict):
            item = item.get("package_name") or item.get("name")
        if isinstance(item, str) and item:
            names.append(item)
    return {"names": names[:_MAX_NAMES], "count": len(names)}


def _scalars(params: Dict[str, Any]) -> Dict[str, Any]:
    """Short scalar parameters that are not secret-looking."""
    out = {}
    for key, value in params.items():
        if _SECRET_KEY.search(str(key)):
            continue
        if isinstance(value, (bool, int, float)) or (
            isinstance(value, str) and len(value) <= 80
        ):
            out[key] = value
    return out


def describe(message_data: Optional[str]) -> Dict[str, Any]:
    """``{"command_type", "details"}`` safe to show to an operator."""
    try:
        payload = json.loads(message_data or "{}")
    except (TypeError, ValueError):
        return {"command_type": None, "details": {}}
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    command_type = data.get("command_type")
    params = data.get("parameters")
    params = params if isinstance(params, dict) else {}
    details: Dict[str, Any] = {}
    if isinstance(params.get("packages"), list):
        details["packages"] = _names(params["packages"])
    plan = params.get("plan")
    if isinstance(plan, dict):
        details.update(
            _scalars({k: plan.get(k) for k in ("av_product", "distro", "platform")})
        )
        if isinstance(plan.get("packages"), list):
            details["packages"] = _names(plan["packages"])
    if isinstance(params.get("queries"), list):
        details["queries"] = len(params["queries"])
    details.update(
        {
            k: v
            for k, v in _scalars(params).items()
            if k not in details and k not in ("known_fingerprint",)
        }
    )
    return {"command_type": command_type, "details": details}


def held_ceiling() -> timedelta:
    """How long a held command may wait before it expires anyway (see
    ``queue_maintenance.expire_old_messages``)."""
    from backend.config.config import config  # noqa: PLC0415

    return timedelta(
        hours=config.get("message_queue", {}).get("held_max_age_hours", 168)
    )


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() if moment else None


def list_held(db: Session, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """Held commands in this database, newest first, with their release."""
    query = db.query(models.MessageQueue).filter(
        models.MessageQueue.direction == QueueDirection.OUTBOUND,
        models.MessageQueue.status == QueueStatus.PENDING,
        models.MessageQueue.error_message == mw.DEFERRED_MARKER,
    )
    total = query.count()
    rows = (
        query.order_by(models.MessageQueue.created_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    host_ids = {row.host_id for row in rows if row.host_id}
    fqdns = (
        dict(
            db.query(models.Host.id, models.Host.fqdn)
            .filter(models.Host.id.in_(host_ids))
            .all()
        )
        if host_ids
        else {}
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    release: Dict[Any, Dict[str, Any]] = {}
    for host_id in host_ids:
        status = mw.next_window_for_host(db, host_id, now)
        release[host_id] = {
            "state": status.get("state"),
            "blackout": status.get("active_blackout"),
            "window": status.get("next_window"),
        }
    ceiling = held_ceiling()
    items = []
    for row in rows:
        described = describe(row.message_data)
        items.append(
            {
                "id": str(row.id),
                "host_id": str(row.host_id) if row.host_id else None,
                "fqdn": fqdns.get(row.host_id),
                "command_type": described["command_type"],
                "details": described["details"],
                "queued_at": _iso(row.created_at),
                "rechecks_at": _iso(row.scheduled_at),
                "retry_count": row.retry_count,
                "max_retries": row.max_retries,
                "expires_at": (
                    _iso(row.created_at + ceiling) if row.created_at else None
                ),
                "release": release.get(row.host_id),
            }
        )
    return {"total": total, "items": items}


def cancel(db: Session, row_id, username: str) -> Optional[models.MessageQueue]:
    """Cancel one HELD command (the caller commits and audits).  None when
    the row does not exist or is not held -- a command already released,
    sent or finished is not this function's to stop."""
    row = (
        db.query(models.MessageQueue)
        .filter(
            models.MessageQueue.id == row_id,
            models.MessageQueue.direction == QueueDirection.OUTBOUND,
            models.MessageQueue.status == QueueStatus.PENDING,
            models.MessageQueue.error_message == mw.DEFERRED_MARKER,
        )
        .first()
    )
    if row is None:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row.status = QueueStatus.FAILED
    row.error_message = f"{CANCELED_PREFIX}{username}"[:2000]
    row.completed_at = now
    row.last_error_at = now
    row.scheduled_at = None
    return row
