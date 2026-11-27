# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Old kernels and unneeded packages, removed safely (ROADMAP 27.8).

The server decides what a host must keep (``kernel_boots.protected``, from
the boot history only it holds) and sends it with the command; the agent
plans with ``apt-get -s``, never removes a protected kernel, and removes
exactly an approved list.  ``plan`` shows what would go; ``apply`` removes
the approved names -- from an operator's review, or, after an automatic
update run, the agent's own fresh plan (``approve_plan``), still under the
same protections.

Every request and result is a ``package_cleanup_run``; the agent's
``package_cleanup_result`` closes the run it names, for its own host only.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import kernel_boots
from backend.services.agent_capability_service import host_supports
from backend.websocket.messages import create_command_message
from backend.websocket.queue_enums import QueueDirection
from backend.websocket.queue_operations import QueueOperations

logger = logging.getLogger(__name__)
queue_ops = QueueOperations()

COMMAND = "package_cleanup"
STATUSES = ("planned", "done", "refused", "failed", "unsupported", "boot_path_broken")
_IMAGE = re.compile(r"^linux-image-(?:unsigned-)?(\d+\.\d+\.\d+-\d+.*)$")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def installed_kernels(db: Session, host) -> List[str]:
    """Every kernel release installed on the host: the agent's own list when
    it sends one, else from its ``linux-image-<release>`` packages."""
    details = host.os_details
    if isinstance(details, str):
        import json  # pylint: disable=import-outside-toplevel

        try:
            details = json.loads(details)
        except ValueError:
            details = None
    if isinstance(details, dict) and isinstance(details.get("installed_kernels"), list):
        return [str(k) for k in details["installed_kernels"]]
    names = (
        db.query(models.SoftwarePackage.package_name)
        .filter(models.SoftwarePackage.host_id == host.id,
                models.SoftwarePackage.package_name.like("linux-image-%"))
        .all()
    )  # fmt: skip
    found = []
    for (name,) in names:
        match = _IMAGE.match(name or "")
        if match:
            found.append(match.group(1))
    return found


def request(
    db: Session, host, mode: str, who: Optional[str], trigger: str = "manual",
    approved: Optional[List[str]] = None, approve_plan: bool = False,
) -> models.PackageCleanupRun:  # fmt: skip
    """Record a cleanup run and, unless refused, queue it to the agent.
    The caller commits."""
    now = _now()
    refusal, keep = kernel_boots.protected(db, host, installed_kernels(db, host))
    run = models.PackageCleanupRun(
        host_id=host.id, mode="apply" if mode == "apply" else "plan",
        trigger=trigger, requested_by=who, protected=keep,
        approved=list(approved or []) if mode == "apply" else None,
        created_at=now, status="queued",
    )  # fmt: skip
    db.add(run)
    db.flush()
    if refusal:
        run.status, run.error, run.completed_at = "refused", refusal, now
        return run
    if host_supports(host, COMMAND) is False:
        run.status, run.completed_at = "unsupported", now
        run.error = "agent_cannot_clean_up"
        return run
    params: Dict[str, Any] = {
        "run_id": str(run.id), "mode": run.mode,
        "protected_releases": [k["release"] for k in keep],
    }  # fmt: skip
    if run.mode == "apply":
        params["approved"] = run.approved or []
        params["approve_plan"] = bool(approve_plan)
    message = create_command_message(COMMAND, params)
    queue_ops.enqueue_message(
        message_type="command", message_data=message,
        direction=QueueDirection.OUTBOUND, host_id=str(host.id), db=db,
        correlation_id=str(run.id),
    )  # fmt: skip
    return run


def record_result(
    db: Session, host_id, data: Dict[str, Any]
) -> Optional[models.PackageCleanupRun]:
    """Close the run the agent names -- only a pending run of its own host."""
    run_id = data.get("run_id")
    if not run_id:
        return None
    run = (
        db.query(models.PackageCleanupRun)
        .filter(models.PackageCleanupRun.id == str(run_id),
                models.PackageCleanupRun.host_id == str(host_id))
        .first()
    )  # fmt: skip
    if run is None or run.status != "queued":
        return None
    status = str(data.get("status") or "failed")
    run.status = status if status in STATUSES else "failed"
    run.packages = _items(data.get("packages"))
    run.kept = _items(data.get("kept"))
    run.running_kernel = str(data.get("running_kernel") or "")[:128] or None
    run.error = str(data["error"])[:4000] if data.get("error") else None
    run.completed_at = _now()
    return run


def _items(value) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:5000]:
        if isinstance(item, dict) and item.get("name"):
            out.append({"name": str(item["name"])[:255],
                        "kernel": (str(item["kernel"])[:64] if item.get("kernel") else None),
                        "reason": str(item.get("reason") or "")[:32]})  # fmt: skip
    return out


def latest(db: Session, host_id, limit: int = 10) -> List[models.PackageCleanupRun]:
    runs = models.PackageCleanupRun
    return (
        db.query(runs).filter(runs.host_id == str(host_id))
        .order_by(runs.created_at.desc()).limit(limit).all()
    )  # fmt: skip


def to_dict(run: models.PackageCleanupRun) -> Dict[str, Any]:
    return {
        "id": str(run.id), "mode": run.mode, "status": run.status, "trigger": run.trigger,
        "requested_by": run.requested_by, "protected": run.protected or [],
        "approved": run.approved, "packages": run.packages or [], "kept": run.kept or [],
        "running_kernel": run.running_kernel, "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }  # fmt: skip
