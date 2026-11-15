# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Agent lost during its own upgrade (2026-11-15).

Production, 2026-11-15: an update sent from the Updates page included the
sysmanage-agent package.  The agent runs the package manager as its own
child; on five hosts the package's preinst stopped the agent's service, the
old unit killed the package manager with it, dpkg was left half-installed
and the agent never came back.  The server only showed "down", and "Repair
package manager" cannot help: it needs a live agent to run it.

Nothing new is recorded for this.  It is derived from what dispatch already
keeps: the ``update_execution_log`` rows the Updates page writes (kept
indefinitely) and the outbound ``apply_updates`` commands in the message
queue (every dispatch path, kept for a week after delivery).  A host is
"lost during its own upgrade" when:

* it is down;
* an update that included the agent's own package was sent while the host
  was alive (its last check-in is no older than the heartbeat timeout before
  the dispatch); and
* it has not been heard from since: its last check-in is no later than the
  heartbeat timeout after the dispatch.  An agent keeps sending heartbeats
  while the package manager downloads and unpacks, so the last one can land
  a little after the dispatch; one that came back keeps checking in, and is
  up, and so is never flagged.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config.config import get_heartbeat_timeout_minutes
from backend.persistence import models
from backend.websocket.queue_enums import QueueDirection, QueueStatus

logger = logging.getLogger(__name__)

# The names the agent's own package carries in an update list, per installer
# in sysmanage-agent/installer: deb/rpm/BSD/Alpine packages and the snap
# ("sysmanage-agent"), the strict snap, the Windows MSI's display name, the
# macOS pkg identifier and the Flatpak app id.  Compared case-insensitively.
AGENT_PACKAGE_NAMES = frozenset(
    {
        "sysmanage-agent",
        "sysmanage-agent-strict",
        "sysmanage agent",
        "com.sysmanage.agent",
        "org.sysmanage.agent",
    }
)

# A queued command reached the agent once it was sent.
_DELIVERED = (QueueStatus.SENT, QueueStatus.IN_PROGRESS, QueueStatus.COMPLETED)

# (dispatched_at, package_manager)
Dispatch = Tuple[datetime, Optional[str]]


def is_agent_package(name: Optional[str]) -> bool:
    """True when ``name`` is the agent's own package on some platform."""
    return isinstance(name, str) and name.strip().lower() in AGENT_PACKAGE_NAMES


def _naive(stamp: Optional[datetime]) -> Optional[datetime]:
    """Naive UTC, the way host.last_access is stored."""
    if stamp is not None and stamp.tzinfo is not None:
        return stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return stamp


def _logged_dispatches(session: Session, host_ids, since) -> Dict:
    """Agent-package rows the Updates page logged, per host."""
    rows = (
        session.query(
            models.UpdateExecutionLog.host_id,
            models.UpdateExecutionLog.package_name,
            models.UpdateExecutionLog.package_manager,
            models.UpdateExecutionLog.created_at,
        )
        .filter(models.UpdateExecutionLog.host_id.in_(host_ids))
        .filter(models.UpdateExecutionLog.created_at >= since)
        .filter(
            func.lower(models.UpdateExecutionLog.package_name).in_(AGENT_PACKAGE_NAMES)
        )
        .all()
    )
    found: Dict = {}
    for host_id, _name, manager, created_at in rows:
        found.setdefault(host_id, []).append((_naive(created_at), manager))
    return found


def _agent_package_manager(message_data: str) -> Tuple[bool, Optional[str]]:
    """Whether a queued command is an apply_updates including the agent's
    package, and that package's manager."""
    try:
        data = json.loads(message_data).get("data") or {}
    except (TypeError, ValueError, AttributeError):
        return False, None
    if not isinstance(data, dict) or data.get("command_type") != "apply_updates":
        return False, None
    packages = (data.get("parameters") or {}).get("packages") or []
    for package in packages:
        if isinstance(package, dict) and is_agent_package(package.get("package_name")):
            return True, package.get("package_manager")
    return False, None


def _queued_dispatches(session: Session, host_ids, since) -> Dict:
    """Delivered apply_updates commands that included the agent's package."""
    rows = (
        session.query(
            models.MessageQueue.host_id,
            models.MessageQueue.message_data,
            models.MessageQueue.created_at,
        )
        .filter(models.MessageQueue.host_id.in_(host_ids))
        .filter(models.MessageQueue.direction == QueueDirection.OUTBOUND)
        .filter(models.MessageQueue.message_type == "command")
        .filter(models.MessageQueue.status.in_(_DELIVERED))
        .filter(models.MessageQueue.created_at >= since)
        .filter(models.MessageQueue.message_data.like("%apply_updates%"))
        .all()
    )
    found: Dict = {}
    for host_id, message_data, created_at in rows:
        included, manager = _agent_package_manager(message_data)
        if included:
            found.setdefault(host_id, []).append((_naive(created_at), manager))
    return found


def _lost_to(host, dispatches, window: timedelta) -> Optional[Dispatch]:
    """The latest agent-package dispatch the host was alive for and never
    came back from.  One sent after it was already down (a retry) is not
    what took it down, and must not hide the one that did."""
    seen = _naive(host.last_access)
    alive_for = [d for d in dispatches if d[0] - window <= seen <= d[0] + window]
    return max(alive_for, key=lambda d: d[0]) if alive_for else None


def lost_hosts(session: Session, hosts: Iterable) -> Dict:
    """``{host.id: (dispatched_at, package_manager)}`` for each of ``hosts``
    lost during its own upgrade."""
    down = [h for h in hosts if h.status == "down" and h.last_access]
    if not down:
        return {}
    window = timedelta(minutes=get_heartbeat_timeout_minutes())
    since = min(_naive(h.last_access) for h in down) - window
    ids = [h.id for h in down]
    try:
        found = _logged_dispatches(session, ids, since)
        for host_id, sent in _queued_dispatches(session, ids, since).items():
            found.setdefault(host_id, []).extend(sent)
    except Exception as exc:  # noqa: BLE001  a host list must still load
        logger.warning("Agent self-update check failed: %s", exc)
        session.rollback()
        return {}
    lost = {h.id: _lost_to(h, found.get(h.id, []), window) for h in down}
    return {host_id: dispatch for host_id, dispatch in lost.items() if dispatch}


def fields(dispatch: Optional[Dispatch]) -> dict:
    """The host API's view of :func:`lost_hosts` for one host."""
    when, manager = dispatch if dispatch else (None, None)
    return {
        "agent_lost_in_self_update": dispatch is not None,
        "agent_self_update_dispatched_at": (
            when.replace(tzinfo=timezone.utc).isoformat() if when else None
        ),
        "agent_self_update_package_manager": manager,
    }
