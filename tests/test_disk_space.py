# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Disk sizes from every agent's shape, and the nearly-full warning
(2026-11-20).  Production: functionallyparanoid.com's root sat at 96-99 %
for days while every host's disk list had no sizes at all, until an update
ran out of room part-way."""

# pylint: disable=redefined-outer-name

import uuid

import pytest

from backend.api.handlers.custom_metric_handlers import handle_host_metrics
from backend.api.handlers.os_hardware_handlers import handle_hardware_update
from backend.persistence import models
from backend.services import disk_space
from backend.services.storage_sizes import device_sizes
from tests.services.test_backup_results import _host

GIB = 1024**3


# --- every agent's shape -----------------------------------------------------


def test_linux_lsblk_human_sizes_are_read():
    # Linux agents up to 3.14 send only lsblk's text: "8.7G".
    sizes = device_sizes({"name": "vda1", "size": "8.7G", "file_system": "ext4"})
    assert sizes["total"] == int(8.7 * GIB)
    assert sizes["used"] is None and sizes["available"] is None
    assert sizes["filesystem"] == "ext4"


def test_bsd_and_macos_bytes_are_read():
    sizes = device_sizes(
        {"capacity_bytes": 100, "used_bytes": 60, "available_bytes": 40,
         "file_system": "ufs", "size": "100B"}
    )  # fmt: skip
    assert sizes == {"total": 100, "used": 60, "available": 40, "filesystem": "ufs"}


def test_windows_size_and_free_space_are_read():
    sizes = device_sizes({"size": 1000, "free_space": 250, "file_system": "NTFS"})
    assert sizes == {"total": 1000, "used": 750, "available": 250, "filesystem": "NTFS"}


@pytest.mark.parametrize("bad", ["", "N/A", "lots", None, True, -5])
def test_an_unreadable_size_is_none_never_a_guess(bad):
    assert device_sizes({"size": bad})["total"] is None


def test_placeholder_filesystems_are_none():
    assert device_sizes({"file_system": "N/A"})["filesystem"] is None
    assert device_sizes({"file_system": "unknown"})["filesystem"] is None


# --- the fullest filesystem ----------------------------------------------------


def _fs(mount, total, available, fs="ext4", **extra):
    return {"mount_point": mount, "capacity_bytes": total,
            "available_bytes": available, "file_system": fs, **extra}  # fmt: skip


def test_the_fullest_fillable_filesystem_is_found():
    found = disk_space.fullest(
        [
            _fs("/", 100, 3),
            _fs("/data", 100, 50),
            _fs("/snap/core/1", 100, 0, fs="squashfs"),  # full by design
            _fs("/boot/efi", 100, 1, fs="vfat"),
            _fs("/mnt/nas", 100, 0, fs="nfs4"),  # someone else's disk
            {"name": "vda", "capacity_bytes": 100},  # not mounted
            {"error": "lsblk failed"},
        ]
    )
    assert found == {"mount": "/", "percent": 97.0, "available": 3}


def test_no_free_space_reported_is_none():
    assert disk_space.fullest([{"mount_point": "/", "size": "8.7G"}]) is None


# --- through the handlers -------------------------------------------------------


class _Conn:  # pylint: disable=too-few-public-methods
    def __init__(self, host_id):
        self.host_id = host_id
        self.hostname = "fp.example"


@pytest.mark.asyncio
async def test_a_disk_list_with_sizes_lands_and_warns(session):
    host = _host(session, fqdn="fp.example")
    await handle_hardware_update(
        session,
        _Conn(host.id),
        {
            "storage_devices": [
                _fs("/", 8 * GIB, GIB // 100, name="vda1"),
                _fs("/boot", GIB, GIB // 2, name="vda16"),
            ]
        },
    )
    rows = session.query(models.StorageDevice).filter_by(host_id=host.id).all()
    assert {r.mount_point: r.filesystem for r in rows} == {"/": "ext4", "/boot": "ext4"}
    assert all(r.total_size_bytes and r.available_size_bytes for r in rows)
    session.refresh(host)
    assert host.disk_fullest_mount == "/" and disk_space.nearly_full(host)
    assert disk_space.summary(session)["disk_hosts"][0]["fqdn"] == "fp.example"


@pytest.mark.asyncio
async def test_host_metrics_warn_without_a_license(session, monkeypatch):
    from backend.services import (  # pylint: disable=import-outside-toplevel
        host_metrics,
    )

    monkeypatch.setattr(host_metrics, "collecting", lambda: False)
    host = _host(session, fqdn="old-linux.example")
    await handle_host_metrics(
        session,
        _Conn(host.id),
        {"collected_at": "2026-11-20T17:39:52Z",
         "metrics": {disk_space.METRIC_KEY: 99.3}},
    )  # fmt: skip
    session.refresh(host)
    assert host.disk_used_percent == 99.3 and disk_space.nearly_full(host)
    assert disk_space.summary(session)["disk_nearly_full"] == 1


def test_a_healthy_disk_is_not_named(session):
    host = _host(session, fqdn="roomy.example")
    disk_space.record_from_metrics(
        session, host.id, {"metrics": {disk_space.METRIC_KEY: 33.0}}
    )
    session.commit()
    assert not disk_space.nearly_full(host)
    assert disk_space.summary(session) == {"disk_nearly_full": 0, "disk_hosts": []}


def test_an_unapproved_or_unknown_host_is_ignored(session):
    assert not disk_space.record_from_metrics(
        session, uuid.uuid4(), {"metrics": {disk_space.METRIC_KEY: 99.0}}
    )
    assert not disk_space.record_from_metrics(session, None, {"metrics": {}})
