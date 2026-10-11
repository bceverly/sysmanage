# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Asset tag CSV import / export and held tags (Phase 23.2 S5).

The dry run must say exactly what apply will do, and apply must never write a
row the plan refused.  Held tags must land on the machine they name -- found
by either UUID byte order -- the first time it reports in, and nowhere else.
"""

import csv
import io
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import asset_tag_csv as tc
from backend.services import asset_tag_scheme as schemes
from backend.services import held_asset_tags as held
from backend.services import machine_identity as mi

# Scrambled identities.  T480 is in SMBIOS order; T480_SWAPPED is the same
# machine as OpenBSD prints it (first three fields byte-swapped).
T480 = "6956e14c-347a-11b2-a85c-0f1e2d3c4b5a"
T480_SWAPPED = "4ce15669-7a34-b211-a85c-0f1e2d3c4b5a"
X13S = "9f8e7d6c-5b4a-3928-1716-a5b4c3d2e1f0"
LOOSE = schemes.Scheme()
GDR = schemes.Scheme(prefix="GDR", separator="-", digits=6, enforce=True)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _machine(db, raw_uuid, serial=None, tag=None, fqdns=()):
    key, _ = held.uuid_key(raw_uuid)
    now = datetime.utcnow()
    machine = models.Machine(
        id=uuid.uuid4(),
        match_key=key,
        system_uuid=raw_uuid,
        system_serial=serial,
        vendor="LENOVO",
        model="20L6",
        asset_tag=tag,
        created_at=now,
        updated_at=now,
    )
    db.add(machine)
    for fqdn in fqdns:
        db.add(
            models.Host(
                id=uuid.uuid4(),
                fqdn=fqdn,
                active=True,
                approval_status="approved",
                machine_id=machine.id,
            )
        )
    db.commit()
    return machine


def _csv(*rows, header=("system_uuid", "system_serial", "asset_tag")):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def _by_line(rows):
    return {row.line: row for row in rows}


# --- identity keys ----------------------------------------------------------


def test_either_uuid_byte_order_is_one_key():
    assert held.uuid_key(T480)[0] == held.uuid_key(T480_SWAPPED)[0]
    assert held.uuid_key("{" + T480.upper() + "}")[0] == held.uuid_key(T480)[0]


@pytest.mark.parametrize(
    "raw,reason",
    [
        ("not-a-uuid", held.BAD_UUID),
        ("03000200-0400-0500-0006-000700080009", held.PLACEHOLDER),
        ("00000000-0000-0000-0000-000000000000", held.PLACEHOLDER),
    ],
)
def test_unusable_uuids_identify_nothing(raw, reason):
    assert held.uuid_key(raw) == (None, reason)


def test_placeholder_serials_identify_nothing():
    assert held.serial_key("To Be Filled By O.E.M.") == (None, held.PLACEHOLDER)
    assert held.serial_key("  PF9Z  Q7X1 ") == ("PF9Z Q7X1", None)


# --- reading ----------------------------------------------------------------


@pytest.mark.parametrize(
    "text,code",
    [
        ("asset_tag\nGDR-1\n", tc.MISSING_COLUMNS),
        ("system_uuid,serial\nx,y\n", tc.MISSING_COLUMNS),
        ("", tc.MISSING_COLUMNS),
        ("a" * (tc.MAX_BYTES + 1), tc.FILE_TOO_LARGE),
    ],
)
def test_an_unusable_file_is_refused_as_a_whole(text, code):
    with pytest.raises(tc.CsvError) as caught:
        tc.read(text)
    assert caught.value.code == code


def test_headers_are_forgiving_and_blank_lines_are_skipped():
    rows = tc.read("\ufeffSerial Number,Asset-Tag\nPF9ZQ7X1,GDR-000001\n,\n")
    assert len(rows) == 1
    assert (rows[0].system_serial, rows[0].asset_tag, rows[0].line) == (
        "PF9ZQ7X1",
        "GDR-000001",
        2,
    )


def test_too_many_rows_is_refused():
    text = "serial,asset_tag\n" + "s,t\n" * (tc.MAX_ROWS + 1)
    with pytest.raises(tc.CsvError) as caught:
        tc.read(text)
    assert caught.value.code == tc.TOO_MANY_ROWS


# --- planning ---------------------------------------------------------------


def test_the_dry_run_reports_every_outcome_and_writes_nothing(db):
    _machine(db, T480, serial="PF9ZQ7X1", fqdns=["ubuntu.t480", "openbsd.t480"])
    _machine(db, X13S, serial="R90X13S", tag="GDR-000002")
    _machine(db, "11111111-2222-3333-4444-555555555555", tag="GDR-000003")
    text = _csv(
        (T480_SWAPPED, "", "GDR-000001"),  # 2 assign, found by the swapped UUID
        ("", "R90X13S", "GDR-000002"),  # 3 unchanged, found by serial
        ("", "NEW-SERIAL-1", "GDR-000010"),  # 4 hold: nothing reported yet
        ("", "NEW-SERIAL-2", "GDR-1"),  # 5 fails the scheme
        ("", "NEW-SERIAL-3", "GDR-000003"),  # 6 another machine's tag
        ("", "NEW-SERIAL-4", "GDR-000010"),  # 7 tag repeated in the file
        ("bogus", "", "GDR-000011"),  # 8 unusable UUID
        ("", "", "GDR-000012"),  # 9 no identifier at all
    )
    rows = _by_line(tc.plan(db, text, GDR))
    assert rows[2].status == tc.ASSIGN
    assert rows[2].hosts == ["openbsd.t480", "ubuntu.t480"]
    assert rows[3].status == tc.UNCHANGED
    assert rows[4].status == tc.HOLD
    assert (rows[5].status, rows[5].reason) == (tc.FAILS_SCHEME, schemes.NO_MATCH)
    assert (rows[6].status, rows[6].reason) == (tc.DUPLICATE, "tag_in_use")
    assert (rows[7].status, rows[7].reason) == (tc.DUPLICATE, "duplicate_in_file")
    assert (rows[8].status, rows[8].reason) == (tc.INVALID, held.BAD_UUID)
    assert (rows[9].status, rows[9].reason) == (tc.INVALID, "no_identifier")
    assert db.query(models.HeldAssetTag).count() == 0
    assert db.query(models.Machine).filter_by(asset_tag="GDR-000001").count() == 0


def test_tags_are_unique_ignoring_case(db):
    _machine(db, X13S, tag="GDR-000002")
    rows = tc.plan(db, _csv(("", "NEW", "gdr-000002")), LOOSE)
    assert (rows[0].status, rows[0].reason) == (tc.DUPLICATE, "tag_in_use")


def test_one_machine_named_twice_in_a_file_is_a_duplicate(db):
    _machine(db, T480, serial="PF9ZQ7X1")
    text = _csv((T480, "", "A-1"), ("", "PF9ZQ7X1", "A-2"))
    rows = _by_line(tc.plan(db, text, LOOSE))
    assert rows[2].status == tc.ASSIGN
    assert (rows[3].status, rows[3].reason) == (tc.DUPLICATE, "identifier_repeated")


def test_a_uuid_two_machines_share_is_ambiguous_unless_the_serial_decides(db):
    _machine(db, T480, serial="CLONE-A")
    _machine(db, T480, serial="CLONE-B")
    rows = _by_line(
        tc.plan(db, _csv((T480, "", "A-1"), (T480, "CLONE-B", "A-2")), LOOSE)
    )
    assert rows[2].status == tc.AMBIGUOUS
    assert rows[3].status == tc.ASSIGN


def test_a_serial_bare_metal_discovery_saw_is_shown_with_its_mac(db):
    db.add(
        models.DiscoveredHost(
            mac_address="52:54:00:12:34:56", serial_number="BLANK-BOX-1", facts={}
        )
    )
    db.commit()
    rows = tc.plan(db, _csv(("", "blank-box-1", "A-9")), LOOSE)
    assert rows[0].status == tc.HOLD
    assert rows[0].discovered_mac == "52:54:00:12:34:56"


# --- applying ---------------------------------------------------------------


def test_apply_writes_only_what_the_plan_allows_and_audits_each_write(db):
    t480 = _machine(db, T480, serial="PF9ZQ7X1")
    text = _csv(
        (T480, "", "GDR-000001"),
        ("", "NEW-SERIAL-1", "GDR-000010"),
        ("", "NEW-SERIAL-2", "GDR-1"),
    )
    rows = tc.apply(db, text, GDR, None, "admin@example.com")
    db.commit()
    assert [r.status for r in rows] == [tc.ASSIGN, tc.HOLD, tc.FAILS_SCHEME]
    db.refresh(t480)
    assert t480.asset_tag == "GDR-000001"
    holds = db.query(models.HeldAssetTag).all()
    assert [(h.kind, h.identifier, h.asset_tag) for h in holds] == [
        ("system_serial", "NEW-SERIAL-1", "GDR-000010")
    ]
    audits = db.query(models.AuditLog).all()
    assert {a.entity_name for a in audits} == {"GDR-000001", "GDR-000010"}
    assert all(a.details["source"] == "csv_import" for a in audits)


def test_re_importing_a_hold_with_a_new_tag_replaces_it(db):
    tc.apply(db, _csv(("", "NEW-1", "A-1")), LOOSE, None, "admin")
    db.commit()
    rows = tc.apply(db, _csv(("", "new-1", "A-2")), LOOSE, None, "admin")
    db.commit()
    assert (rows[0].status, rows[0].previous) == (tc.HOLD, "A-1")
    assert [h.asset_tag for h in db.query(models.HeldAssetTag).all()] == ["A-2"]


def test_applying_the_same_file_twice_changes_nothing_the_second_time(db):
    _machine(db, T480)
    text = _csv((T480, "", "A-1"), ("", "NEW-1", "A-2"))
    tc.apply(db, text, LOOSE, None, "admin")
    db.commit()
    rows = tc.apply(db, text, LOOSE, None, "admin")
    assert {r.status for r in rows} == {tc.UNCHANGED}


# --- held tags reach their machine -----------------------------------------


def _report(db, fqdn, raw_uuid, serial):
    host = models.Host(
        id=uuid.uuid4(), fqdn=fqdn, active=True, approval_status="approved"
    )
    db.add(host)
    db.flush()
    mi.record_identity(
        db,
        host,
        {
            "system_uuid": raw_uuid,
            "system_serial": serial,
            "match_key": held.uuid_key(raw_uuid)[0],
            "vendor": "LENOVO",
            "model": "20L6",
            "status": {"system_uuid": "ran"},
        },
    )
    db.commit()
    return db.get(models.Machine, host.machine_id)


def test_a_tag_held_by_uuid_lands_when_the_machine_first_reports(db):
    tc.apply(db, _csv((T480_SWAPPED, "", "GDR-000042")), LOOSE, None, "admin")
    db.commit()
    machine = _report(db, "windows.t480", T480, "PF9ZQ7X1")
    assert machine.asset_tag == "GDR-000042"
    assert db.query(models.HeldAssetTag).count() == 0
    assert any("GDR-000042" in a.description for a in db.query(models.AuditLog))


def test_a_tag_held_by_serial_lands_too_ignoring_case(db):
    tc.apply(db, _csv(("", "pf9zq7x1", "GDR-000042")), LOOSE, None, "admin")
    db.commit()
    assert _report(db, "ubuntu.t480", T480, "PF9ZQ7X1").asset_tag == "GDR-000042"


def test_a_held_tag_never_overwrites_a_tag_the_machine_already_has(db):
    _machine(db, T480, serial="PF9ZQ7X1", tag="OLD-1")
    db.add(
        models.HeldAssetTag(
            kind="system_serial",
            identifier="PF9ZQ7X1",
            asset_tag="NEW-1",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    assert _report(db, "ubuntu.t480", T480, "PF9ZQ7X1").asset_tag == "OLD-1"
    assert db.query(models.HeldAssetTag).count() == 1


def test_a_held_tag_another_machine_took_meanwhile_stays_held(db):
    _machine(db, X13S, tag="GDR-000042")
    db.add(
        models.HeldAssetTag(
            kind="system_serial",
            identifier="PF9ZQ7X1",
            asset_tag="GDR-000042",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    assert _report(db, "ubuntu.t480", T480, "PF9ZQ7X1").asset_tag is None
    assert db.query(models.HeldAssetTag).count() == 1


# --- exporting --------------------------------------------------------------


def test_an_export_re_imports_unchanged(db):
    _machine(db, T480, serial="PF9ZQ7X1", tag="GDR-000001", fqdns=["ubuntu.t480"])
    _machine(db, X13S, serial="R90X13S")
    tc.apply(db, _csv(("", "NEW-1", "GDR-000010")), LOOSE, None, "admin")
    db.commit()
    exported = tc.export(db)
    lines = list(csv.reader(io.StringIO(exported)))
    assert lines[0] == tc.EXPORT_COLUMNS
    assert lines[1][0] == "GDR-000001" and lines[1][6] == "ubuntu.t480"
    assert lines[-1][-1] == "held"
    rows = tc.plan(db, exported, LOOSE)
    assert [r.status for r in rows] == [tc.UNCHANGED, tc.SKIPPED, tc.UNCHANGED]


def test_export_cells_never_run_as_spreadsheet_formulas(db):
    machine = _machine(db, T480, serial='=HYPERLINK("http://x")')
    machine.vendor = "@SUM(1)"
    db.commit()
    exported = tc.export(db)
    assert "'=HYPERLINK" in exported and "'@SUM(1)" in exported
    rows = tc.read(exported)
    assert rows[0].system_serial == '=HYPERLINK("http://x")'
