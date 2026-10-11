# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Linking hosts to the machine they run on (Phase 23.2 S2).

Every hardware report carries the agent's ``hardware_identity``.  This module
records it on the host and links the host to its ``Machine``:

* PHYSICAL hardware links automatically.  Several hosts on one physical
  machine is the case this exists for -- a multi-boot laptop, an OS reinstall.
* VIRTUAL hardware (QEMU, VMware, Hyper-V, ...) that collides with a machine
  another host is already on is held as a CONFLICT for an admin: that is
  usually a clone that kept its UUID, and merging it would put two real
  machines under one asset tag.
* Two hosts with the same UUID but DIFFERENT system serials are a conflict
  too -- a firmware vendor that duplicated UUIDs, never a silent merge.
* A container that reads its parent's hardware (same key as its parent host)
  is not linked: it is not another OS installed on the machine.
* No usable identity (unprivileged, placeholder, absent) creates nothing and
  keeps any existing link; the host's per-source status says why.

The identity groups hosts; it is never a credential (Phase 22.0).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import held_asset_tags

logger = logging.getLogger(__name__)

CONFLICT_VIRTUAL_CLONE = "virtual_clone"
CONFLICT_SERIAL_MISMATCH = "serial_mismatch"

DECISION_SAME = "same"
DECISION_DIFFERENT = "different"

# Vendor / model strings of virtual hardware.  Matched case-insensitively
# against "<vendor> <model>".
_VIRTUAL = re.compile(
    r"qemu|kvm|vmware|virtualbox|innotek|\bxen\b|bochs|bhyve|parallels"
    r"|virtual machine|hyper-v|amazon ec2|google compute engine|digitalocean"
    r"|openstack|hetzner vserver|linode",
    re.IGNORECASE,
)

_TEXT_FIELDS = ("system_uuid", "system_serial", "board_serial")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_virtual(vendor: Optional[str], model: Optional[str]) -> bool:
    """True when the reported hardware is a hypervisor's virtual machine."""
    return bool(_VIRTUAL.search(f"{vendor or ''} {model or ''}"))


def _clean(value: Any, limit: int) -> Optional[str]:
    """A reported string, trimmed and bounded; anything else is None."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] or None


def _serials_agree(machine: models.Machine, serial: Optional[str]) -> bool:
    """Missing on either side is not a disagreement; two values must match."""
    return not (machine.system_serial and serial) or machine.system_serial == serial


def _new_machine(identity: Dict[str, Any], key: str) -> models.Machine:
    now = _now()
    return models.Machine(
        match_key=key,
        system_uuid=identity.get("system_uuid"),
        system_serial=identity.get("system_serial"),
        board_serial=identity.get("board_serial"),
        vendor=identity.get("vendor"),
        model=identity.get("model"),
        is_virtual=is_virtual(identity.get("vendor"), identity.get("model")),
        created_at=now,
        updated_at=now,
    )


def _fill_gaps(machine: models.Machine, identity: Dict[str, Any]) -> None:
    """Complete what an earlier host could not read (e.g. it was unprivileged)."""
    changed = False
    for field in ("system_uuid", "system_serial", "board_serial", "vendor", "model"):
        if getattr(machine, field) is None and identity.get(field):
            setattr(machine, field, identity[field])
            changed = True
    if changed:
        machine.updated_at = _now()


def _link(host: models.Host, machine: models.Machine) -> None:
    host.machine_id = machine.id
    host.machine_conflict_id = None
    host.machine_conflict_reason = None


def _normalize(raw: Any) -> Optional[Dict[str, Any]]:
    """The agent's ``hardware_identity`` with every value bounded and typed."""
    if not isinstance(raw, dict):
        return None
    identity: Dict[str, Any] = {
        "system_uuid": _clean(raw.get("system_uuid"), 36),
        "system_serial": _clean(raw.get("system_serial"), 255),
        "board_serial": _clean(raw.get("board_serial"), 255),
        "vendor": _clean(raw.get("vendor"), 255),
        "model": _clean(raw.get("model"), 255),
        "match_key": _clean(raw.get("match_key"), 36),
    }
    if identity["system_uuid"]:
        identity["system_uuid"] = identity["system_uuid"].lower()
    if identity["match_key"]:
        identity["match_key"] = identity["match_key"].lower()
    status = raw.get("status")
    identity["status"] = (
        {k: str(v)[:16] for k, v in status.items() if k in _TEXT_FIELDS}
        if isinstance(status, dict)
        else {}
    )
    return identity


