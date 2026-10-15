# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
CSV import and export of asset tags (Phase 23.2 S5).

A file maps an identifier -- the SMBIOS system UUID and/or the system serial
-- to an asset tag.  ``plan`` decides what every row WOULD do and writes
nothing; ``apply`` re-plans against the database as it is now (never trusting
a preview the browser sends back) and writes only the rows that plan to.

Row outcomes:

* ``assign``       -- the machine gets this tag (``previous`` is what it had)
* ``unchanged``    -- it already has it
* ``hold``         -- no machine has reported this identity yet; the tag is
                      held and applied when one does (``previous`` is a tag
                      already held for it)
* ``fails_scheme`` -- the tag does not fit the naming scheme (``reason``)
* ``duplicate``    -- the tag belongs to another machine or hold, or the
                      file repeats a tag or a machine
* ``ambiguous``    -- the identifier matches more than one machine
* ``invalid``      -- the row names no usable identifier (``reason``)
* ``skipped``      -- the tag cell is blank; an import never CLEARS a tag

Swapping two machines' tags in one file reports a duplicate: each new tag is
still the other machine's when the row is checked.  Clear one first.

Export writes the same columns, plus vendor / model / hosts / status, so an
exported file re-imports unchanged.  Every cell that a spreadsheet would run
as a formula is escaped.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.persistence.models.machine import HELD_BY_SERIAL, HELD_BY_UUID
from backend.services import asset_tag_scheme as schemes
from backend.services import held_asset_tags as held
from backend.services.audit_service import ActionType, AuditService, EntityType

MAX_BYTES = 1_000_000
MAX_ROWS = 10_000

ASSIGN = "assign"
UNCHANGED = "unchanged"
HOLD = "hold"
FAILS_SCHEME = "fails_scheme"
DUPLICATE = "duplicate"
AMBIGUOUS = "ambiguous"
INVALID = "invalid"
SKIPPED = "skipped"

# Why a file, rather than a row, is refused.
FILE_TOO_LARGE = "file_too_large"
TOO_MANY_ROWS = "too_many_rows"
MISSING_COLUMNS = "missing_columns"
NOT_CSV = "not_csv"

# Header spellings accepted for each column (compared lowercase, with spaces
# and hyphens read as underscores).
_COLUMNS = {
    "asset_tag": ("asset_tag", "tag", "asset"),
    "system_uuid": ("system_uuid", "uuid", "smbios_uuid"),
    "system_serial": ("system_serial", "serial", "serial_number"),
}
EXPORT_COLUMNS = [
    "asset_tag",
    "system_uuid",
    "system_serial",
    "board_serial",
    "vendor",
    "model",
    "hosts",
    "status",
]
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class CsvError(ValueError):
    """The file as a whole cannot be read; ``code`` says why."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Row:
    line: int
    asset_tag: str
    system_uuid: str
    system_serial: str
    status: str = INVALID
    reason: Optional[str] = None
    machine_id: Optional[str] = None
    previous: Optional[str] = None
    hosts: List[str] = field(default_factory=list)
    # A bare-metal box 18.2 discovery saw with this serial (its MAC).
    discovered_mac: Optional[str] = None
    # Internal: what a hold would be keyed by.
    hold_key: Optional[Tuple[str, str]] = None

    def public(self) -> Dict[str, object]:
        data = asdict(self)
        data.pop("hold_key")
        return data


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def _header_name(raw: str) -> str:
    return raw.strip().lstrip("\ufeff").lower().replace(" ", "_").replace("-", "_")


def _unescape(cell: str) -> str:
    """Undo our own export escaping: a quote before a formula character."""
    if len(cell) > 1 and cell[0] == "'" and cell[1] in _FORMULA_START:
        return cell[1:]
    return cell


def _column_positions(header_row: List[str]) -> Dict[str, int]:
    """Each known column's index in the header row (first match wins)."""
    header = [_header_name(h) for h in header_row]
    where: Dict[str, int] = {}
    for column, names in _COLUMNS.items():
        for index, name in enumerate(header):
            if name in names:
                where[column] = index
                break
    return where


def read(text: str) -> List[Row]:
    """The file's data rows.  CsvError when the file itself is unusable."""
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise CsvError(FILE_TOO_LARGE)
    try:
        records = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    except csv.Error as exc:
        raise CsvError(NOT_CSV) from exc
    if not records:
        raise CsvError(MISSING_COLUMNS)
    where = _column_positions(records[0])
    if "asset_tag" not in where or not (
        "system_uuid" in where or "system_serial" in where
    ):
        raise CsvError(MISSING_COLUMNS)
    if len(records) - 1 > MAX_ROWS:
        raise CsvError(TOO_MANY_ROWS)

    def cell(record: List[str], column: str) -> str:
        index = where.get(column)
        if index is None or index >= len(record):
            return ""
        return _unescape(record[index].strip())

    return [
        Row(
            line=number,
            asset_tag=cell(record, "asset_tag"),
            system_uuid=cell(record, "system_uuid"),
            system_serial=cell(record, "system_serial"),
        )
        for number, record in enumerate(records[1:], start=2)
        if any(part.strip() for part in record)
    ]


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------


