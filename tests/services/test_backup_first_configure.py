# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A new host's first configure (production milsurpmonitor, 2026-10-31).

The host refuses its first job files ("mount_point is not an NFS mount on
this host") until the storage host reports where its export is; that report
bumps the policy's version.  The host must get the new version at once, the
refusal of the old one is history rather than a failed job, and Prepare --
which runs on the storage host -- must not wait for the host at all."""

# pylint: disable=redefined-outer-name,unused-argument

import json

import pytest
from fastapi import HTTPException

from backend.api import backups as api
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)
from tests.test_backups_api import MANAGER

REFUSAL = "mount_point is not an NFS mount on this host"


def _new_host(session):
    s = _setup(session, storage_acked=0)
    s.policy.host_acked_version = 0
    session.commit()
    return s


def _configure_runs(session, s, host_id):
    return (
        session.query(models.BackupRun)
        .filter(
            models.BackupRun.policy_id == s.policy.id,
            models.BackupRun.host_id == host_id,
            models.BackupRun.action == jobs.CONFIGURE,
        )
        .order_by(models.BackupRun.queued_at)
        .all()
    )


def _version(run):
    return json.loads(run.parameters).get("config_version")


def test_a_learned_export_sends_the_host_its_new_jobs_at_once(session, sent):
    s = _new_host(session)
    s.nas.ipv4 = "192.168.4.10"
    host_v1 = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    storage_v1 = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(
        session, {"command_id": host_v1.command_id, "success": False, "error": REFUSAL}
    )
    results.record_command_result(session, {
        "command_id": storage_v1.command_id, "success": True,
        "result": {"nfs_path": "/restate/web-01"},
    })  # fmt: skip
    assert s.policy.config_version == 2
    # Queued now, not on the next five-minute tick.
    host_runs = _configure_runs(session, s, s.host.id)
    assert [_version(r) for r in host_runs] == [1, 2]
    assert host_runs[1].status in jobs.PENDING
    # The host accepts version 2: its refusal of version 1 leaves the job list.
    results.record_command_result(
        session, {"command_id": host_runs[1].command_id, "success": True}
    )
    assert s.policy.host_acked_version == 2
    assert host_v1.status == "failed" and host_v1.dismissed_at is not None
    assert host_runs[1].dismissed_at is None


def test_a_refusal_of_an_already_superseded_version_is_hidden_and_resent(session, sent):
    s = _new_host(session)
    old = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    s.policy.config_version = 2  # the storage host reported its export meanwhile
    session.flush()
    results.record_command_result(
        session, {"command_id": old.command_id, "success": False, "error": REFUSAL}
    )
    assert old.dismissed_at is not None
    assert [_version(r) for r in _configure_runs(session, s, s.host.id)] == [1, 2]


def test_a_current_refusal_stays_visible(session, sent):
    s = _new_host(session)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "host")
    results.record_command_result(
        session, {"command_id": run.command_id, "success": False, "error": REFUSAL}
    )
    assert run.status == "failed" and run.dismissed_at is None


@pytest.mark.asyncio
async def test_prepare_needs_only_the_storage_side(session, sent):
    s = _new_host(session)
    s.policy.storage_acked_version = 1
    session.commit()
    out = await api.backup_now(
        str(s.host.id), api.RunBody(action="prepare"), session, MANAGER
    )
    assert out["action"] == "prepare"
    assert sent[-1][0] == str(s.nas.id)
    with pytest.raises(HTTPException) as caught:
        await api.backup_now(
            str(s.host.id), api.RunBody(action="capture"), session, MANAGER
        )
    assert caught.value.status_code == 409


@pytest.mark.asyncio
async def test_prepare_still_waits_for_the_storage_side(session, sent):
    s = _new_host(session)
    with pytest.raises(HTTPException) as caught:
        await api.backup_now(
            str(s.host.id), api.RunBody(action="prepare"), session, MANAGER
        )
    assert caught.value.status_code == 409


def test_the_policy_view_says_when_storage_needs_preparing(session, sent):
    s = _new_host(session)
    assert views.policy_dict(s.policy)["needs_prepare"] is False  # nothing reported
    s.policy.storage_audit = json.dumps(
        [{"code": "export_own", "level": "error", "params": {}}]
    )
    assert views.policy_dict(s.policy)["needs_prepare"] is True
    s.policy.storage_audit = json.dumps(
        [{"code": "export_own", "level": "ok", "params": {}}]
    )
    assert views.policy_dict(s.policy)["needs_prepare"] is False