def record_identity(db: Session, host: models.Host, raw: Any) -> None:
    """Store ``host``'s reported identity and link it to its machine, then
    apply any asset tag held for that machine (S5).

    The caller commits.  Logged loudly when a link is held for an admin."""
    _record_identity(db, host, raw)
    if host.machine_id:
        held_asset_tags.claim(db, db.get(models.Machine, host.machine_id))


def _record_identity(db: Session, host: models.Host, raw: Any) -> None:
    identity = _normalize(raw)
    if identity is None:
        return
    host.hw_system_uuid = identity["system_uuid"]
    host.hw_system_serial = identity["system_serial"]
    host.hw_board_serial = identity["board_serial"]
    host.hw_match_key = identity["match_key"]
    host.hw_identity_status = json.dumps(identity["status"], sort_keys=True)
    host.hw_identity_updated_at = _now()

    key = identity["match_key"]
    if not key:
        return  # nothing usable this time; an existing link stands

    if host.parent_host_id:
        parent = db.get(models.Host, host.parent_host_id)
        if parent is not None and parent.hw_match_key == key:
            return  # a container reading its parent's hardware

    if host.machine_id:
        current = db.get(models.Machine, host.machine_id)
        if current is not None and current.match_key == key:
            _fill_gaps(current, identity)
            return

    candidates: List[models.Machine] = (
        db.query(models.Machine)
        .filter(models.Machine.match_key == key)
        .order_by(models.Machine.created_at)
        .all()
    )
    if not candidates:
        machine = _new_machine(identity, key)
        db.add(machine)
        db.flush()
        _link(host, machine)
        return

    agreeing = [m for m in candidates if _serials_agree(m, identity["system_serial"])]
    if not agreeing:
        _hold(host, candidates[0], CONFLICT_SERIAL_MISMATCH)
        return
    machine = agreeing[0]
    if machine.is_virtual and _other_hosts(db, machine, host):
        _hold(host, machine, CONFLICT_VIRTUAL_CLONE)
        return
    _fill_gaps(machine, identity)
    _link(host, machine)


def _other_hosts(db: Session, machine: models.Machine, host: models.Host) -> bool:
    return (
        db.query(models.Host.id)
        .filter(models.Host.machine_id == machine.id, models.Host.id != host.id)
        .first()
        is not None
    )


def _hold(host: models.Host, machine: models.Machine, reason: str) -> None:
    host.machine_conflict_id = machine.id
    host.machine_conflict_reason = reason
    logger.warning(
        "Machine link held for an admin: host %s (%s) reports the identity of "
        "machine %s (%s)",
        host.id,
        host.fqdn,
        machine.id,
        reason,
    )


def resolve_conflict(db: Session, host: models.Host, decision: str) -> models.Machine:
    """An admin's answer to a held link.  ``same``: the host IS on that machine.
    ``different``: it is another machine that happens to share the UUID (a
    clone) -- it gets its own record, and keeps it on later reports.  The
    caller commits and audits.  ValueError when nothing is held or the
    decision is unknown."""
    if not host.machine_conflict_id:
        raise ValueError("no conflict to resolve")
    collided = db.get(models.Machine, host.machine_conflict_id)
    if decision == DECISION_SAME and collided is not None:
        _link(host, collided)
        return collided
    if decision in (DECISION_SAME, DECISION_DIFFERENT):
        if not host.hw_match_key:
            raise ValueError("the host reported no identity to give a machine")
        identity = {
            "system_uuid": host.hw_system_uuid,
            "system_serial": host.hw_system_serial,
            "board_serial": host.hw_board_serial,
            "vendor": collided.vendor if collided is not None else None,
            "model": collided.model if collided is not None else None,
        }
        machine = _new_machine(identity, host.hw_match_key)
        db.add(machine)
        db.flush()
        _link(host, machine)
        held_asset_tags.claim(db, machine)
        return machine
    raise ValueError(f"unknown decision {decision!r}")
