# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Swap so a small host clears the antivirus memory floor (2026-11-21, Bryan).

ClamAV is deployed only where memory clears ``av_auto_deploy.MIN_MEMORY_MB``
(3,500 MB) -- a 2 GB host without swap went down under it in production on
2026-10-15.  Swap now counts toward the floor, and with ONE setting
("Add swap to hosts with too little memory for ClamAV", off until turned on) SysManage
gives such a host the swap it lacks, then deploys ClamAV:

1. The deploy -- automatic or the Deploy button -- finds the host short.
2. Instead of holding it, the server asks the agent for a swap file
   (``ensure_swap``) sized to the gap plus a margin, in whole GB, 1 to 8.
3. When the agent reports the swap made, the deploy plan is queued at once
   (no second request); the agent's hardware report then shows the swap.

A host is held, with the reason, where swap cannot be added: not Linux or a
BSD, an agent too old to add it, more than 8 GB needed, or the agent's own
refusal (no room, a filesystem that takes no swap file, a container) -- tried
again after ``SWAP_RETRY_HOURS``.  The swap made is recorded
(``antivirus_auto_deploy.swap_added_mb``), so removing antivirus can offer to
remove it.  The setting is the tenant's (each tenant's hosts are its own).
"""

import logging
import math
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.config import config, settings_service
from backend.persistence import models
from backend.persistence.tenant_context import get_active_tenant
from backend.services import agent_capability_service
from backend.websocket.messages import CommandType, Message, MessageType
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)

SETTING = "antivirus_add_swap"
COMMAND = "ensure_swap"
REMOVE_COMMAND = "remove_swap"
# Above the floor, so a reload's second copy has room (and rounded to GB).
MARGIN_MB = 512
MIN_SWAP_MB, MAX_SWAP_MB = 1024, 8192
PLATFORMS = ("Linux", "FreeBSD", "OpenBSD", "NetBSD")
STATUS_ADDING = "adding_swap"
STATUS_FAILED = "swap_failed"
SWAP_RETRY_HOURS = 24

_queue_ops = QueueOperations()


def _tenant(tenant_id: Optional[str] = None) -> Optional[str]:
    if tenant_id:
        return tenant_id
    return get_active_tenant() if config.is_multitenancy_enabled() else None


def enabled(tenant_id: Optional[str] = None) -> bool:
    """The setting (off until turned on, and off when it cannot be read)."""
    try:
        tenant = _tenant(tenant_id)
        if tenant:
            return settings_service.get_tenant_setting(tenant, SETTING) is True
        return settings_service.get_setting(SETTING) is True
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("The antivirus swap setting could not be read; treated as off")
        return False


def set_enabled(value: bool, tenant_id: Optional[str] = None) -> None:
    tenant = _tenant(tenant_id)
    if tenant:
        settings_service.set_tenant_setting(tenant, SETTING, bool(value))
    else:
        settings_service.set_setting(SETTING, bool(value))


def swap_needed_mb(host: Any, floor: Optional[int]) -> Optional[int]:
    """The swap file (MB, whole GB) that lifts memory plus swap over the
    floor with ``MARGIN_MB`` to spare; None when nothing is needed (or the
    host's memory is unknown)."""
    memory = getattr(host, "memory_total_mb", None)
    if not floor or memory is None:
        return None
    gap = floor + MARGIN_MB - (memory + (getattr(host, "swap_total_mb", None) or 0))
    if gap <= 0:
        return None
    return max(MIN_SWAP_MB, math.ceil(gap / 1024) * 1024)


def cannot_add(host: Any, size_mb: Optional[int]) -> Optional[str]:
    """Why SysManage cannot add the swap, or None when it can."""
    if host.platform not in PLATFORMS:
        return f"swap files are added only on Linux and the BSDs, not {host.platform}"
    if agent_capability_service.host_supports(host, COMMAND) is False:
        return "the agent is too old to add swap; upgrade it"
    if size_mb is None:
        return "its memory is not known yet"
    if size_mb > MAX_SWAP_MB:
        return f"it would need {size_mb} MB of swap, more than {MAX_SWAP_MB} MB"
    return None


def waiting(record: Any, now: datetime) -> Optional[str]:
    """Why the host waits on a swap already asked for, or None."""
    if record is None:
        return None
    if record.status == STATUS_ADDING:
        if record.requested_at > now - timedelta(hours=SWAP_RETRY_HOURS):
            return "adding_swap"
        return None  # no answer in a day: ask again
    if record.status == STATUS_FAILED and (
        record.finished_at or record.requested_at
    ) > now - timedelta(hours=SWAP_RETRY_HOURS):
        return "swap_failed"
    return None


def queue(session: Session, host: Any, package: str, size_mb: int, now: datetime):
    """Ask the agent for the swap file (the caller commits); returns the
    command id, also kept on the host's auto-deploy record."""
    command_id = str(uuid.uuid4())
    message = Message(
        message_id=command_id,
        message_type=MessageType.COMMAND,
        data={
            "command_type": CommandType.ENSURE_SWAP,
            "parameters": {"size_mb": int(size_mb)},
        },
    )
    _queue_ops.enqueue_message(
        message_type="command", message_id=command_id, message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND, host_id=str(host.id), db=session,
    )  # fmt: skip
    record = (
        session.query(models.AntivirusAutoDeploy)
        .filter(models.AntivirusAutoDeploy.host_id == host.id)
        .first()
    )
    if record is None:
        record = models.AntivirusAutoDeploy(host_id=host.id, attempts=0, plan_version=0)
        session.add(record)
    record.antivirus_package = package
    record.status = STATUS_ADDING
    record.command_id = command_id
    record.requested_at = now
    record.finished_at = None
    record.last_error = None
    logger.info("Antivirus: asked host %s for %d MB of swap before %s",
                host.id, size_mb, package)  # fmt: skip
    return command_id


def record_result(session: Session, message_data: Dict[str, Any], now: datetime):
    """An ``ensure_swap`` answer: the host's record, updated (success: the
    swap made; failure: held with the agent's reason), or None when it
    answers none of ours.  The caller deploys after a success and commits."""
    command_id = message_data.get("command_id")
    if not command_id:
        return None
    record = (
        session.query(models.AntivirusAutoDeploy)
        .filter(
            models.AntivirusAutoDeploy.command_id == str(command_id),
            models.AntivirusAutoDeploy.status == STATUS_ADDING,
        )
        .first()
    )
    if record is None:
        return None
    result = message_data.get("result")
    result = result if isinstance(result, dict) else {}
    record.finished_at = now
    if message_data.get("success") and result.get("success", True):
        record.swap_added_mb = result.get("size_mb") or record.swap_added_mb
        record.last_error = None
        return record
    record.status = STATUS_FAILED
    record.last_error = str(
        result.get("error")
        or message_data.get("error")
        or "the agent could not add swap"
    )[:2000]
    logger.warning("Antivirus: host %s could not add swap: %s",
                   record.host_id, record.last_error)  # fmt: skip
    return record


def queue_removal(session: Session, host: Any) -> str:
    """Ask the agent to remove the swap file SysManage added."""
    command_id = str(uuid.uuid4())
    message = Message(
        message_id=command_id,
        message_type=MessageType.COMMAND,
        data={"command_type": CommandType.REMOVE_SWAP, "parameters": {}},
    )
    _queue_ops.enqueue_message(
        message_type="command", message_id=command_id, message_data=message.to_dict(),
        direction=QueueDirection.OUTBOUND, host_id=str(host.id), db=session,
    )  # fmt: skip
    return command_id
