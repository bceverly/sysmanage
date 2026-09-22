# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ad-hoc fleet-wide live queries — Phase 21.1 S5.

The behaviour worth pinning is the BOUND. A live query is one statement typed
at a console and pointed at a fleet, so the failure mode it must never have is
the one fleet jobs were built to replace: four thousand hosts dispatched at
once because somebody pressed enter.

Everything else here — results, grading, "not covered is not empty" — is S4's,
reused deliberately rather than reimplemented, which is why a live query's
targets are ``QueryPackRun`` rows.
"""

import uuid
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import query_pack_live as live_svc


class FakeHost:
    def __init__(self):
        self.id = uuid.uuid4()
        self.platform = "Linux"
        self.agent_capabilities = None


def hosts(count):
    return [FakeHost() for _ in range(count)]


@pytest.fixture
def engine_present():
    """Stand in for the licensed engine's bounding maths."""
    with patch.object(
        live_svc.shim, "validate_live_query", return_value=[]
    ), patch.object(
        live_svc.shim, "clamp_concurrency", side_effect=lambda v: int(v or 20)
    ), patch.object(
        live_svc.shim, "clamp_timeout", side_effect=lambda v: int(v or 120)
    ), patch.object(
        live_svc.shim,
        "next_batch_size",
        side_effect=lambda c, f, w: max(0, min(int(c) - int(f), int(w))),
    ), patch.object(
        live_svc.shim,
        "live_status_after",
        side_effect=lambda t, f: "completed" if f >= t else "running",
    ), patch.object(
        live_svc.dispatch, "build_payload", return_value={"queries": [{"name": "live"}]}
    ), patch.object(
        live_svc.dispatch, "queue_run", return_value="cmd-1"
    ):
        yield


def _add_hosts(session, fake_hosts):
    """The service loads Host rows to dispatch; give it real ones."""
    for h in fake_hosts:
        session.add(
            models.Host(id=h.id, fqdn=f"h{h.id}", active=True, platform="Linux")
        )
    session.flush()


class TestBoundedFanOut:
    def test_only_concurrency_targets_go_out_at_once(self, session, engine_present):
        """THE test. 100 hosts, concurrency 10 — ten dispatched, ninety
        waiting. Unbounded fan-out is what this slice exists to prevent."""
        fleet = hosts(100)
        _add_hosts(session, fleet)
        live, problems = live_svc.create(session, "SELECT 1", fleet, concurrency=10)
        assert problems == []
        live_svc.advance(session, live)

        runs = (
            session.query(models.QueryPackRun)
            .filter(models.QueryPackRun.live_query_id == live.id)
            .all()
        )
        in_flight = [r for r in runs if r.status == models.RUN_STATUS_PENDING]
        waiting = [r for r in runs if r.status == models.RUN_STATUS_WAITING]
        assert len(in_flight) == 10
        assert len(waiting) == 90

    def test_every_target_exists_immediately(self, session, engine_present):
        """The operator sees "0 of 100" at once. A total that grows as
        dispatch proceeds is indistinguishable from a stalled fan-out."""
        fleet = hosts(100)
        _add_hosts(session, fleet)
        live, _ = live_svc.create(session, "SELECT 1", fleet, concurrency=10)
        assert live.total_targets == 100
        assert (
            session.query(models.QueryPackRun)
            .filter(models.QueryPackRun.live_query_id == live.id)
            .count()
            == 100
        )

    def test_a_settled_target_frees_a_slot(self, session, engine_present):
        fleet = hosts(20)
        _add_hosts(session, fleet)
        live, _ = live_svc.create(session, "SELECT 1", fleet, concurrency=5)
        live_svc.advance(session, live)

        first = (
            session.query(models.QueryPackRun)
            .filter(
                models.QueryPackRun.live_query_id == live.id,
                models.QueryPackRun.status == models.RUN_STATUS_PENDING,
            )
            .first()
        )
        first.status = models.RUN_STATUS_SUCCESS
        session.flush()

        live_svc.advance(session, live)
        in_flight = (
            session.query(models.QueryPackRun)
            .filter(
                models.QueryPackRun.live_query_id == live.id,
                models.QueryPackRun.status == models.RUN_STATUS_PENDING,
            )
            .count()
        )
        assert in_flight == 5

    def test_no_engine_dispatches_nothing(self, session):
        """A server that has lost its licence mid-query must STOP, not fall
        back to the unbounded behaviour."""
        fleet = hosts(10)
        _add_hosts(session, fleet)
        with patch.object(
            live_svc.shim, "validate_live_query", return_value=[]
        ), patch.object(
            live_svc.shim, "clamp_concurrency", return_value=1
        ), patch.object(
            live_svc.shim, "clamp_timeout", return_value=120
        ):
            live, _ = live_svc.create(session, "SELECT 1", fleet)
        with patch.object(
            live_svc.shim, "next_batch_size", return_value=0
        ), patch.object(live_svc.shim, "live_status_after", return_value="running"):
            assert live_svc.advance(session, live) == 0


