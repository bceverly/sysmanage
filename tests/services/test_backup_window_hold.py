# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backups and maintenance windows (ROADMAP 24.6): a capture a closed window
holds is waiting, not stuck and not "backing up".  Timing from the queue time
failed held runs after twelve hours and queued another, so the host got both
when the window opened (2026-10-27)."""

import uuid
from datetime import datetime, timedelta

from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_tick as tick
from backend.services import backup_views as views
from backend.services import queue_clock
from backend.services.maintenance_window_service import DEFERRED_MARKER
from tests.services.test_backup_results import _setup

NOW = datetime(2026, 10, 20, 3, 0)


def _run(session, s, status="queued", queued_at=NOW, action="capture"):
    run = models.BackupRun(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id, action=action,
        status=status, queued_at=queued_at, command_id=str(uuid.uuid4()),
    )  # fmt: skip
    session.add(run)
    session.flush()
    return run


def _queue(session, run, status="pending", started_at=None, held=False):
    session.add(
        models.MessageQueue(
            host_id=run.host_id, message_id=run.command_id, direction="outbound",
            message_type="command", message_data="{}", status=status,
            priority="normal", created_at=run.queued_at, started_at=started_at,
            error_message=DEFERRED_MARKER if held else None,
        )
    )  # fmt: skip
    session.flush()


def _good_capture(session, s, at):
    session.add(
        models.BackupRun(
            id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id,
            action="capture", status="ok", queued_at=at, finished_at=at,
        )
    )  # fmt: skip
    session.flush()


def test_a_run_held_by_a_window_is_not_stuck(session):
    s = _setup(session)
    run = _run(session, s, queued_at=NOW - timedelta(days=3))
    _queue(session, run, held=True)
    assert tick.fail_stuck(session, NOW) == 0
    assert run.status == "queued"


def test_a_run_waiting_for_its_agent_is_not_stuck(session):
    s = _setup(session)
    run = _run(session, s, queued_at=NOW - timedelta(days=1))
    _queue(session, run)
    assert tick.fail_stuck(session, NOW) == 0


def test_twelve_hours_count_from_the_send(session):
    s = _setup(session)
    run = _run(session, s, status="running", queued_at=NOW - timedelta(days=3))
    _queue(session, run, status="sent", started_at=NOW - timedelta(hours=2))
    assert tick.fail_stuck(session, NOW) == 0
    assert tick.fail_stuck(session, NOW + timedelta(hours=11)) == 1
    assert run.status == "failed"


def test_a_run_whose_queue_row_is_gone_counts_from_the_queue_time(session):
    s = _setup(session)
    _run(session, s, status="running", queued_at=NOW - timedelta(hours=13))
    assert tick.fail_stuck(session, NOW) == 1


def test_a_held_run_is_never_queued_twice(session):
    s = _setup(session)
    run = _run(session, s, queued_at=NOW - timedelta(days=3))
    _queue(session, run, held=True)
    tick.fail_stuck(session, NOW)
    assert jobs.pending(session, s.policy.id, "capture")


def test_a_held_capture_reads_waiting_for_window(session):
    s = _setup(session)
    _good_capture(session, s, NOW - timedelta(hours=20))
    run = _run(session, s, queued_at=NOW - timedelta(hours=1))
    _queue(session, run, held=True)
    row = views.host_status(session, s.host, NOW)
    assert row["status"] == "waiting_window" and row["capture_held"] is True


def test_a_sent_capture_reads_backing_up(session):
    s = _setup(session)
    _good_capture(session, s, NOW - timedelta(hours=20))
    run = _run(session, s, status="running")
    _queue(session, run, status="sent", started_at=NOW)
    row = views.host_status(session, s.host, NOW)
    assert row["status"] == "running" and row["capture_held"] is False


def test_an_overdue_host_stays_overdue_while_its_capture_is_held(session):
    """A window that never opens must not hide an overdue host."""
    s = _setup(session)
    _good_capture(session, s, NOW - timedelta(days=5))
    run = _run(session, s, queued_at=NOW - timedelta(hours=1))
    _queue(session, run, held=True)
    row = views.host_status(session, s.host, NOW)
    assert row["status"] == "overdue" and row["capture_held"] is True
    assert views.ATTENTION_STATUSES.count("waiting_window") == 0


def test_the_clock_rules():
    sent_at = NOW - timedelta(minutes=5)
    assert queue_clock.clock_start(None, NOW) == NOW
    sent = queue_clock.Delivery(sent_at=sent_at, waiting=False, held=False)
    assert queue_clock.clock_start(sent, NOW) == sent_at
    waiting = queue_clock.Delivery(sent_at=None, waiting=True, held=True)
    assert queue_clock.clock_start(waiting, NOW) is None
    expired = queue_clock.Delivery(sent_at=None, waiting=False, held=False)
    assert queue_clock.clock_start(expired, NOW) == NOW


# --- Pro+ key rotation from the tick (24.6 S5) ---------------------------------


class _Engine:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def rotate_due(self, db, target, policies, now=None, logger=None):
        self.calls.append([p.id for p in policies])
        if self.fail:
            raise RuntimeError("engine bug")
        return len(policies)


def test_the_tick_hands_only_encrypted_policies_to_the_engine(session, monkeypatch):
    s = _setup(session)
    engine = _Engine()
    monkeypatch.setattr(tick, "_encryption_engine", lambda: engine)
    target = jobs.the_target(session)
    assert tick.rotate_keys(session, target, NOW) == 0  # nothing encrypted
    assert engine.calls == []
    s.policy.encrypt_public_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n"
    assert tick.rotate_keys(session, target, NOW) == 1
    assert engine.calls == [[s.policy.id]]


def test_no_engine_no_rotation_and_an_engine_failure_never_stops_the_tick(
    session, monkeypatch
):
    s = _setup(session)
    s.policy.encrypt_public_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nk\n"
    target = jobs.the_target(session)
    monkeypatch.setattr(tick, "_encryption_engine", lambda: None)
    assert tick.rotate_keys(session, target, NOW) == 0
    monkeypatch.setattr(tick, "_encryption_engine", lambda: _Engine(fail=True))
    assert tick.rotate_keys(session, target, NOW) == 0  # logged, not raised
    tick.reconcile(session, NOW)  # and the pass itself still runs
