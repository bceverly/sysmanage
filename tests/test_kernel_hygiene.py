# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Boot history, the kernels a cleanup keeps, and the cleanup runs (ROADMAP 27.8).

Bryan, 2026-11-27: never remove the kernel last booted successfully -- Livepatch
may be what keeps it safe -- until the new kernel has had one clean boot."""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import auto_update_cleanup, kernel_boots, package_cleanup

T0 = datetime(2026, 11, 27, 12, 0, 0)


@pytest.fixture(name="host")
def _host(db_session):
    host = models.Host(id=uuid.uuid4(), fqdn="license.example", active=True, status="up",
                       approval_status="approved")  # fmt: skip
    host.os_details = json.dumps(
        {
            "installed_kernels": [
                "6.8.0-139-generic",
                "6.8.0-149-generic",
                "6.8.0-151-generic",
                "6.8.0-94-generic",
            ]
        }
    )
    db_session.add(host)
    db_session.commit()
    return host


def _boot(db, host, boot_time, release, seen):
    host.boot_time = boot_time
    kernel_boots.note(db, host, release, now=seen)
    db.flush()


def test_a_kernel_is_proven_only_by_a_boot_that_stayed_up(db_session, host):
    _boot(db_session, host, T0, "6.8.0-151-generic", T0 + timedelta(minutes=2))
    row = kernel_boots.history(db_session, host.id)[0]
    assert row.proven_at is None
    _boot(db_session, host, T0, "6.8.0-151-generic", T0 + timedelta(minutes=16))
    assert kernel_boots.history(db_session, host.id)[0].proven_at is not None
    assert len(kernel_boots.history(db_session, host.id)) == 1  # same boot, one row


def test_boot_time_jitter_is_the_same_boot(db_session, host):
    _boot(db_session, host, T0, "6.8.0-151-generic", T0 + timedelta(minutes=1))
    _boot(
        db_session,
        host,
        T0 + timedelta(seconds=1),
        "6.8.0-151-generic",
        T0 + timedelta(minutes=20),
    )
    assert len(kernel_boots.history(db_session, host.id)) == 1


def test_long_running_host_proves_its_kernel_on_first_report(db_session, host):
    """A host up for weeks when this ships: its running kernel is proven."""
    _boot(db_session, host, T0 - timedelta(days=30), "6.8.0-139-generic", T0)
    refusal, keep = kernel_boots.protected(
        db_session, host, package_cleanup.installed_kernels(db_session, host)
    )
    assert refusal is None
    assert {k["release"]: k["reason"] for k in keep} == {
        "6.8.0-139-generic": "running",
        "6.8.0-151-generic": "newest",
    }


def test_after_reboot_the_last_good_kernel_is_kept_until_the_new_one_is_proven(
    db_session, host
):
    _boot(db_session, host, T0 - timedelta(days=30), "6.8.0-139-generic", T0)
    # reboot into 151: just booted, not proven -> no cleanup at all
    _boot(
        db_session,
        host,
        T0 + timedelta(hours=1),
        "6.8.0-151-generic",
        T0 + timedelta(hours=1, minutes=3),
    )
    refusal, _keep = kernel_boots.protected(
        db_session, host, package_cleanup.installed_kernels(db_session, host)
    )
    assert refusal == "running_kernel_not_proven"
    # 151 proven: 139 (the last good boot before it) is still kept, as the way back
    _boot(
        db_session,
        host,
        T0 + timedelta(hours=1),
        "6.8.0-151-generic",
        T0 + timedelta(hours=1, minutes=20),
    )
    refusal, keep = kernel_boots.protected(
        db_session, host, package_cleanup.installed_kernels(db_session, host)
    )
    assert refusal is None
    assert {k["release"]: k["reason"] for k in keep} == {
        "6.8.0-151-generic": "running",
        "6.8.0-139-generic": "last_proven",
    }


def test_unknown_running_kernel_refuses(db_session, host):
    host.boot_time = T0
    refusal, keep = kernel_boots.protected(db_session, host, ["6.8.0-151-generic"])
    assert (refusal, keep) == ("unknown_running_kernel", [])


def test_minimum_two_kernels(db_session, host):
    host.os_details = json.dumps(
        {"installed_kernels": ["6.8.0-151-generic", "6.8.0-149-generic"]}
    )
    _boot(db_session, host, T0 - timedelta(days=3), "6.8.0-151-generic", T0)
    _refusal, keep = kernel_boots.protected(
        db_session, host, package_cleanup.installed_kernels(db_session, host)
    )
    assert [k["release"] for k in keep] == ["6.8.0-151-generic", "6.8.0-149-generic"]


def test_installed_kernels_from_packages_without_agent_list(db_session, host):
    host.os_details = None
    for name in (
        "linux-image-6.8.0-151-generic",
        "linux-image-unsigned-6.8.0-149-generic",
        "linux-image-generic",
        "bash",
    ):
        db_session.add(
            models.SoftwarePackage(
                host_id=host.id,
                package_name=name,
                package_version="1",
                package_manager="apt",
                created_at=T0,
                updated_at=T0,
            )
        )
    db_session.flush()
    assert sorted(package_cleanup.installed_kernels(db_session, host)) == [
        "6.8.0-149-generic",
        "6.8.0-151-generic",
    ]


def test_request_sends_the_protected_kernels(db_session, host):
    _boot(db_session, host, T0 - timedelta(days=30), "6.8.0-139-generic", T0)
    with patch.object(package_cleanup.queue_ops, "enqueue_message") as enqueue:
        run = package_cleanup.request(
            db_session,
            host,
            "apply",
            "admin@example.com",
            approved=["linux-image-6.8.0-94-generic"],
        )
    assert run.status == "queued"
    params = (
        enqueue.call_args.kwargs["message_data"]["data"]["parameters"]
        if "parameters" in enqueue.call_args.kwargs["message_data"].get("data", {})
        else enqueue.call_args.kwargs["message_data"]["data"]
    )
    assert set(params["protected_releases"]) == {
        "6.8.0-139-generic",
        "6.8.0-151-generic",
    }
    assert params["approved"] == ["linux-image-6.8.0-94-generic"]


def test_request_refused_while_running_kernel_unproven(db_session, host):
    _boot(db_session, host, T0, "6.8.0-151-generic", T0 + timedelta(minutes=1))
    with patch.object(package_cleanup.queue_ops, "enqueue_message") as enqueue:
        run = package_cleanup.request(db_session, host, "plan", "admin@example.com")
    assert run.status == "refused" and run.error == "running_kernel_not_proven"
    enqueue.assert_not_called()


def test_result_closes_only_its_own_hosts_queued_run(db_session, host):
    _boot(db_session, host, T0 - timedelta(days=30), "6.8.0-139-generic", T0)
    with patch.object(package_cleanup.queue_ops, "enqueue_message"):
        run = package_cleanup.request(db_session, host, "plan", "admin@example.com")
    data = {
        "run_id": str(run.id),
        "status": "planned",
        "packages": [
            {
                "name": "linux-image-6.8.0-94-generic",
                "kernel": "6.8.0-94",
                "reason": "old_kernel",
            }
        ],
        "kept": [
            {
                "name": "linux-image-6.8.0-139-generic",
                "kernel": "6.8.0-139",
                "reason": "protected",
            }
        ],
        "running_kernel": "6.8.0-139-generic",
    }
    assert (
        package_cleanup.record_result(db_session, uuid.uuid4(), data) is None
    )  # another host
    closed = package_cleanup.record_result(db_session, host.id, data)
    assert closed.status == "planned" and closed.packages[0]["reason"] == "old_kernel"
    assert (
        package_cleanup.record_result(db_session, host.id, data) is None
    )  # already closed


def _finished_run(db, host, reboot_status="back"):
    run = models.AutoUpdateRun(profile_name="p", host_id=host.id, status="succeeded",
                               reboot_status=reboot_status, queued_at=T0, completed_at=T0)  # fmt: skip
    db.add(run)
    db.flush()
    return run


def test_auto_update_cleans_up_once_after_a_finished_run(db_session, host):
    _boot(db_session, host, T0 - timedelta(days=30), "6.8.0-139-generic", T0)
    _finished_run(db_session, host)
    with patch.object(package_cleanup.queue_ops, "enqueue_message") as enqueue:
        assert (
            auto_update_cleanup.after_runs(
                db_session, T0 + timedelta(minutes=5), "apply"
            )
            == 1
        )
        db_session.flush()
        assert (
            auto_update_cleanup.after_runs(
                db_session, T0 + timedelta(minutes=6), "apply"
            )
            == 0
        )
    params = enqueue.call_args.kwargs["message_data"]["data"]
    params = params.get("parameters", params)
    assert params["mode"] == "apply" and params["approve_plan"] is True


def test_auto_update_waits_for_the_new_kernel_to_prove_itself(db_session, host):
    _boot(
        db_session,
        host,
        T0 - timedelta(days=30),
        "6.8.0-139-generic",
        T0 - timedelta(minutes=1),
    )
    _boot(
        db_session, host, T0, "6.8.0-151-generic", T0 + timedelta(minutes=2)
    )  # just rebooted
    _finished_run(db_session, host)
    with patch.object(package_cleanup.queue_ops, "enqueue_message") as enqueue:
        assert (
            auto_update_cleanup.after_runs(
                db_session, T0 + timedelta(minutes=3), "apply"
            )
            == 0
        )
    enqueue.assert_not_called()


def test_auto_update_cleanup_off_and_pending_reboot(db_session, host):
    _boot(db_session, host, T0 - timedelta(days=30), "6.8.0-139-generic", T0)
    _finished_run(db_session, host, reboot_status="queued")
    with patch.object(package_cleanup.queue_ops, "enqueue_message"):
        assert (
            auto_update_cleanup.after_runs(db_session, T0, "apply") == 0
        )  # reboot pending
        assert auto_update_cleanup.after_runs(db_session, T0, "off") == 0
