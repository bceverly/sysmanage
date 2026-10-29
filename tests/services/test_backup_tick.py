# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The backup scheduler (Phase 24): configure first, captures when due and
within the window and the target's cap, storage upkeep on the storage host
only, stuck runs failed loudly, and a clean no-op with nothing set up."""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_tick as tick
from tests.services.test_backup_results import EQUIPPED, _host, _setup

NOW = datetime(2026, 10, 20, 3, 0)


@pytest.fixture(autouse=True)
def no_spread():
    with patch.object(tick, "host_offset", return_value=0.0):
        yield


@pytest.fixture
def sent():
    calls = []

    def fake(_db, host_id, command_type, parameters):
        calls.append(
            (str(host_id), getattr(command_type, "value", command_type), parameters)
        )
        return str(uuid.uuid4())

    with patch.object(jobs.config_mgmt_dispatch, "queue_command", side_effect=fake):
        yield calls


def _actions(sent):
    return [(c, p.get("action") or p.get("role")) for _h, c, p in sent]


def _finish(session, policy, host_id, action, status="ok", at=NOW, result=None):
    run = models.BackupRun(
        id=uuid.uuid4(), policy_id=policy.id, host_id=host_id, action=action,
        status=status, queued_at=at, finished_at=at,
        result=json.dumps(result or {}),
    )  # fmt: skip
    session.add(run)
    session.flush()
    return run


def test_nothing_set_up_is_a_clean_no_op(session, sent):
    _host(session)
    assert tick.reconcile(session, NOW) == 0
    assert sent == []


def test_unconfigured_hosts_get_their_job_files_first(session, sent):
    s = _setup(session, storage_acked=0)
    s.policy.host_acked_version = 0
    tick.reconcile(session, NOW)
    assert _actions(sent) == [
        ("backup_configure", "host"),
        ("backup_configure", "storage"),
    ]
    assert {h for h, _c, _p in sent} == {str(s.host.id), str(s.nas.id)}
    tick.reconcile(session, NOW)  # pending: not re-sent
    assert len(sent) == 2


def test_a_policy_off_schedule_is_still_configured_but_never_captured(session, sent):
    # "Back up now" needs the job files even when nothing is scheduled
    # (found in the 24.0 lab, 2026-10-20: such a host was never configured).
    s = _setup(session, storage_acked=0)
    s.policy.host_acked_version = 0
    s.policy.enabled = False
    tick.reconcile(session, NOW)
    assert _actions(sent) == [
        ("backup_configure", "host"),
        ("backup_configure", "storage"),
    ]
    s.policy.host_acked_version = s.policy.storage_acked_version = 1
    sent.clear()
    tick.reconcile(session, NOW)
    assert ("backup_run", "capture") not in _actions(sent)


def test_a_manual_capture_off_schedule_is_still_sealed(session, sent):
    s = _setup(session)
    s.policy.enabled = False
    _finish(session, s.policy, s.host.id, "capture", at=NOW - timedelta(minutes=5))
    tick.reconcile(session, NOW)
    assert _actions(sent)[0] in (("backup_run", "seal"), ("backup_run", "prune"))


def test_configure_now_sends_job_files_without_capturing(session, sent):
    s = _setup(session, storage_acked=0)
    s.policy.host_acked_version = 0
    tick.configure_now(session)
    assert _actions(sent) == [
        ("backup_configure", "host"),
        ("backup_configure", "storage"),
    ]
    tick.configure_now(session)  # pending: not re-sent
    assert len(sent) == 2


def test_configure_now_with_no_target_is_a_no_op(session, sent):
    _host(session)
    tick.configure_now(session)
    assert sent == []


def test_a_never_backed_up_host_is_estimated_then_captured(session, sent):
    s = _setup(session)
    tick.reconcile(session, NOW)
    assert ("backup_run", "estimate") in _actions(sent)
    assert ("backup_run", "capture") not in _actions(sent)
    session.query(models.BackupRun).filter_by(action="estimate").delete()
    _finish(session, s.policy, s.host.id, "estimate", at=NOW)
    tick.reconcile(session, NOW + timedelta(minutes=5))
    assert ("backup_run", "capture") in _actions(sent)


def test_a_capture_waits_for_its_interval(session, sent):
    s = _setup(session)
    _finish(session, s.policy, s.host.id, "capture", at=NOW - timedelta(hours=2))
    _finish(session, s.policy, s.nas.id, "prune", at=NOW - timedelta(hours=1))
    _finish(session, s.policy, s.nas.id, "check", at=NOW)
    assert tick.reconcile(session, NOW) == 0
    assert tick.reconcile(session, NOW + timedelta(hours=23)) == 1


def test_busy_and_failed_retry_sooner(session):
    s = _setup(session)
    _finish(session, s.policy, s.host.id, "capture", "busy", at=NOW)
    assert tick.capture_due_at(session, s.policy) == NOW + tick.BUSY_RETRY
    _finish(
        session, s.policy, s.host.id, "capture", "failed", at=NOW + timedelta(minutes=1)
    )
    assert tick.capture_due_at(session, s.policy) == NOW + timedelta(minutes=61)


def test_the_window_is_honored_across_midnight():
    policy = models.BackupPolicy(window_start_hour=22)
    assert tick.in_window(policy, NOW.replace(hour=23))
    assert tick.in_window(policy, NOW.replace(hour=3))
    assert not tick.in_window(policy, NOW.replace(hour=4))
    assert not tick.in_window(policy, NOW.replace(hour=21))


def test_spread_is_bounded_by_a_quarter_interval():
    with patch.object(tick, "host_offset", return_value=0.5):
        assert tick.spread(
            models.BackupPolicy(host_id=uuid.uuid4(), interval_hours=1)
        ) == timedelta(minutes=7.5)
        assert tick.spread(
            models.BackupPolicy(host_id=uuid.uuid4(), interval_hours=24)
        ) == timedelta(minutes=30)


def test_the_target_cap_holds_captures_back(session, sent):
    s = _setup(session)
    s.target.max_concurrent = 1
    other = _host(session, fqdn="b.lab")
    session.add(models.BackupPolicy(
        id=uuid.uuid4(), host_id=other.id, target_id=s.target.id, enabled=True,
        interval_hours=24, keep_last=3, check_interval_days=7, config_version=1,
        host_acked_version=1, storage_acked_version=1, created_at=NOW, updated_at=NOW,
    ))  # fmt: skip
    _finish(session, s.policy, s.host.id, "estimate", at=NOW)
    session.commit()
    tick.reconcile(session, NOW)
    assert [a for a in _actions(sent) if a[1] == "capture"] == [
        ("backup_run", "capture")
    ]


def test_upkeep_seals_then_prunes_on_the_storage_host(session, sent):
    s = _setup(session, seal_mode="zfs_snapshot")
    _finish(session, s.policy, s.host.id, "capture", at=NOW - timedelta(hours=1))
    tick.reconcile(session, NOW)
    storage = [(h, p["action"]) for h, _c, p in sent if p.get("action") != "capture"]
    assert storage == [(str(s.nas.id), "seal")]
    _finish(session, s.policy, s.nas.id, "seal", at=NOW)
    session.query(models.BackupRun).filter_by(action="seal", status="queued").delete()
    tick.reconcile(session, NOW + timedelta(minutes=5))
    assert sent[-1][2]["action"] == "prune" and sent[-1][0] == str(s.nas.id)


def test_check_when_due(session, sent):
    s = _setup(session)
    _finish(session, s.policy, s.host.id, "capture", at=NOW - timedelta(hours=1))
    _finish(session, s.policy, s.nas.id, "prune", at=NOW)
    assert tick._upkeep_action(session, s.policy, s.target, NOW) == "check"
    _finish(session, s.policy, s.nas.id, "check", "different", at=NOW)
    assert tick._upkeep_action(session, s.policy, s.target, NOW) is None
    later = NOW + timedelta(days=7)
    assert tick._upkeep_action(session, s.policy, s.target, later) == "check"


def test_a_busy_storage_job_waits_before_retrying(session):
    s = _setup(session)
    _finish(session, s.policy, s.nas.id, "check", "busy", at=NOW)
    assert not tick._storage_retry_ok(
        session, s.policy, "check", NOW + timedelta(minutes=10)
    )
    assert tick._storage_retry_ok(
        session, s.policy, "check", NOW + timedelta(minutes=30)
    )


def test_an_incomplete_protect_runs_again_a_few_times(session, sent):
    """Production, nextcloud, 2026-10-29: protect ran a second after the
    capture and the client still held its newest files."""
    s = _setup(session)
    s.policy.storage_protects = True
    _finish(session, s.policy, s.host.id, "capture", at=NOW - timedelta(hours=1))
    _finish(session, s.policy, s.nas.id, "prune", at=NOW - timedelta(minutes=50))
    _finish(session, s.policy, s.nas.id, "check", at=NOW - timedelta(minutes=50))
    _finish(session, s.policy, s.nas.id, "protect", "incomplete", at=NOW)
    assert tick._upkeep_action(session, s.policy, s.target, NOW) is None  # too soon
    later = NOW + tick.PROTECT_RETRY
    assert tick._storage_upkeep(session, s.policy, s.target, later) == "protect"
    queued = jobs.latest_run(session, s.policy.id, "protect")
    assert json.loads(queued.parameters)["chain"] is False
    assert sent[-1][0] == str(s.nas.id) and sent[-1][2]["action"] == "protect"
    queued.status, queued.finished_at = "failed", later
    _finish(session, s.policy, s.nas.id, "protect", "incomplete",
            at=later + timedelta(minutes=1))  # fmt: skip
    # Three in a row without an ok: no more.
    assert (
        tick._upkeep_action(session, s.policy, s.target, NOW + timedelta(hours=2))
        is None
    )


def test_a_protect_that_succeeded_or_is_off_is_left_alone(session):
    s = _setup(session)
    _finish(session, s.policy, s.nas.id, "protect", "incomplete", at=NOW)
    assert not tick._protect_again(session, s.policy, NOW + timedelta(hours=1))
    s.policy.storage_protects = True
    _finish(session, s.policy, s.nas.id, "protect", "ok", at=NOW + timedelta(minutes=1))
    assert not tick._protect_again(session, s.policy, NOW + timedelta(hours=1))


def test_an_unequipped_host_is_skipped(session, sent):
    s = _setup(session)
    s.host.agent_capabilities = json.dumps(
        {"capabilities": [], "unavailable": {"backup": "missing_tool"}}
    )
    session.commit()
    assert tick.reconcile(session, NOW) == 0 and sent == []


def test_no_storage_host_means_no_upkeep_but_captures_continue(session, sent):
    s = _setup(session)
    s.nas.agent_capabilities = None
    _finish(session, s.policy, s.host.id, "estimate", at=NOW)
    session.commit()
    tick.reconcile(session, NOW)
    assert _actions(sent) == [("backup_run", "capture")]


def test_stuck_runs_are_failed(session):
    s = _setup(session)
    old = models.BackupRun(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, action="capture",
        status="running", queued_at=NOW - timedelta(hours=13),
    )  # fmt: skip
    session.add(old)
    session.flush()
    assert tick.fail_stuck(session, NOW) == 1
    assert old.status == "failed" and "12 hours" in old.message


def test_every_database_and_a_failure_is_contained():
    good, bad = MagicMock(), MagicMock()

    def reconcile(db):
        if db is bad:
            raise RuntimeError("down")
        return 2

    with patch.object(
        tick,
        "iter_host_databases",
        return_value=iter([("a", None, good), ("b", "t", bad)]),
    ), patch.object(tick, "reconcile", side_effect=reconcile):
        assert tick.run_one_tick() == 2
    good.commit.assert_called_once()
    bad.rollback.assert_called_once()
    assert good.close.called and bad.close.called


def test_community_always_starts():
    with patch.object(
        tick, "singleton_task", return_value="task"
    ) as start, patch.object(tick, "_TASK", None), patch.object(
        tick, "backup_tick_service", MagicMock()
    ):
        assert tick.start_if_licensed() == "task"
    start.assert_called_once()


def test_equipped_fixture_is_the_backup_group():
    assert "backup" in json.loads(EQUIPPED)["capabilities"]


def test_a_moved_host_gets_its_storage_jobs_re_sent(session, sent):
    s = _setup(session)
    s.host.ipv4 = "192.168.4.196"
    first = jobs.queue_configure(session, s.policy, s.target, s.host, "storage")
    first.status = "ok"  # acknowledged
    assert s.policy.storage_client_address == "192.168.4.196"
    sent.clear()
    s.policy.storage_acked_version = s.policy.config_version
    tick.reconcile(session, NOW)
    assert ("backup_configure", "storage") not in _actions(sent)  # unchanged
    s.host.ipv4 = "192.168.4.200"
    version = s.policy.config_version
    tick.reconcile(session, NOW)
    assert s.policy.config_version == version + 1
    storage = [p for _h, c, p in sent if p.get("role") == "storage"]
    assert storage[-1]["target"]["client_address"] == "192.168.4.200"
