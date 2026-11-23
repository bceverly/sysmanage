# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Swap for the antivirus memory floor (av_swap): with the setting on, a host
below ClamAV's floor gets the swap it lacks and then ClamAV, without a second
request; otherwise it is held with the reason."""

# pylint: disable=redefined-outer-name,unused-argument,unused-import,unnecessary-lambda

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import av_auto_deploy, av_swap
from tests.services.test_av_auto_deploy import _host, db, queued  # noqa: F401


@pytest.fixture
def swap_on():
    with patch.object(av_swap, "enabled", return_value=True), patch.object(
        av_swap._queue_ops, "enqueue_message",
        side_effect=lambda **kw: av_auto_deploy._queue_ops.enqueue_message(**kw),
    ):  # fmt: skip
        yield


def _commands(queued):
    return [m["message_data"]["data"]["command_type"] for m in queued]


def test_swap_is_sized_to_the_gap_in_whole_gb():
    host = SimpleNamespace(memory_total_mb=1962, swap_total_mb=0)
    assert av_swap.swap_needed_mb(host, 3500) == 3072  # 3500 + 512 - 1962 -> 3 GB
    host.swap_total_mb = 2048
    assert av_swap.swap_needed_mb(host, 3500) == 1024
    host.swap_total_mb = 4096
    assert av_swap.swap_needed_mb(host, 3500) is None  # enough already
    assert av_swap.swap_needed_mb(SimpleNamespace(memory_total_mb=None), 3500) is None


def test_swap_counts_toward_the_floor():
    host = SimpleNamespace(memory_total_mb=1962, swap_total_mb=2048)
    assert av_auto_deploy.memory_shortfall(host, "clamav") is None
    host.swap_total_mb = 1024
    assert "1024 MB of swap" in av_auto_deploy.memory_shortfall(host, "clamav")


def test_with_the_setting_off_a_small_host_is_held_as_before(db, queued):
    small = _host(db, memory_total_mb=1962)
    summary = av_auto_deploy.reconcile(db)
    assert summary["low_memory"] == 1 and not queued
    assert db.get(models.AntivirusAutoDeploy, small.id) is None


def test_with_it_on_the_host_gets_swap_then_clamav(db, queued, swap_on):
    small = _host(db, memory_total_mb=1962)
    summary = av_auto_deploy.reconcile(db)
    assert summary["swap_asked"] == 1 and _commands(queued) == ["ensure_swap"]
    assert queued[0]["message_data"]["data"]["parameters"] == {"size_mb": 3072}
    record = db.get(models.AntivirusAutoDeploy, small.id)
    assert record.status == av_swap.STATUS_ADDING
    av_auto_deploy.reconcile(db)
    assert len(queued) == 1  # not asked twice while it works
    handled = av_auto_deploy.record_swap_result(db, {
        "command_id": queued[0]["message_id"], "success": True,
        "result": {"success": True, "size_mb": 3072, "path": "/sysmanage.swap"},
    })  # fmt: skip
    db.commit()
    assert handled and _commands(queued) == ["ensure_swap", "apply_deployment_plan"]
    assert (
        record.status == av_auto_deploy.STATUS_QUEUED and record.swap_added_mb == 3072
    )


def test_a_refused_swap_holds_the_host_with_why_and_retries_later(db, queued, swap_on):
    small = _host(db, memory_total_mb=1962)
    av_auto_deploy.reconcile(db)
    av_auto_deploy.record_swap_result(db, {
        "command_id": queued[0]["message_id"], "success": False,
        "result": {"success": False, "reason": "no_room",
                   "error": "There is no room for a 3072 MB swap file"},
    })  # fmt: skip
    db.commit()
    record = db.get(models.AntivirusAutoDeploy, small.id)
    assert record.status == av_swap.STATUS_FAILED and "no room" in record.last_error
    assert av_auto_deploy.reconcile(db)["swap_failed"] == 1 and len(queued) == 1
    record.finished_at = datetime.utcnow() - timedelta(
        hours=av_swap.SWAP_RETRY_HOURS + 1
    )
    db.commit()
    av_auto_deploy.reconcile(db)
    assert _commands(queued) == ["ensure_swap", "ensure_swap"]


@pytest.mark.parametrize(
    "platform,release,capabilities,memory",
    [
        ("Windows", "Windows 11", None, 1962),  # not Linux or a BSD
        ("Linux", "Ubuntu 24.04", {"commands": ["check_updates"]}, 1962),  # old agent
        ("Linux", "Ubuntu 24.04", None, 512),  # a 512 MB host: 4 GB of swap, allowed
    ],
)
def test_where_swap_cannot_be_added_the_host_is_held(db, queued, swap_on, platform,
                                                    release, capabilities, memory):  # fmt: skip
    if platform == "Windows":
        db.add(models.AntivirusDefault(os_name="Windows", antivirus_package="clamav",
                                       created_at=datetime.utcnow(),
                                       updated_at=datetime.utcnow()))  # fmt: skip
        db.commit()
    host = _host(db, release=release, platform=platform, memory_total_mb=memory)
    if capabilities:
        host.agent_capabilities = json.dumps(capabilities)
        db.commit()
    summary = av_auto_deploy.reconcile(db)
    expected_swap = memory == 512  # only the Linux host with a current agent
    assert bool(summary.get("swap_asked")) is expected_swap


def test_why_it_cannot():
    host = SimpleNamespace(platform="Linux", agent_capabilities=None)
    assert av_swap.cannot_add(host, 3072) is None
    assert "more than 8192" in av_swap.cannot_add(host, 9216)
    assert "Linux and the BSDs" in av_swap.cannot_add(
        SimpleNamespace(platform="Darwin", agent_capabilities=None), 2048
    )
