# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Linking hosts to their machine (Phase 23.2 S2).

The rules that matter are the ones that must NOT link: a cloned VM, a UUID two
machines share by vendor accident, a container reading its parent's hardware.
Merging any of those would put two physical machines under one asset tag.
"""

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import machine_identity as mi

# The same laptop: 1a2b... in SMBIOS order; the match_key is what the agent
# sends (the byte-order-insensitive form).
UUID = "1a2b3c4d-5e6f-11b2-a85c-0f1e2d3c4b5a"
KEY = "1a2b3c4d-5e6f-11b2-a85c-0f1e2d3c4b5a"


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


def _host(db, name, parent=None):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=name,
        active=True,
        approval_status="approved",
        parent_host_id=parent.id if parent else None,
    )
    db.add(host)
    db.flush()
    return host


def _identity(serial="PF9ZQ7X1", vendor="LENOVO", model="20L6S0U300", key=KEY):
    return {
        "system_uuid": UUID,
        "system_serial": serial,
        "board_serial": None,
        "vendor": vendor,
        "model": model,
        "match_key": key,
        "status": {
            "system_uuid": "ran",
            "system_serial": "ran",
            "board_serial": "absent",
        },
    }


def test_the_first_report_creates_the_machine_and_links_the_host(db):
    host = _host(db, "ubuntu.t480")
    mi.record_identity(db, host, _identity())
    machine = db.get(models.Machine, host.machine_id)
    assert machine.match_key == KEY and machine.system_serial == "PF9ZQ7X1"
    assert not machine.is_virtual
    assert json.loads(host.hw_identity_status)["board_serial"] == "absent"


def test_three_oses_on_one_physical_laptop_share_one_machine(db):
    hosts = [_host(db, n) for n in ("windows.t480", "ubuntu.t480", "openbsd.t480")]
    for host in hosts:
        mi.record_identity(db, host, _identity())
    assert len({h.machine_id for h in hosts}) == 1
    assert db.query(models.Machine).count() == 1
    assert all(h.machine_conflict_id is None for h in hosts)


def test_a_reinstalled_os_lands_back_on_the_same_machine(db):
    old, new = _host(db, "old-install"), _host(db, "new-install")
    mi.record_identity(db, old, _identity())
    mi.record_identity(db, new, _identity())
    assert new.machine_id == old.machine_id


def test_a_cloned_vm_is_held_for_an_admin_not_merged(db):
    vm_identity = _identity(serial=None, vendor="QEMU", model="Standard PC")
    original, clone = _host(db, "vm-a"), _host(db, "vm-b")
    mi.record_identity(db, original, vm_identity)
    mi.record_identity(db, clone, vm_identity)
    assert clone.machine_id is None
    assert clone.machine_conflict_id == original.machine_id
    assert clone.machine_conflict_reason == mi.CONFLICT_VIRTUAL_CLONE


def test_the_same_uuid_with_a_different_serial_is_held(db):
    first, second = _host(db, "a"), _host(db, "b")
    mi.record_identity(db, first, _identity(serial="PF9ZQ7X1"))
    mi.record_identity(db, second, _identity(serial="ZZ000001"))
    assert second.machine_id is None
    assert second.machine_conflict_reason == mi.CONFLICT_SERIAL_MISMATCH


def test_a_missing_serial_is_not_a_disagreement(db):
    privileged, unprivileged = _host(db, "a"), _host(db, "b")
    mi.record_identity(db, privileged, _identity(serial="PF9ZQ7X1"))
    mi.record_identity(db, unprivileged, _identity(serial=None))
    assert unprivileged.machine_id == privileged.machine_id


def test_a_container_reading_its_parents_hardware_is_not_linked(db):
    parent = _host(db, "server")
    mi.record_identity(db, parent, _identity())
    container = _host(db, "lxd-container", parent=parent)
    mi.record_identity(db, container, _identity())
    assert container.machine_id is None and container.machine_conflict_id is None


def test_no_usable_identity_creates_nothing_and_keeps_an_existing_link(db):
    host = _host(db, "a")
    mi.record_identity(db, host, _identity())
    linked = host.machine_id
    unreadable = {
        "system_uuid": None,
        "match_key": None,
        "status": {"system_uuid": "unprivileged"},
    }
    mi.record_identity(db, host, unreadable)
    assert host.machine_id == linked
    assert json.loads(host.hw_identity_status) == {"system_uuid": "unprivileged"}
    fresh = _host(db, "b")
    mi.record_identity(db, fresh, unreadable)
    assert fresh.machine_id is None
    assert db.query(models.Machine).count() == 1


def test_resolve_same_links_the_host(db):
    vm = _identity(serial=None, vendor="VMware, Inc.", model="VMware Virtual Platform")
    first, second = _host(db, "a"), _host(db, "b")
    mi.record_identity(db, first, vm)
    mi.record_identity(db, second, vm)
    machine = mi.resolve_conflict(db, second, mi.DECISION_SAME)
    assert second.machine_id == first.machine_id == machine.id
    assert second.machine_conflict_id is None


def test_resolve_different_gives_the_clone_its_own_machine_for_good(db):
    vm = _identity(serial=None, vendor="QEMU", model="Standard PC")
    original, clone = _host(db, "a"), _host(db, "b")
    mi.record_identity(db, original, vm)
    mi.record_identity(db, clone, vm)
    own = mi.resolve_conflict(db, clone, mi.DECISION_DIFFERENT)
    assert own.id != original.machine_id and clone.machine_id == own.id
    # Later reports keep the clone on its own machine instead of re-holding it.
    mi.record_identity(db, clone, vm)
    assert clone.machine_id == own.id and clone.machine_conflict_id is None


def test_resolving_when_nothing_is_held_is_refused(db):
    host = _host(db, "a")
    with pytest.raises(ValueError):
        mi.resolve_conflict(db, host, mi.DECISION_SAME)


def test_a_later_host_fills_in_what_an_earlier_one_could_not_read(db):
    unprivileged, privileged = _host(db, "a"), _host(db, "b")
    mi.record_identity(db, unprivileged, _identity(serial=None))
    mi.record_identity(db, privileged, _identity(serial="PF9ZQ7X1"))
    machine = db.get(models.Machine, unprivileged.machine_id)
    assert machine.system_serial == "PF9ZQ7X1"


@pytest.mark.parametrize(
    "vendor,model,virtual",
    [
        ("QEMU", "Standard PC (i440FX + PIIX, 1996)", True),
        ("Microsoft Corporation", "Virtual Machine", True),
        ("VMware, Inc.", "VMware7,1", True),
        ("innotek GmbH", "VirtualBox", True),
        ("Amazon EC2", "m5.large", True),
        ("LENOVO", "20L6S0U300", False),
        ("Apple Inc.", "MacBookAir10,1", False),
        ("Dell Inc.", "PowerEdge R750", False),
    ],
)
def test_virtual_hardware_is_recognized(vendor, model, virtual):
    assert mi.is_virtual(vendor, model) is virtual


def test_reported_values_are_bounded_and_typed(db):
    host = _host(db, "a")
    mi.record_identity(
        db,
        host,
        {**_identity(), "system_serial": "S" * 5000, "vendor": 42, "status": "junk"},
    )
    assert len(host.hw_system_serial) == 255
    assert json.loads(host.hw_identity_status) == {}
    mi.record_identity(db, host, "not a dict")  # ignored, never raises
