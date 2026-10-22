# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage host's own health on the backup target (ROADMAP 24.8): its
drives by hardware health, and the space under the storage path."""

import uuid
from datetime import datetime

from backend.persistence import models
from backend.services import backup_storage_health as health
from backend.services import backup_views as views
from tests.services.test_backup_results import _setup

NOW = datetime(2026, 10, 21, 12, 0)
GB = 1024**3


def _component(session, host, kind, state, name):
    session.add(models.HardwareComponent(
        id=uuid.uuid4(), host_id=host.id, kind=kind, ident=name, name=name,
        state=state, first_seen_at=NOW, last_seen_at=NOW, state_since=NOW,
    ))  # fmt: skip
    session.commit()


def _disk(session, host, mount, total_gb, available_gb):
    session.add(models.StorageDevice(
        id=uuid.uuid4(), host_id=host.id, device_name=mount, mount_point=mount,
        total_size_bytes=total_gb * GB, available_size_bytes=available_gb * GB,
        last_updated=NOW,
    ))  # fmt: skip
    session.commit()


def test_a_healthy_storage_host_has_no_warnings(session):
    s = _setup(session)
    _component(session, s.nas, "drive", "ok", "ada0")
    _component(session, s.nas, "sensor", "failed", "cpu0")  # sensors do not count
    _disk(session, s.nas, "/srv/backups/restate", 1000, 800)
    found = health.storage_health(session, s.target, s.nas)
    assert found["drives"] == {"failed": [], "warning": []}
    assert found["space"]["used_percent"] == 20.0
    assert health.health_warnings(found) == []


def test_the_most_specific_mount_holding_the_path_is_measured(session):
    s = _setup(session)
    _disk(session, s.nas, "/", 100, 1)  # nearly full, but not where backups go
    _disk(session, s.nas, "/srv/backups", 1000, 500)
    _disk(session, s.nas, "/srv/backups/restate", 1000, 900)
    _disk(session, s.nas, "/srv/backups/restatex", 10, 0)  # a prefix, not a parent
    space = health.storage_health(session, s.target, s.nas)["space"]
    assert space["mount_point"] == "/srv/backups/restate"
    assert space["available_bytes"] == 900 * GB


def test_failing_drives_and_full_disks_warn_worst_first(session):
    s = _setup(session)
    _component(session, s.nas, "drive", "failed", "ada1")
    _component(session, s.nas, "pool", "warning", "zroot")
    _disk(session, s.nas, "/srv", 1000, 30)  # 97% used
    found = health.storage_health(session, s.target, s.nas)
    assert health.health_warnings(found) == [
        "storage_drive_failed", "storage_space_critical", "storage_drive_warning",
    ]  # fmt: skip
    target = views.target_dict(s.target, session)
    assert "storage_drive_failed" in target["warnings"] and target["problem"] is True
    assert target["storage_health"]["drives"]["failed"] == ["ada1"]


def test_space_low_is_a_caution_not_a_problem(session):
    s = _setup(session)
    _disk(session, s.nas, "/srv", 1000, 120)  # 88% used
    target = views.target_dict(s.target, session)
    assert "storage_space_low" in target["warnings"]
    assert "storage_space_critical" not in target["warnings"]


def test_no_inventory_means_no_space_figure(session):
    s = _setup(session)
    assert health.storage_health(session, s.target, s.nas)["space"] is None
    assert health.storage_health(session, s.target, None) is None
