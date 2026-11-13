# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Package manager needs repair (2026-11-13).

Production, 2026-11-13: an update that stopped the agent mid-upgrade left
dpkg interrupted on eight hosts, and every update sent to them afterwards
failed with "dpkg was interrupted, you must manually run 'sudo dpkg
--configure -a'" while the hosts looked healthy.

The agent's update scan says whether its package manager can install
anything (agent collection/package_manager_health.py); :func:`store` keeps it
on the host.  The hosts grid flags such a host, "Repair package manager"
(:func:`start`) has its agent run the platform's standard repair, and the
alerting engine's ``package_manager_repair`` condition watches for it on any
platform.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import agent_capability_service as capabilities

logger = logging.getLogger(__name__)

GROUP = "package_manager_repair"
COMMAND = "repair_package_manager"
MANAGERS = ("dpkg", "dnf", "pkg")
REASON_MAX = 255

NOT_SUPPORTED = "agent_outdated"
NOT_NEEDED = "not_needed"
NOT_REPAIRABLE = "not_repairable"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def store(host: Optional[models.Host], health: Any) -> bool:
    """Keep what the agent reported; True when the flag changed.  An agent
    that reports nothing (an older one) leaves the host as it was."""
    if host is None or not isinstance(health, dict):
        return False
    manager = health.get("manager")
    manager = manager if manager in MANAGERS else None
    needs = bool(health.get("needs_repair")) and manager is not None
    reason = health.get("reason") if needs else None
    before = host.package_manager_needs_repair
    host.package_manager_name = manager
    host.package_manager_needs_repair = needs
    host.package_manager_repair_reason = (
        str(reason)[:REASON_MAX] if isinstance(reason, str) and reason else None
    )
    host.package_manager_repairable = (
        bool(health.get("repairable")) and manager is not None
    )
    host.package_manager_checked_at = _now()
    return bool(before) != needs


def store_for_host(db: Session, host_id: Any, health: Any) -> None:
    """:func:`store` for the host an update scan came from, committed."""
    if not isinstance(health, dict) or not host_id:
        return
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if store(host, health):
        logger.info("Package manager on %s: %s", host.fqdn,
                    "needs repair" if host.package_manager_needs_repair else "repaired")  # fmt: skip
    db.commit()


def blocker(host: models.Host) -> Optional[str]:
    """Why "Repair package manager" cannot run on this host, or None."""
    if not host.package_manager_needs_repair:
        return NOT_NEEDED
    if not host.package_manager_repairable:
        return NOT_REPAIRABLE
    report = capabilities.get_capability_report(host) or {}
    if GROUP not in (report.get("capabilities") or []):
        return NOT_SUPPORTED
    return None


def start(db: Session, host: models.Host) -> Tuple[Optional[str], Optional[str]]:
    """Queue the repair: ``(command_id, None)`` or ``(None, why not)``.  The
    caller commits.  The server sends nothing but the request."""
    # pylint: disable=import-outside-toplevel
    from backend.services.config_mgmt_dispatch import queue_command  # noqa: PLC0415
    from backend.websocket.messages import CommandType  # noqa: PLC0415

    why = blocker(host)
    if why:
        return None, why
    return queue_command(db, host.id, CommandType.REPAIR_PACKAGE_MANAGER, {}), None


def record_result(db: Session, host_id: Any, message_data: Dict[str, Any]) -> bool:
    """The agent's answer: keep the health it checked after the repair."""
    host = (
        db.query(models.Host).filter(models.Host.id == host_id).first()
        if host_id
        else None
    )
    result = message_data.get("result") if isinstance(message_data, dict) else None
    if host is None or not isinstance(result, dict):
        return False
    store(host, result.get("health"))
    logger.info(
        "Package manager repair on %s: %s%s",
        host.fqdn,
        "repaired" if result.get("success") else "not repaired",
        f" ({result.get('reason')})" if result.get("reason") else "",
    )
    return True
