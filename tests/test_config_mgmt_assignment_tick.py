# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The assignment tick (Phase 20.1).

Until this loop existed, an assignment was decoration: you could bind a
profile to a host with a cron expression and nothing would ever run it.

The behaviours worth pinning are the ones that only show up at 3am:

* **No catch-up storm.** A schedule missed while the server was down fires
  ONCE, not once per occurrence slept through. Replaying a week of nightly
  applies across a fleet is far worse than a late apply.
* **Per-host isolation.** One host that cannot take the command must not stop
  the rest of the fleet from getting the profile.
* **The cursor always advances.** A target that matched nothing, or a profile
  that cannot be dispatched, still moves ``last_applied_at`` -- otherwise the
  same failure is re-decided every 60 seconds forever.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import config_mgmt_assignment_tick as tick

NOW = datetime(2026, 8, 28, 4, 0, 0)
PROFILE_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
HOST_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


class _Cron:
    """Stands in for automation_engine's cron parser."""

    def __init__(self, delta=timedelta(days=1), raises=False):
        self.delta = delta
        self.raises = raises
        self.calls = []

    def next_run_from_cron(self, expr, anchor):
        self.calls.append((expr, anchor))
        if self.raises:
            raise ValueError("bad cron")
        return anchor + self.delta


def assignment(**over):
    base = {
        "id": uuid.uuid4(),
        "profile_id": PROFILE_ID,
        "host_id": HOST_ID,
        "tag_id": None,
        "site_id": None,
        "enabled": True,
        "schedule": "0 3 * * *",
        "check_mode": True,
        # Yesterday: one occurrence is due, not a week of them.
        "last_applied_at": NOW - timedelta(days=1, hours=2),
        "created_at": NOW - timedelta(days=30),
    }
    base.update(over)
    return SimpleNamespace(**base)


class TestDueness:
    def test_an_assignment_past_its_next_occurrence_is_due(self):
        assert tick._is_due(_Cron(), assignment(), NOW) is True

    def test_one_applied_moments_ago_is_not_due(self):
        row = assignment(last_applied_at=NOW - timedelta(minutes=1))
        assert tick._is_due(_Cron(), row, NOW) is False

    def test_dueness_is_anchored_on_the_last_apply_not_the_clock(self):
        # This is what stops a catch-up storm: the next occurrence is measured
        # from when it last ran, and firing sets that to now, so a long
        # outage produces exactly one apply.
        cron = _Cron()
        row = assignment(last_applied_at=NOW - timedelta(days=14))
        tick._is_due(cron, row, NOW)
        assert cron.calls[0][1] == row.last_applied_at

    def test_a_never_applied_assignment_anchors_on_creation(self):
        cron = _Cron()
        row = assignment(last_applied_at=None)
        tick._is_due(cron, row, NOW)
        assert cron.calls[0][1] == row.created_at

    def test_an_unusable_cron_is_skipped_not_raised(self):
        # One bad expression must not stop every other assignment firing.
        assert tick._is_due(_Cron(raises=True), assignment(), NOW) is False

    def test_an_aware_cron_result_is_compared_correctly(self):
        # Rows are naive-UTC; comparing them to an aware value raises, and the
        # whole tick would die on one assignment.
        cron = _Cron()
        cron.next_run_from_cron = lambda _e, _a: datetime(
            2026, 8, 27, 3, 0, 0, tzinfo=timezone.utc
        )
        assert tick._is_due(cron, assignment(), NOW) is True


class _HostQuery:
    def __init__(self, hosts):
        self._hosts = hosts
        self.joined = False

    def filter(self, *_a, **_k):
        return self

    def join(self, *_a, **_k):
        self.joined = True
        return self

    def all(self):
        return list(self._hosts)


class _Session:
    def __init__(self, hosts=(), assignments=(), profile=None):
        self.hosts = list(hosts)
        self.assignments = list(assignments)
        self.profile = profile
        self.committed = 0
        self.rolled_back = 0
        self.closed = False
        self.host_query = None

    def query(self, entity):
        name = getattr(entity, "__name__", "")
        if name == "Host":
            self.host_query = _HostQuery(self.hosts)
            return self.host_query
        return _RowQuery(self, name)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


