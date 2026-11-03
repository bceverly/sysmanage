# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage host backs itself up (ROADMAP 24.13): its own policy goes out
as ONE ``self`` configure carrying both sides on a local target; one
acknowledgment counts for both; a capture's storage chain runs on the same
machine; it counts toward the target's cap."""

import json
import uuid
from datetime import datetime

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_tick as tick
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _result,
    _setup,
    sent,
)

STAMP = datetime(2026, 11, 3, 5, 0)


def _self_policy(session, s):
    policy = models.BackupPolicy(
        id=uuid.uuid4(), host_id=s.nas.id, target_id=s.target.id, enabled=True,
        interval_hours=24, keep_last=7, check_interval_days=7, quiesce=False,
        config_version=1, host_acked_version=0, storage_acked_version=0,
        created_at=STAMP, updated_at=STAMP,
    )  # fmt: skip
    session.add(policy)
    session.commit()
    return policy


def test_the_storage_hosts_policy_is_one_local_configure_for_both_sides(session):
    s = _setup(session)
    policy = _self_policy(session, s)
    assert jobs.is_self(policy, s.target) and not jobs.is_self(s.policy, s.target)
    payload = jobs.self_configuration(policy, s.target, s.nas)
    assert payload["role"] == "self"
    assert payload["target"] == {
        "mount_point": "/srv/backups/restate",
        "repo_dir": jobs.repo_dir(s.nas),
        "service_account": "restate",
    }
    assert {
        "capture",
        "snapshots",
        "estimate",
        "prune",
        "protect",
        "seal",
        "du",
    } <= set(payload["jobs"])
    assert "nfs" not in payload["target"] and "client_address" not in payload["target"]


def test_the_tick_sends_one_self_configure_to_the_storage_host(session, sent):
    s = _setup(session)
    _self_policy(session, s)
    tick.configure_now(session)
    to_nas = [
        (h, p) for h, c, p in sent if c == "backup_configure" and h == str(s.nas.id)
    ]
    roles = sorted(p["role"] for _h, p in to_nas)
    assert roles.count("self") == 1
    # s.policy (the other host) still gets its storage-side configure there.
    assert roles.count("storage") <= 1


def test_one_self_acknowledgment_counts_for_both_sides(session, sent):
    s = _setup(session)
    policy = _self_policy(session, s)
    run = jobs.queue_configure(session, policy, s.target, s.nas, jobs.SELF_ROLE)
    reply = {
        "success": True,
        "installed": ["capture", "prune", "protect"],
        "abilities": ["list", "status"],
        "storage_abilities": ["keep_yearly"],
        "hooks": ["postgresql"],
        "restate_version": "2.2.0.17",
        "self_left_out": ["/srv/backups/restate"],
    }
    results.record_command_result(
        session, {"command_id": run.command_id, "success": True, "result": reply}
    )
    assert (policy.host_acked_version, policy.storage_acked_version) == (1, 1)
    assert policy.storage_protects is True
    assert json.loads(policy.storage_abilities) == ["keep_yearly"]
    assert json.loads(policy.host_abilities) == ["list", "status"]
    assert policy.restate_version == policy.storage_restate_version == "2.2.0.17"


def test_a_self_capture_is_protected_sealed_and_pruned_on_the_same_machine(
    session, sent
):
    s = _setup(session)
    policy = _self_policy(session, s)
    policy.host_acked_version = policy.storage_acked_version = 1
    policy.storage_protects = True
    session.commit()
    capture = jobs.queue_run(session, policy, s.nas.id, "capture")
    results.record_result(session, s.nas.id, _result(capture, "ok", snapshot="s1"))
    queued = (
        session.query(models.BackupRun)
        .filter(models.BackupRun.policy_id == policy.id,
                models.BackupRun.action.in_(jobs.STORAGE_ACTIONS))
        .all()
    )  # fmt: skip
    assert queued and all(str(run.host_id) == str(s.nas.id) for run in queued)


def test_a_self_capture_counts_toward_the_targets_cap(session, sent):
    s = _setup(session)
    policy = _self_policy(session, s)
    jobs.queue_run(session, policy, s.nas.id, "capture")
    session.commit()
    assert tick.running_captures(session, s.target.id) == 1
