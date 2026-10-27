# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The storage host's append-only audit on the server (24.1 / 24.5): stored
from configure replies and storage job results, summarized into the
target's warnings -- host-wide once, per repository with its hosts."""

# pylint: disable=redefined-outer-name,unused-import

import json

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_results as results
from backend.services import backup_storage_audit as audit
from backend.services import backup_views as views
from tests.services.test_backup_results import (  # noqa: F401  # fixture
    _host,
    _result,
    _setup,
    sent,
)

BAD = [
    {"code": "nfs_local_locks", "level": "error", "params": {}},
    {"code": "export_shared", "level": "error", "params": {"exports": ["/srv/b"]}},
    {
        "code": "append_only_layout",
        "level": "warning",
        "params": {"unprotected_files": 9},
    },
    {"code": "nfs_server", "level": "ok", "params": {}},
    {"code": 7, "level": "error"},  # junk: dropped
]


def test_the_storage_configuration_says_whom_the_export_serves(session):
    s = _setup(session)
    s.host.ipv4 = "192.168.4.196"
    config = jobs.storage_configuration(s.policy, s.target, s.host)
    assert config["target"]["client_address"] == "192.168.4.196"
    assert config["target"]["service_account"] == "restate"
    s.target.service_account = "backup"
    assert (
        jobs.storage_configuration(s.policy, s.target, s.host)["target"][
            "service_account"
        ]
        == "backup"
    )


def test_a_storage_configure_reply_stores_the_audit(session, sent):
    s = _setup(session, storage_acked=0)
    run = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    results.record_command_result(session, {
        "command_id": run.command_id, "success": True,
        "result": {"storage_fs": {}, "storage_audit": BAD},
    })  # fmt: skip
    stored = json.loads(s.policy.storage_audit)
    assert [f["code"] for f in stored] == [
        "nfs_local_locks", "export_shared", "append_only_layout", "nfs_server"
    ]  # fmt: skip
    assert s.policy.storage_audit_at is not None


def test_a_storage_job_result_refreshes_the_audit_but_a_host_result_does_not(
    session, sent
):
    s = _setup(session)
    prune = jobs.queue_run(session, s.policy, s.nas.id, "prune")
    payload = _result(prune)
    payload["storage_audit"] = [{"code": "export_own", "level": "ok", "params": {}}]
    results.record_result(session, s.nas.id, payload)
    assert json.loads(s.policy.storage_audit)[0]["code"] == "export_own"
    capture = jobs.queue_run(session, s.policy, s.host.id, "capture")
    payload = _result(capture, snapshot="a1")
    payload["storage_audit"] = BAD  # a backed-up host cannot speak for storage
    results.record_result(session, s.host.id, payload)
    assert json.loads(s.policy.storage_audit)[0]["code"] == "export_own"


def test_the_target_summarizes_audits_worst_first(session):
    s = _setup(session)
    s.policy.storage_audit = json.dumps(BAD[:4])
    other = _host(session, fqdn="db.lab")
    session.add(models.BackupPolicy(
        id=__import__("uuid").uuid4(), host_id=other.id, target_id=s.target.id,
        enabled=True, interval_hours=24, keep_last=14, check_interval_days=7,
        quiesce=False, config_version=1, host_acked_version=1, storage_acked_version=1,
        created_at=s.policy.created_at, updated_at=s.policy.updated_at,
        storage_audit=json.dumps([
            {"code": "nfs_local_locks", "level": "error", "params": {}},
            {"code": "append_only_layout", "level": "warning", "params": {}},
        ]),
    ))  # fmt: skip
    session.commit()
    summary = audit.summarize(session, s.target)
    assert summary["nfs_local_locks"]["hosts"] == []  # host-wide: once
    assert sorted(summary["append_only_layout"]["hosts"]) == sorted(
        [str(s.host.id), str(other.id)]
    )
    assert "nfs_server" not in summary  # ok findings are not warnings
    target = views.target_dict(s.target, session)
    tail = [w for w in target["warnings"] if w.startswith("audit_")]
    assert tail == ["audit_export_shared", "audit_nfs_local_locks",
                    "audit_append_only_layout"]  # fmt: skip
    assert target["problem"] is True


def test_a_storage_hosts_audit_outside_any_job_is_stored(session, sent):
    # The agent's storage_reaudit: at start, daily, Request Host Data
    # (production 2026-10-27: an NFSv4 finding two days stale).
    s = _setup(session)
    fresh = [{"code": "nfs_v4", "level": "ok", "params": {}}]
    stored = results.record_storage_audit(
        session, s.nas.id, {"policy_id": str(s.policy.id), "storage_audit": fresh}
    )
    assert stored is True
    assert json.loads(s.policy.storage_audit) == fresh
    assert s.policy.storage_audit_at is not None


def test_an_audit_from_any_other_host_or_policy_is_ignored(session, sent):
    s = _setup(session)
    s.policy.storage_audit = json.dumps(
        [{"code": "nfs_v4", "level": "error", "params": {}}]
    )
    ok = [{"code": "nfs_v4", "level": "ok", "params": {}}]
    # the backed-up host cannot speak for its storage
    assert not results.record_storage_audit(
        session, s.host.id, {"policy_id": str(s.policy.id), "storage_audit": ok}
    )
    # nor can anyone name a policy that does not exist, or no policy at all
    assert not results.record_storage_audit(
        session, s.nas.id, {"policy_id": "00000000-0000-4000-8000-000000000000",
                            "storage_audit": ok}
    )  # fmt: skip
    assert not results.record_storage_audit(session, s.nas.id, {"storage_audit": ok})
    assert json.loads(s.policy.storage_audit)[0]["level"] == "error"  # unchanged
