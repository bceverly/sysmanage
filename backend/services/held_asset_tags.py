# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Asset tags held for machines that have not reported in yet (Phase 23.2 S5).

A CSV row whose UUID or serial matches no machine, or a tag given to a box
that 18.2's bare-metal discovery saw before it had an OS, is HELD.  The first
time a machine with that identity appears without a tag, the held tag is
applied and the hold deleted.

The identity rules here are the agent's (``collection/hardware_identity.py``):
a UUID and its byte-swapped form are one machine, and vendor placeholder
UUIDs and serials identify nothing.  They must stay in step with the agent --
a key computed differently here would never match the machine it was meant
for.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.persistence.models.machine import HELD_BY_SERIAL, HELD_BY_UUID
from backend.services.audit_service import ActionType, AuditService, EntityType

logger = logging.getLogger(__name__)

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_PLACEHOLDER_UUIDS = frozenset(
    {
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "03000200-0400-0500-0006-000700080009",
        "00020003-0004-0005-0006-000700080009",
    }
)
_PLACEHOLDER_SERIALS = frozenset(
    {
        "to be filled by o.e.m.",
        "to be filled by oem",
        "default string",
        "system serial number",
        "chassis serial number",
        "base board serial number",
        "not specified",
        "not applicable",
        "none",
        "n/a",
        "na",
        "0",
        "0123456789",
        "123456789",
        "serial",
        "oem",
    }
)

# Why an identifier cannot be used.
BAD_UUID = "bad_uuid"
PLACEHOLDER = "placeholder"


def _swap(uuid: str) -> str:
    """The same UUID with its first three fields byte-swapped."""

    def rev(hexstr: str) -> str:
        return "".join(hexstr[i : i + 2] for i in range(len(hexstr) - 2, -2, -2))

    return f"{rev(uuid[0:8])}-{rev(uuid[9:13])}-{rev(uuid[14:18])}{uuid[18:]}"


def uuid_key(raw: str) -> tuple[Optional[str], Optional[str]]:
    """``(match key, None)`` or ``(None, reason)`` for a UUID as typed."""
    text = (raw or "").strip().lower().strip("{}")
    if not _UUID.match(text):
        return None, BAD_UUID
    if text in _PLACEHOLDER_UUIDS or len(set(text.replace("-", ""))) == 1:
        return None, PLACEHOLDER
    return min(text, _swap(text)), None


def serial_key(raw: str) -> tuple[Optional[str], Optional[str]]:
    """``(serial, None)`` or ``(None, PLACEHOLDER)``; whitespace collapsed.
    Matching ignores case (a spreadsheet may have changed it)."""
    text = " ".join((raw or "").split())
    folded = text.lower()
    if not text or folded in _PLACEHOLDER_SERIALS or len(set(folded)) == 1:
        return None, PLACEHOLDER
    return text[:255], None


def _held_for(db: Session, machine: models.Machine) -> Optional[models.HeldAssetTag]:
    """The hold that names this machine: by UUID first, then by serial."""
    held = (
        db.query(models.HeldAssetTag)
        .filter(
            models.HeldAssetTag.kind == HELD_BY_UUID,
            models.HeldAssetTag.identifier == machine.match_key,
        )
        .first()
    )
    if held is None and machine.system_serial:
        held = (
            db.query(models.HeldAssetTag)
            .filter(
                models.HeldAssetTag.kind == HELD_BY_SERIAL,
                func.lower(models.HeldAssetTag.identifier)
                == machine.system_serial.lower(),
            )
            .first()
        )
    return held


def claim(db: Session, machine: Optional[models.Machine]) -> Optional[str]:
    """Apply a held tag to ``machine`` if it has none.  Returns the tag.

    The caller commits.  A held tag another machine has meanwhile been given
    stays held and is logged -- never a silent second owner."""
    if machine is None or machine.asset_tag:
        return None
    held = _held_for(db, machine)
    if held is None:
        return None
    taken = (
        db.query(models.Machine.id)
        .filter(
            func.lower(models.Machine.asset_tag) == held.asset_tag.lower(),
            models.Machine.id != machine.id,
        )
        .first()
    )
    if taken is not None:
        logger.warning(
            "Held asset tag %s not applied to machine %s: machine %s already has it",
            held.asset_tag,
            machine.id,
            taken[0],
        )
        return None
    machine.asset_tag = held.asset_tag
    machine.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.delete(held)
    AuditService.log(
        db=db,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=str(machine.id),
        entity_name=held.asset_tag,
        description=_("Held asset tag %s applied") % held.asset_tag,
        details={
            "machine_id": str(machine.id),
            "to": held.asset_tag,
            "held_by": held.kind,
            "held_since": held.created_at.isoformat() if held.created_at else None,
        },
        commit=False,
    )
    logger.info("Held asset tag %s applied to machine %s", held.asset_tag, machine.id)
    return held.asset_tag
