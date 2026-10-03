# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: a busy server tells connecting agents to spread their first
reports (``initial_report_window_seconds`` in ``registration_success``).

Real database (the per-test SQLite schema), not mocks.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.persistence.models import MessageQueue
from backend.websocket import report_window
from backend.websocket.queue_enums import QueueDirection, QueueStatus

LIMITS = "backend.websocket.report_window._limits"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    report_window.reset()
    monkeypatch.setenv("SYSMANAGE_UVICORN_WORKERS", "1")
    yield
    report_window.reset()


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _queue(db, count, direction=QueueDirection.INBOUND, status=QueueStatus.PENDING):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add_all(
        MessageQueue(id=uuid.uuid4(), message_id=str(uuid.uuid4()),
                     direction=direction, message_type="software_inventory_update",
                     message_data=json.dumps({}), status=status, priority="normal",
                     created_at=now)  # fmt: skip
        for _ in range(count)
    )
    db.commit()


def test_a_quiet_server_says_report_now(db_session):
    with patch(LIMITS, return_value=(50.0, 10.0, 1800.0)):
        assert report_window.suggest(db_session) == 0


def test_a_backlog_spreads_the_reports(db_session):
    _queue(db_session, 500)
    with patch(LIMITS, return_value=(10.0, 0.0, 1800.0)):
        assert report_window.suggest(db_session) == 50  # 500 pending / 10 a second


def test_only_pending_inbound_counts(db_session):
    _queue(db_session, 500, direction=QueueDirection.OUTBOUND)
    _queue(db_session, 500, status=QueueStatus.COMPLETED)
    with patch(LIMITS, return_value=(10.0, 0.0, 1800.0)):
        assert report_window.suggest(db_session) == 0


def test_a_storm_counts_before_its_reports_are_queued(db_session, monkeypatch):
    """The first thousand agents connect before their reports reach the
    queue: recent registrations, on every worker, are work coming."""
    monkeypatch.setenv("SYSMANAGE_UVICORN_WORKERS", "4")
    clock = _Clock()
    with patch(LIMITS, return_value=(50.0, 10.0, 1800.0)):
        windows = [report_window.suggest(db_session, clock) for _ in range(100)]
    assert windows[0] == 0  # one agent: nothing to spread
    assert windows[-1] == 80  # 100 x 4 workers x 10 messages / 50 a second
    assert windows == sorted(windows)


def test_registrations_age_out(db_session):
    clock = _Clock()
    with patch(LIMITS, return_value=(1.0, 10.0, 1800.0)):
        assert report_window.suggest(db_session, clock) == 10
        clock.now += report_window.RECENT_SECONDS + 1
        assert report_window.suggest(db_session, clock) == 10  # only this one


def test_the_window_is_capped(db_session):
    _queue(db_session, 500)
    with patch(LIMITS, return_value=(0.1, 0.0, 120.0)):
        assert report_window.suggest(db_session) == 120


def test_the_count_is_cached(db_session):
    clock = _Clock()
    with patch(LIMITS, return_value=(10.0, 0.0, 1800.0)):
        assert report_window.suggest(db_session, clock) == 0
        _queue(db_session, 500)
        assert report_window.suggest(db_session, clock) == 0  # still cached
        clock.now += report_window.REFRESH_SECONDS
        assert report_window.suggest(db_session, clock) == 50


def test_a_failed_count_means_no_delay(db_session):
    with patch.object(db_session, "execute", side_effect=RuntimeError("down")):
        assert report_window.suggest(db_session) == 0


def test_limits_come_from_the_config():
    conf = {"security": {"agent_connection_limits": {
        "initial_report_drain_per_second": 200,
        "initial_report_messages_per_agent": 5,
        "initial_report_max_window_seconds": 600}}}  # fmt: skip
    with patch("backend.config.config.get_config", return_value=conf):
        assert report_window._limits() == (
            200.0,
            5.0,
            600.0,
        )  # pylint: disable=protected-access


def test_bad_limits_fall_back_to_defaults():
    conf = {"security": {"agent_connection_limits": {
        "initial_report_drain_per_second": "fast"}}}  # fmt: skip
    with patch("backend.config.config.get_config", return_value=conf):
        assert report_window._limits() == (  # pylint: disable=protected-access
            report_window.DEFAULT_DRAIN_PER_SECOND,
            report_window.DEFAULT_MESSAGES_PER_AGENT,
            report_window.DEFAULT_MAX_WINDOW_SECONDS,
        )


async def test_registration_success_carries_the_window(db_session):
    from backend.api.message_handlers_core import (  # pylint: disable=import-outside-toplevel
        _process_approved_system_info,
    )
    from backend.persistence.models import (
        Host,
    )  # pylint: disable=import-outside-toplevel

    host = Host(id=uuid.uuid4(), fqdn="w.example.com", active=True,
                approval_status="approved", host_token="tok")  # fmt: skip
    db_session.add(host)
    db_session.commit()
    _queue(db_session, 500)
    with patch(LIMITS, return_value=(10.0, 0.0, 1800.0)), patch(
        "backend.services.logging_config_service.push_logging_to_host"
    ):
        reply = await _process_approved_system_info(
            db_session, None, host, host.fqdn, {}, "Linux", None, None, True
        )
    assert reply["message_type"] == "registration_success"
    assert reply["initial_report_window_seconds"] == 50


def test_a_faster_server_measures_its_own_drain_rate(db_session, monkeypatch):
    """The 10k run drained 150-200/s against the configured 50: every agent
    got the 30-minute maximum.  The measured rate wins when it is higher."""
    monkeypatch.setenv("SYSMANAGE_UVICORN_WORKERS", "2")
    clock = _Clock()
    _queue(db_session, 600)
    for _ in range(60):  # this worker: 3,000 in the last minute = 50/s
        report_window.record_processed(50, clock)
    assert report_window.measured_drain_rate(clock) == 100.0  # x 2 workers
    with patch(LIMITS, return_value=(10.0, 0.0, 1800.0)):
        assert report_window.suggest(db_session, clock) == 6  # 600 / 100


def test_a_quiet_server_keeps_the_configured_floor(db_session):
    clock = _Clock()
    _queue(db_session, 500)
    report_window.record_processed(1, clock)  # next to nothing measured
    with patch(LIMITS, return_value=(10.0, 0.0, 1800.0)):
        assert report_window.suggest(db_session, clock) == 50


def test_old_drain_counts_age_out():
    clock = _Clock()
    report_window.record_processed(600, clock)
    clock.now += report_window.RECENT_SECONDS + 1
    assert report_window.measured_drain_rate(clock) == 0.0