class TestValidation:
    def test_an_invalid_statement_writes_nothing(self, session):
        """A stored, targeted query can be dispatched a moment later by the
        advance path — and the SQL is operator-typed."""
        with patch.object(
            live_svc.shim, "validate_live_query", return_value=["a query may only read"]
        ):
            live, problems = live_svc.create(session, "DROP TABLE users", hosts(3))
        assert live is None and problems
        assert session.query(models.QueryPackLiveQuery).count() == 0


class TestDegenerateTargets:
    def test_targeting_nothing_completes_rather_than_hanging(
        self, session, engine_present
    ):
        """A tag matching no hosts is legitimate. The honest answer is an
        empty COMPLETED query, not a running one nothing can finish."""
        live, problems = live_svc.create(session, "SELECT 1", [])
        assert problems == []
        live_svc.advance(session, live)
        assert live.total_targets == 0
        assert live.status == models.LIVE_COMPLETED


class TestTimeouts:
    def test_a_silent_host_is_settled_so_the_wave_can_move(
        self, session, engine_present
    ):
        """One unreachable host would otherwise hold its slot forever and
        every host behind it would never be asked."""
        fleet = hosts(3)
        _add_hosts(session, fleet)
        live, _ = live_svc.create(
            session, "SELECT 1", fleet, concurrency=1, timeout_seconds=10
        )
        live_svc.advance(session, live)

        stuck = (
            session.query(models.QueryPackRun)
            .filter(models.QueryPackRun.status == models.RUN_STATUS_PENDING)
            .one()
        )
        stuck.started_at = live_svc.utcnow() - live_svc.timedelta(seconds=60)
        session.flush()

        assert live_svc.sweep_timeouts(session, live) == 1
        session.refresh(stuck)
        assert stuck.status == models.RUN_STATUS_FAILED
        assert "no answer" in stuck.error


class TestCancel:
    def test_cancel_stops_dispatch_but_does_not_lie_about_hosts_in_flight(
        self, session, engine_present
    ):
        """A command already on a host's queue cannot be recalled. Reporting
        those hosts as cancelled would claim something untrue."""
        fleet = hosts(10)
        _add_hosts(session, fleet)
        live, _ = live_svc.create(session, "SELECT 1", fleet, concurrency=3)
        live_svc.advance(session, live)

        not_dispatched = live_svc.cancel(session, live)
        assert not_dispatched == 7
        assert live.status == models.LIVE_CANCELED
        still_out = (
            session.query(models.QueryPackRun)
            .filter(
                models.QueryPackRun.live_query_id == live.id,
                models.QueryPackRun.status == models.RUN_STATUS_PENDING,
            )
            .count()
        )
        assert still_out == 3

    def test_a_cancelled_query_releases_no_more_waves(self, session, engine_present):
        fleet = hosts(10)
        _add_hosts(session, fleet)
        live, _ = live_svc.create(session, "SELECT 1", fleet, concurrency=3)
        live_svc.advance(session, live)
        live_svc.cancel(session, live)
        assert live_svc.advance(session, live) == 0


class TestNotCoveredIsTrackedSeparately:
    def test_a_host_that_cannot_answer_is_not_counted_as_a_failure(
        self, session, engine_present
    ):
        """Folding the two together would make a Windows box look broken for
        lacking ``mounts``."""
        fleet = hosts(2)
        _add_hosts(session, fleet)
        live, _ = live_svc.create(session, "SELECT 1", fleet, concurrency=2)
        live_svc.advance(session, live)

        runs = (
            session.query(models.QueryPackRun)
            .filter(models.QueryPackRun.live_query_id == live.id)
            .all()
        )
        runs[0].status = models.RUN_STATUS_PARTIAL
        runs[0].queries_not_covered = 1
        runs[1].status = models.RUN_STATUS_FAILED
        session.flush()

        live_svc.advance(session, live)
        assert live.not_covered_count == 1
        assert live.failed_count == 1