class _Index:
    """What a plan looks things up in, loaded once per file."""

    def __init__(self, db: Session):
        self.machines = db.query(models.Machine).all()
        self.by_key: Dict[str, List[models.Machine]] = {}
        self.by_serial: Dict[str, List[models.Machine]] = {}
        self.tag_owner: Dict[str, str] = {}
        for machine in self.machines:
            self.by_key.setdefault(machine.match_key, []).append(machine)
            if machine.system_serial:
                self.by_serial.setdefault(machine.system_serial.lower(), []).append(
                    machine
                )
            if machine.asset_tag:
                self.tag_owner[machine.asset_tag.lower()] = str(machine.id)
        self.holds: Dict[Tuple[str, str], models.HeldAssetTag] = {}
        self.held_tag_owner: Dict[str, Tuple[str, str]] = {}
        for hold in db.query(models.HeldAssetTag).all():
            key = (hold.kind, _hold_identifier(hold.kind, hold.identifier))
            self.holds[key] = hold
            self.held_tag_owner[hold.asset_tag.lower()] = key
        self.hosts: Dict[str, List[str]] = {}
        for machine_id, fqdn in (
            db.query(models.Host.machine_id, models.Host.fqdn)
            .filter(models.Host.machine_id.isnot(None))
            .order_by(models.Host.fqdn)
            .all()
        ):
            self.hosts.setdefault(str(machine_id), []).append(fqdn)
        self.discovered: Dict[str, str] = {}
        discovered_model = getattr(models, "DiscoveredHost", None)
        if discovered_model is not None:
            for serial, mac in (
                db.query(discovered_model.serial_number, discovered_model.mac_address)
                .filter(discovered_model.serial_number.isnot(None))
                .all()
            ):
                self.discovered.setdefault(serial.lower(), mac)


def _hold_identifier(kind: str, identifier: str) -> str:
    return identifier.lower() if kind == HELD_BY_SERIAL else identifier


def _candidates(
    row: Row, index: _Index
) -> Tuple[Optional[List[models.Machine]], Optional[Tuple[str, str]]]:
    """Machines the row's identifier names, and what a hold would key on.
    ``(None, None)`` with ``row.reason`` set when the identifier is unusable."""
    serial = None
    if row.system_serial:
        serial, reason = held.serial_key(row.system_serial)
        if reason and not row.system_uuid:
            row.reason = reason
            return None, None
    if row.system_uuid:
        key, reason = held.uuid_key(row.system_uuid)
        if reason:
            row.reason = reason
            return None, None
        found = index.by_key.get(key, [])
        if len(found) > 1 and serial:
            found = [
                m for m in found if (m.system_serial or "").lower() == serial.lower()
            ]
        return found, (HELD_BY_UUID, key)
    if serial is None:
        row.reason = "no_identifier"
        return None, None
    return index.by_serial.get(serial.lower(), []), (HELD_BY_SERIAL, serial.lower())


def _plan_row(
    row: Row,
    index: _Index,
    scheme: schemes.Scheme,
    seen_tags: Set[str],
    seen_targets: Set[str],
) -> None:
    if not row.asset_tag:
        row.status = SKIPPED  # e.g. an untagged machine in a re-imported export
        return
    found, hold_key = _candidates(row, index)
    if found is None:
        row.status = INVALID
        return
    if len(found) > 1:
        row.status = AMBIGUOUS
        return
    reason = schemes.check(scheme, row.asset_tag)
    if reason is not None:
        row.status, row.reason = FAILS_SCHEME, reason
        return
    tag = row.asset_tag.lower()
    machine = found[0] if found else None
    target = f"m:{machine.id}" if machine else f"h:{hold_key[0]}:{hold_key[1]}"
    if target in seen_targets:
        row.status, row.reason = DUPLICATE, "identifier_repeated"
        return
    if tag in seen_tags:
        row.status, row.reason = DUPLICATE, "duplicate_in_file"
        return
    seen_targets.add(target)
    seen_tags.add(tag)
    if machine is not None:
        _plan_machine(row, machine, index, tag)
    else:
        _plan_hold(row, hold_key, index, tag)


def _plan_machine(row: Row, machine: models.Machine, index: _Index, tag: str) -> None:
    row.machine_id = str(machine.id)
    row.previous = machine.asset_tag
    row.hosts = index.hosts.get(str(machine.id), [])
    owner = index.tag_owner.get(tag)
    if owner is not None and owner != str(machine.id):
        row.status, row.reason = DUPLICATE, "tag_in_use"
    elif tag in index.held_tag_owner:
        row.status, row.reason = DUPLICATE, "tag_held"
    elif (machine.asset_tag or "").lower() == tag:
        row.status = UNCHANGED
    else:
        row.status = ASSIGN


