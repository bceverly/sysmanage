# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Operator-requested active sweeps (Phase 21.6 S4).

Listening cannot find a device that never speaks (21.6 S0); a sweep can -- by
sending one datagram to every address of an on-link network and reading what
the kernel's own ARP resolution learned. It is also the only discovery method
that puts traffic on a network, so it is gated three times over:

  1. the tenant policy must allow sweeps (a separate opt-in from listening);
  2. the requester needs Manage Network Discovery (checked by the API);
  3. the licensed engine validates the range -- IPv4, ON-LINK for an agent
     that will run it, bounded in size and rate -- and the agent re-checks
     on-link itself before sending anything.

Every run is a ``NetworkSweepRun`` row -- refused, failed and timed-out ones
too -- so "who put traffic on this network, and when" stays answerable.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.i18n import _
from backend.persistence.models import (
    Host,
    NetworkDiscoveryObserver,
    NetworkSweepRun,
)
from backend.persistence.models.asset_discovery import (
    SWEEP_COMPLETED,
    SWEEP_QUEUED,
    SWEEP_TIMED_OUT,
)
from backend.services import asset_discovery_shim as shim
from backend.services import network_discovery_policy as policy_svc
from backend.services.agent_capability_service import host_supports

logger = logging.getLogger(__name__)

COMMAND = "run_network_sweep"
# A run the agent never answered: it went offline, or the command was lost.
RUN_TIMEOUT = timedelta(hours=1)
# A network swept this recently no longer carries the "silent devices are
# unseen" blind spot.
SWEEP_FRESHNESS = timedelta(days=7)


class SweepError(ValueError):
    """A refused sweep request: a machine code and a translated message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_MESSAGES = {
    "invalid_network": lambda: _("That is not a valid network"),
    "ipv6_not_supported": lambda: _(
        "IPv6 networks cannot be swept; only IPv4 networks can be enumerated"
    ),
    "too_large": lambda: _(
        "That network is too large to sweep (at most 4096 addresses)"
    ),
    "not_on_link": lambda: _(
        "No agent is on that network, so it cannot be swept from here"
    ),
    "bad_rate": lambda: _("The rate must be between 1 and 200 addresses per second"),
}


def _candidates(db) -> List[Dict[str, Any]]:
    """Capable agents with the networks they reported, and whether busy."""
    busy = {
        row.agent_host_id
        for row in db.query(NetworkSweepRun.agent_host_id).filter(
            NetworkSweepRun.status == SWEEP_QUEUED
        )
    }
    out = []
    for observer, host in db.query(NetworkDiscoveryObserver, Host).join(
        Host, Host.id == NetworkDiscoveryObserver.host_id
    ):
        if not host.active or host_supports(host, COMMAND) is not True:
            continue
        out.append(
            {
                "host_id": str(host.id),
                "networks": [n["network"] for n in observer.networks or []],
                "last_report_at": observer.last_report_at.isoformat(),
                "busy": host.id in busy,
            }
        )
    return out


def _enqueue(db, host_id: str, parameters: Dict[str, Any]) -> str:
    """One id for the envelope and the queue row (the agent echoes it back)."""
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
        data={"command_type": CommandType.RUN_NETWORK_SWEEP, "parameters": parameters},
    )
    QueueOperations().enqueue_message(
        message_type="command",
        message_id=command_id,
        message_data=command.to_dict(),
        direction=QueueDirection.OUTBOUND,
        host_id=host_id,
        db=db,
    )
    return command_id


def request_sweep(db, cidr: str, rate: Optional[int], actor: str) -> Dict[str, Any]:
    """Queue one sweep, or raise ``SweepError``. Never commits."""
    engine = shim.engine()
    if engine is None:
        raise SweepError("engine_unavailable", _("Network discovery is not available"))
    policy = policy_svc.get_policy(db)
    if not (policy["enabled"] and policy["sweep_enabled"]):
        raise SweepError(
            "sweeps_disabled",
            _("Active sweeps are turned off in the network discovery settings"),
        )
    candidates = _candidates(db)
    known = [n for c in candidates for n in c["networks"]]
    verdict = engine.validate_sweep(cidr, rate, known)
    if verdict["errors"]:
        code = verdict["errors"][0]
        raise SweepError(code, _MESSAGES.get(code, lambda: code)())
    host_id = engine.choose_sweeper(verdict["cidr"], candidates)
    if host_id is None:
        raise SweepError(
            "busy",
            _("Every agent on that network is already sweeping; try again shortly"),
        )
    run = NetworkSweepRun(
        cidr=verdict["cidr"],
        rate=verdict["rate"],
        addresses=verdict["addresses"],
        status=SWEEP_QUEUED,
        requested_by=actor,
        requested_at=_utcnow(),
        agent_host_id=uuid.UUID(host_id),
    )
    db.add(run)
    db.flush()
    run.command_id = _enqueue(
        db, host_id, {"run_id": str(run.id), "cidr": run.cidr, "rate": run.rate}
    )
    db.flush()
    return run.to_dict()


def record_result(db, observer_id, sweep: Dict[str, Any], devices_found: int) -> bool:
    """Close the run a sweep report answers. Only the agent that was asked
    may close it; anything else is logged and ignored."""
    try:
        run_id = uuid.UUID(sweep["run_id"])
    except ValueError:
        return False
    run = db.query(NetworkSweepRun).filter(NetworkSweepRun.id == run_id).first()
    if run is None or run.agent_host_id != observer_id or run.status != SWEEP_QUEUED:
        logger.warning(
            "sweep result for run %s from host %s ignored: no such queued run for it",
            run_id,
            observer_id,
        )
        return False
    run.status = sweep["status"]
    run.reason = sweep["reason"]
    run.probed = sweep["probed"]
    run.devices_found = devices_found if sweep["status"] == SWEEP_COMPLETED else 0
    run.finished_at = _utcnow()
    db.flush()
    return True


def expire_stale(db, now: Optional[datetime] = None) -> int:
    """Mark runs no agent answered within ``RUN_TIMEOUT`` as timed out."""
    cutoff = (now or _utcnow()) - RUN_TIMEOUT
    stale = (
        db.query(NetworkSweepRun)
        .filter(
            NetworkSweepRun.status == SWEEP_QUEUED,
            NetworkSweepRun.requested_at < cutoff,
        )
        .all()
    )
    for run in stale:
        run.status = SWEEP_TIMED_OUT
        run.finished_at = now or _utcnow()
    return len(stale)


def list_runs(db, limit: int = 50) -> List[Dict[str, Any]]:
    """Newest first, every outcome included, with the sweeping host's name."""
    rows = (
        db.query(NetworkSweepRun, Host.fqdn)
        .outerjoin(Host, Host.id == NetworkSweepRun.agent_host_id)
        .order_by(NetworkSweepRun.requested_at.desc())
        .limit(max(1, min(int(limit), 500)))
        .all()
    )
    return [dict(run.to_dict(), agent_fqdn=fqdn) for run, fqdn in rows]


def recently_swept(db, now: Optional[datetime] = None) -> Dict[str, str]:
    """``{cidr: finished_at}`` for networks with a completed sweep in the last
    ``SWEEP_FRESHNESS``."""
    since = (now or _utcnow()) - SWEEP_FRESHNESS
    out: Dict[str, str] = {}
    for run in db.query(NetworkSweepRun).filter(
        NetworkSweepRun.status == SWEEP_COMPLETED,
        NetworkSweepRun.finished_at >= since,
    ):
        stamp = run.finished_at.isoformat()
        if run.cidr not in out or stamp > out[run.cidr]:
            out[run.cidr] = stamp
    return out