class _RowQuery:
    def __init__(self, session, name):
        self._session = session
        self._name = name

    def join(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def all(self):
        return list(self._session.assignments)

    def first(self):
        return self._session.profile


def host(active=True, host_id=None):
    return SimpleNamespace(id=host_id or HOST_ID, fqdn="h.invalid", active=active)


def profile(**over):
    base = {
        "id": PROFILE_ID,
        "name": "baseline",
        "engine": "ansible-core",
        "content": "- hosts: all\n",
        "is_active": True,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _run(session, cron=None, engines_loaded=True, queued_ok=True, dispatched=None):
    """Drive one tick against a fake session."""
    mods = {
        "config_management_engine": object() if engines_loaded else None,
        "automation_engine": cron if cron is not None else _Cron(),
    }
    calls = [] if dispatched is None else dispatched

    def fake_dispatch(_db, host_row, parameters):
        calls.append((host_row.id, parameters))
        return queued_ok

    sessions = session if isinstance(session, list) else [session]

    def fake_iter():
        for i, one in enumerate(sessions):
            yield (f"db{i}", None, one)

    with patch.object(
        tick.module_loader, "get_module", lambda name: mods.get(name)
    ), patch.object(tick, "iter_host_databases", fake_iter), patch.object(
        tick, "_dispatch_one", fake_dispatch
    ), patch.object(
        tick,
        "datetime",
        SimpleNamespace(now=lambda _tz: NOW.replace(tzinfo=timezone.utc)),
    ):
        return tick.run_one_tick(), calls


class TestDispatchOne:
    """The enqueue itself -- TestTick stubs _dispatch_one, so without this the
    only code that actually builds the command message goes untested."""

    def test_the_queue_row_carries_the_envelope_id_so_results_correlate(self):
        # REGRESSION (2026-08-28). A scheduled check-mode run whose result
        # cannot be correlated produces no run row and therefore no drift
        # finding: the schedule appears to work and the dashboard stays empty.
        # That is exactly what a real round trip found.
        queued = {}

        class FakeQueue:
            def enqueue_message(self, **kwargs):
                queued.update(kwargs)

        with patch.object(tick, "QueueOperations", FakeQueue):
            assert tick._dispatch_one(None, host(), {"profile_name": "baseline"})

        assert queued["message_id"] == queued["message_data"]["message_id"]

    def test_a_host_that_refuses_the_command_is_reported_not_raised(self):
        class FakeQueue:
            def enqueue_message(self, **_kwargs):
                raise RuntimeError("agent cannot run playbooks")

        with patch.object(tick, "QueueOperations", FakeQueue):
            assert tick._dispatch_one(None, host(), {}) is False


class TestTick:
    def test_unlicensed_is_inert_not_an_error(self):
        session = _Session()
        summary, _ = _run(session, engines_loaded=False)
        assert summary["due"] == 0
        assert session.committed == 0

    def test_without_a_cron_engine_nothing_is_guessed_at(self):
        # Firing everything would be worse than firing nothing.
        mods = {"config_management_engine": object(), "automation_engine": None}
        with patch.object(tick.module_loader, "get_module", lambda n: mods.get(n)):
            summary = tick.run_one_tick()
        assert summary["no_cron_engine"] is True
        assert summary["due"] == 0

    def test_a_due_assignment_queues_for_its_host(self):
        session = _Session(
            hosts=[host()], assignments=[assignment()], profile=profile()
        )
        summary, calls = _run(session)
        assert summary["due"] == 1
        assert summary["queued"] == 1
        assert calls[0][0] == HOST_ID

    def test_the_queued_parameters_carry_the_profile_linkage(self):
        session = _Session(
            hosts=[host()], assignments=[assignment()], profile=profile()
        )
        _, calls = _run(session)
        params = calls[0][1]
        assert params["profile_id"] == str(PROFILE_ID)
        assert params["profile_name"] == "baseline"
        assert params["check_mode"] is True
        assert params["profile"] == {"playbook": "- hosts: all\n"}

    def test_firing_advances_the_cursor_so_it_cannot_re_fire(self):
        row = assignment()
        session = _Session(hosts=[host()], assignments=[row], profile=profile())
        _run(session)
        assert row.last_applied_at == NOW
        assert session.committed == 1

    def test_a_target_matching_no_hosts_still_advances_the_cursor(self):
        # Otherwise an empty tag is re-evaluated every 60 seconds forever.
        row = assignment()
        session = _Session(hosts=[], assignments=[row], profile=profile())
        summary, calls = _run(session)
        assert calls == []
        assert summary["due"] == 1
        assert row.last_applied_at == NOW

    def test_a_host_that_cannot_take_it_is_counted_not_fatal(self):
        session = _Session(
            hosts=[host(), host(host_id=uuid.uuid4())],
            assignments=[assignment()],
            profile=profile(),
        )
        summary, _ = _run(session, queued_ok=False)
        assert summary["queued"] == 0
        assert summary["skipped_hosts"] == 2

    def test_an_undispatchable_profile_advances_rather_than_looping(self):
        # A stored DSC body that is not JSON produces the same failure every
        # minute; re-deciding it forever just floods the log.
        row = assignment()
        session = _Session(
            hosts=[host()],
            assignments=[row],
            profile=profile(engine="dsc", content="{not json"),
        )
        summary, calls = _run(session)
        assert calls == []
        assert row.last_applied_at == NOW
        assert summary["queued"] == 0

    def test_a_not_due_assignment_neither_queues_nor_commits(self):
        row = assignment(last_applied_at=NOW - timedelta(minutes=1))
        session = _Session(hosts=[host()], assignments=[row], profile=profile())
        summary, calls = _run(session)
        assert summary["due"] == 0
        assert calls == []
        assert session.committed == 0
        assert row.last_applied_at != NOW

    def test_the_session_is_always_closed(self):
        session = _Session(
            hosts=[host()], assignments=[assignment()], profile=profile()
        )
        _run(session)
        assert session.closed is True


class TestHostResolution:
    def test_a_host_target_selects_that_host(self):
        session = _Session(hosts=[host()])
        assert tick._hosts_for(session, assignment()) == session.hosts

    def test_a_tag_target_joins_through_host_tags(self):
        session = _Session(hosts=[host()])
        tick._hosts_for(session, assignment(host_id=None, tag_id=uuid.uuid4()))
        assert session.host_query.joined is True

    def test_a_site_target_does_not_need_a_join(self):
        session = _Session(hosts=[host()])
        tick._hosts_for(session, assignment(host_id=None, site_id=uuid.uuid4()))
        assert session.host_query.joined is False

    def test_a_targetless_row_selects_nothing(self):
        session = _Session(hosts=[host()])
        got = tick._hosts_for(session, assignment(host_id=None))
        assert got == []


class TestEveryTenantIsVisited:
    """The tick is a server-wide operation, so it must visit EVERY database.

    A tenant host's assignments, profiles and hosts all live in that tenant's
    database. A tick that reads only the bootstrap session finds zero
    assignments and reports a clean `due=0` -- so scheduled applies silently
    never fire for anyone in multi-tenancy, and nothing anywhere errors.
    Found 2026-08-29 while verifying S3, in code written the day before.
    """

    def test_assignments_in_a_second_database_are_not_missed(self):
        empty = _Session()
        tenant = _Session(hosts=[host()], assignments=[assignment()], profile=profile())
        summary, calls = _run([empty, tenant])
        assert summary["due"] == 1, "the tenant database's assignment was skipped"
        assert summary["queued"] == 1
        assert calls and calls[0][0] == HOST_ID

    def test_every_session_is_closed_even_the_empty_ones(self):
        # iter_host_databases documents that the CALLER closes each session;
        # leaking one per tick exhausts the pool over a long-running server.
        first, second = _Session(), _Session()
        _run([first, second])
        assert first.closed and second.closed

    def test_one_tenants_failure_does_not_stop_the_others(self):
        class _Exploding(_Session):
            def query(self, entity):
                raise RuntimeError("this tenant's database is unreachable")

        broken = _Exploding()
        healthy = _Session(
            hosts=[host()], assignments=[assignment()], profile=profile()
        )
        summary, _calls = _run([broken, healthy])
        assert summary["queued"] == 1, "a broken tenant must not stop the rest"
        assert broken.closed and healthy.closed

    def test_a_database_with_no_due_work_is_not_committed(self):
        # summary accumulates across tenants, so committing on it would write
        # this session on the strength of another tenant's work.
        idle = _Session()
        busy = _Session(hosts=[host()], assignments=[assignment()], profile=profile())
        _run([idle, busy])
        assert idle.committed == 0
        assert busy.committed == 1