def _plan_hold(row: Row, hold_key: Tuple[str, str], index: _Index, tag: str) -> None:
    row.hold_key = hold_key
    existing = index.holds.get(hold_key)
    row.previous = existing.asset_tag if existing is not None else None
    if hold_key[0] == HELD_BY_SERIAL:
        row.discovered_mac = index.discovered.get(hold_key[1])
    if tag in index.tag_owner:
        row.status, row.reason = DUPLICATE, "tag_in_use"
    elif index.held_tag_owner.get(tag, hold_key) != hold_key:
        row.status, row.reason = DUPLICATE, "tag_held"
    elif existing is not None and existing.asset_tag.lower() == tag:
        row.status = UNCHANGED
    else:
        row.status = HOLD


def plan(db: Session, text: str, scheme: schemes.Scheme) -> List[Row]:
    """Every row's outcome.  Writes nothing."""
    rows = read(text)
    index = _Index(db)
    seen_tags: Set[str] = set()
    seen_targets: Set[str] = set()
    for row in rows:
        _plan_row(row, index, scheme, seen_tags, seen_targets)
    return rows


def summary(rows: Iterable[Row]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


# --------------------------------------------------------------------------
# applying
# --------------------------------------------------------------------------


def apply(
    db: Session, text: str, scheme: schemes.Scheme, user_id, username: str
) -> List[Row]:
    """Re-plan, then write the ``assign`` and ``hold`` rows.  The caller
    commits; every write is audited."""
    rows = plan(db, text, scheme)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in rows:
        if row.status == ASSIGN:
            machine = db.get(models.Machine, uuid.UUID(row.machine_id))
            machine.asset_tag = row.asset_tag
            machine.updated_at = now
            description = _("Asset tag set to %s") % row.asset_tag
            entity_id = row.machine_id
        elif row.status == HOLD:
            _write_hold(db, row, now, username)
            description = _("Asset tag %s held until the machine reports in") % (
                row.asset_tag
            )
            entity_id = None
        else:
            continue
        AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.HOST,
            entity_id=entity_id,
            entity_name=row.asset_tag,
            description=description,
            user_id=user_id,
            username=username,
            details={
                "source": "csv_import",
                "line": row.line,
                "machine_id": row.machine_id,
                "system_uuid": row.system_uuid or None,
                "system_serial": row.system_serial or None,
                "from": row.previous,
                "to": row.asset_tag,
            },
            commit=False,
        )
    return rows


def _write_hold(db: Session, row: Row, now: datetime, username: str) -> None:
    kind, key = row.hold_key
    existing = (
        db.query(models.HeldAssetTag)
        .filter(
            models.HeldAssetTag.kind == kind,
            func.lower(models.HeldAssetTag.identifier) == key,
        )
        .first()
    )
    if existing is None:
        identifier = row.system_serial.strip() if kind == HELD_BY_SERIAL else key
        existing = models.HeldAssetTag(
            kind=kind, identifier=" ".join(identifier.split())[:255]
        )
        db.add(existing)
    existing.asset_tag = row.asset_tag
    existing.created_at = now
    existing.created_by = username


# --------------------------------------------------------------------------
# exporting
# --------------------------------------------------------------------------


def _safe(value: Optional[str]) -> str:
    """A cell a spreadsheet will show, never run."""
    text = value or ""
    return "'" + text if text.startswith(_FORMULA_START) else text


def export(db: Session) -> str:
    """Every machine (tagged or not) and every held tag, one row each."""
    hosts: Dict[str, List[str]] = {}
    for machine_id, fqdn in (
        db.query(models.Host.machine_id, models.Host.fqdn)
        .filter(models.Host.machine_id.isnot(None))
        .order_by(models.Host.fqdn)
        .all()
    ):
        hosts.setdefault(str(machine_id), []).append(fqdn or "")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    machines = db.query(models.Machine).all()
    # Tagged machines first, by tag; untagged after them, by vendor.
    machines.sort(
        key=lambda m: (m.asset_tag is None, (m.asset_tag or "").lower(), m.vendor or "")
    )
    for m in machines:
        writer.writerow(
            [
                _safe(v)
                for v in (
                    m.asset_tag,
                    m.system_uuid,
                    m.system_serial,
                    m.board_serial,
                    m.vendor,
                    m.model,
                    "; ".join(hosts.get(str(m.id), [])),
                    "enrolled",
                )
            ]
        )
    for hold in db.query(models.HeldAssetTag).order_by(models.HeldAssetTag.asset_tag):
        by_uuid = hold.kind == HELD_BY_UUID
        writer.writerow(
            [
                _safe(hold.asset_tag),
                _safe(hold.identifier if by_uuid else ""),
                _safe("" if by_uuid else hold.identifier),
                "",
                "",
                "",
                "",
                "held",
            ]
        )
    return out.getvalue()
