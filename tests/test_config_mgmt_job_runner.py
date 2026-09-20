# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The fleet job runner (Phase 20.1).

This is the part of fleet-scale config management that is not schema, and the
behaviours worth pinning are the ones that only bite at four thousand hosts:

* **The wave is bounded.** A job never has more than its concurrency in
  flight. Without this the runner is the all-at-once burst that
  ``ConfigProfileAssignment`` already does and that jobs exist to replace.
* **A host that cannot take the command is SKIPPED, not failed.** It is the
  expected answer for a machine without ansible-core; filing it as a failure
  makes every mixed fleet look broken.
* **Results pace the job.** Closing a target advances its job immediately, so
  a fleet is worked through as fast as it answers rather than at one wave per
  minute -- across thousands of hosts that is the difference in hours.
* **Nothing stalls forever.** A dispatched target that never reports ages out,
  because a job stuck at "running" with an outstanding count that never moves
  reads as a broken feature rather than a failed host.
"""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services import config_mgmt_job_runner as runner

NOW = datetime(2026, 8, 30, 10, 0, 0)
JOB = uuid.UUID("66666666-6666-4666-8666-666666666666")
PROFILE = uuid.UUID("44444444-4444-4444-8444-444444444444")


class _Engine:
    """The release policy and status rules, as the real engine implements them."""

    def clamp_concurrency(self, value):
        return 20 if value is None else max(1, min(500, int(value)))

    def clamp_timeout(self, value):
        return value

    def next_batch_size(self, concurrency, in_flight, pending):
        return max(0, min(pending, int(concurrency) - in_flight))

    def job_status_after(
        self, succeeded, failed, skipped, in_flight, pending, started=True
    ):
        if pending or in_flight:
            return "running" if started else "pending"
        if failed and not succeeded:
            return "failed"
        return "completed"

    def job_is_terminal(self, status):
        return status in ("completed", "failed", "canceled")

    def inventory_selectors(self, inventory, _members):
        return {
            "all_hosts": bool(getattr(inventory, "all_hosts", False)),
            "host_ids": [],
            "tag_ids": [],
            "site_ids": [],
        }


def target(status="pending", **over):
    base = {
        "id": uuid.uuid4(),
        "job_id": JOB,
        "host_id": uuid.uuid4(),
        "host_fqdn": "h.invalid",
        "status": status,
        "command_id": None,
        "run_id": None,
        "detail": None,
        "queued_at": None,
        "finished_at": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


def job(**over):
    base = {
        "id": JOB,
        "profile_id": PROFILE,
        "profile_name": "baseline",
        "status": "pending",
        "check_mode": False,
        "concurrency": 3,
        "timeout_seconds": None,
        "total_targets": 0,
        "succeeded_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "detail": None,
        "started_at": None,
        "finished_at": None,
        "created_at": NOW,
    }
    base.update(over)
    return SimpleNamespace(**base)


def profile(active=True):
    return SimpleNamespace(
        id=PROFILE,
        name="baseline",
        engine="ansible-core",
        content="- hosts: all\n",
        is_active=active,
    )


def _matches(clause, row) -> bool:
    """Evaluate one SQLAlchemy clause against a plain row object.

    The fake session HAS to honour filters rather than ignore them. The runner
    asks for "pending targets" and then for "in-flight targets" against the
    same table, and a fake that returns everything to both makes the bounded
    release look broken when it is not -- or, far worse, makes an unbounded
    one look fine.
    """
    column = getattr(getattr(clause, "left", None), "name", None)
    operator = getattr(getattr(clause, "operator", None), "__name__", None)
    if column is None or operator is None:
        return True
    value = getattr(row, column, None)
    expected = getattr(getattr(clause, "right", None), "value", None)

    if operator == "eq":
        return value == expected
    if operator == "in_op":
        return value in (expected or [])
    if operator == "lt":
        return value is not None and value < expected
    if operator == "is_not":
        return value is not None
    if operator == "is_":
        # `.is_(True)` renders its operand as a SQL literal element (True_ /
        # False_ / Null) rather than a bind parameter, so there is no `.value`
        # to read -- the element's own text is the operand. Without this branch
        # a filter on `enabled` silently passes everything, and a test
        # asserting that a disabled template never fires would pass while the
        # real query did the opposite.
        literal = str(getattr(clause, "right", "")).strip().lower()
        if literal == "null":
            return value is None
        return bool(value) is (literal == "true")
    return True


class _Query:
    def __init__(self, rows, session):
        self.rows = list(rows)
        self.session = session
        self._limit = None

    def filter(self, *clauses, **_k):
        for clause in clauses:
            self.rows = [r for r in self.rows if _matches(clause, r)]
        return self

    def order_by(self, *_a):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def offset(self, _n):
        return self

    def all(self):
        rows = self.rows
        return rows[: self._limit] if self._limit is not None else rows

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return len(self.rows)


class _Session:
    """A session whose target queries reflect the CURRENT statuses.

    The runner reads pending/in-flight counts, releases, and then re-reads.
    A fixed row list would make the second read stale and hide the very bug
    these tests exist to catch.
    """

    def __init__(self, targets=None, profiles=None, jobs=None, others=None):
        self.targets = targets or []
        self.profiles = profiles or []
        self.jobs = jobs or []
        self.others = others or {}
        self.added = []
        self.commits = 0
        self.pending_filter = None

    def query(self, entity, *_rest):
        name = getattr(entity, "__name__", str(entity))
        if name == "ConfigJobTarget":
            return _Query(self.targets, self)
        if name == "ConfigProfile":
            return _Query(self.profiles, self)
        if name == "ConfigJob":
            return _Query(self.jobs, self)
        return _Query(self.others.get(name, []), self)

    def add(self, row):
        self.added.append(row)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def _counts(session, _job_id):
    statuses = [t.status for t in session.targets]
    return {
        "pending": sum(1 for s in statuses if s == "pending"),
        "in_flight": sum(1 for s in statuses if s == "queued"),
    }


def _patched(session, engine=None, queue=None):
    """Patch the engine boundary, live counts and the dispatch helper."""
    engine = engine or _Engine()
    queued = []

    def fake_queue(_db, host_id, _params):
        if queue is not None:
            return queue(host_id)
        command_id = f"cmd-{host_id}"
        queued.append(command_id)
        return command_id

    return (
        patch.object(runner.fleet.shim, "engine_module", lambda: engine),
        patch.object(
            runner.fleet, "target_counts", lambda db, jid: _counts(session, jid)
        ),
        patch.object(runner.dispatch, "queue_apply", fake_queue),
        patch.object(
            runner.dispatch, "parameters_for", lambda *_a, **_k: {"profile": {}}
        ),
        queued,
    )


def _advance(session, the_job, engine=None, queue=None):
    p1, p2, p3, p4, queued = _patched(session, engine, queue)
    with p1, p2, p3, p4:
        result = runner.advance_job(session, the_job)
    return result, queued


class TestBoundedRelease:
    def test_only_the_concurrency_is_released_in_one_wave(self):
        targets = [target() for _ in range(10)]
        session = _Session(targets=targets, profiles=[profile()])
        result, _ = _advance(session, job(concurrency=3))
        assert result["released"] == 3
        assert sum(1 for t in targets if t.status == "queued") == 3
        assert sum(1 for t in targets if t.status == "pending") == 7

    def test_a_saturated_job_releases_nothing_more(self):
        targets = [target("queued") for _ in range(3)] + [target() for _ in range(5)]
        session = _Session(targets=targets, profiles=[profile()])
        result, _ = _advance(session, job(concurrency=3))
        assert result["released"] == 0

    def test_the_tail_releases_only_what_remains(self):
        targets = [target() for _ in range(2)]
        session = _Session(targets=targets, profiles=[profile()])
        result, _ = _advance(session, job(concurrency=50))
        assert result["released"] == 2

    def test_each_released_target_records_its_command_id(self):
        # The command id is the ONLY join back to the arriving result; a target
        # without one can never be closed.
        targets = [target()]
        session = _Session(targets=targets, profiles=[profile()])
        _advance(session, job())
        assert targets[0].command_id
        assert targets[0].queued_at is not None

    def test_the_job_starts_when_its_first_wave_goes_out(self):
        session = _Session(targets=[target()], profiles=[profile()])
        the_job = job()
        _advance(session, the_job)
        assert the_job.started_at is not None
        assert the_job.status == "running"


class TestSkipping:
    def test_a_host_that_cannot_take_the_command_is_skipped_not_failed(self):
        # The expected answer for a machine without ansible-core. Filing it as
        # a failure makes every mixed fleet look broken.
        targets = [target()]
        session = _Session(targets=targets, profiles=[profile()])

        def refuse(_host_id):
            raise RuntimeError("host does not support APPLY_CONFIG_PROFILE")

        the_job = job()
        result, _ = _advance(session, the_job, queue=refuse)
        assert result["skipped"] == 1
        assert targets[0].status == "skipped"
        assert the_job.failed_count == 0
        assert the_job.skipped_count == 1

    def test_the_reason_is_written_to_the_row_not_only_the_log(self):
        targets = [target()]
        session = _Session(targets=targets, profiles=[profile()])

        def refuse(_host_id):
            raise RuntimeError("no config-management capability advertised")

        _advance(session, job(), queue=refuse)
        assert "capability" in targets[0].detail

    def test_one_refusing_host_does_not_stop_the_others(self):
        # Per-host isolation is the point of a row per target.
        targets = [target() for _ in range(3)]
        session = _Session(targets=targets, profiles=[profile()])
        calls = {"n": 0}

        def sometimes(host_id):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("nope")
            return f"cmd-{host_id}"

        result, _ = _advance(session, job(concurrency=3), queue=sometimes)
        assert result["released"] == 2
        assert result["skipped"] == 1

    def test_a_target_whose_host_vanished_is_skipped_with_a_reason(self):
        targets = [target(host_id=None)]
        session = _Session(targets=targets, profiles=[profile()])
        _advance(session, job())
        assert targets[0].status == "skipped"
        assert "removed" in targets[0].detail


class TestUndispatchableProfile:
    def test_a_retired_profile_stops_the_job_rather_than_running_it(self):
        # Applying a profile somebody deliberately took out of service would
        # undo a decision rather than enforce one.
        targets = [target() for _ in range(4)]
        session = _Session(targets=targets, profiles=[profile(active=False)])
        the_job = job()
        _advance(session, the_job)
        assert all(t.status == "skipped" for t in targets)
        assert "out of service" in the_job.detail

    def test_a_deleted_profile_stops_the_job(self):
        targets = [target()]
        session = _Session(targets=targets, profiles=[])
        the_job = job()
        _advance(session, the_job)
        assert the_job.detail
        assert targets[0].status == "skipped"

    def test_an_undispatchable_body_stops_the_job_once_not_every_tick(self):
        # Re-deciding this every minute produces an identical failure and a
        # flooded log -- the same reasoning the assignment tick applies.
        targets = [target()]
        session = _Session(targets=targets, profiles=[profile()])
        the_job = job()
        p1, p2, p3, _p4, _q = _patched(session)
        boom = patch.object(
            runner.dispatch,
            "parameters_for",
            lambda *_a, **_k: (_ for _ in ()).throw(
                runner.dispatch.DispatchError("bad body")
            ),
        )
        with p1, p2, p3, boom:
            runner.advance_job(session, the_job)
        assert the_job.detail == "bad body"
        assert targets[0].status == "skipped"


class TestClosingTargets:
    def _session_for_close(self, the_target, the_job):
        session = _Session(targets=[the_target], jobs=[the_job], profiles=[profile()])
        return session

    def test_a_successful_result_closes_its_target(self):
        tgt = target("queued", command_id="cmd-1")
        the_job = job(status="running", started_at=NOW)
        session = self._session_for_close(tgt, the_job)
        run = SimpleNamespace(
            id=uuid.uuid4(), command_id="cmd-1", success=True, reason=None
        )
        p1, p2, p3, p4, _ = _patched(session)
        with p1, p2, p3, p4:
            assert runner.close_target_for_run(session, run) is True
        assert tgt.status == "succeeded"
        assert the_job.succeeded_count == 1

    def test_a_failed_result_records_the_reason(self):
        tgt = target("queued", command_id="cmd-1")
        the_job = job(status="running", started_at=NOW)
        session = self._session_for_close(tgt, the_job)
        run = SimpleNamespace(
            id=uuid.uuid4(),
            command_id="cmd-1",
            success=False,
            reason="executor_missing",
        )
        p1, p2, p3, p4, _ = _patched(session)
        with p1, p2, p3, p4:
            runner.close_target_for_run(session, run)
        assert tgt.status == "failed"
        assert the_job.failed_count == 1
        assert tgt.detail == "executor_missing"

    def test_an_ad_hoc_run_belonging_to_no_job_is_not_an_error(self):
        # Most applies are ad-hoc or from an assignment; this is the common
        # path and must be silent.
        session = _Session(targets=[], jobs=[])
        run = SimpleNamespace(
            id=uuid.uuid4(), command_id="cmd-x", success=True, reason=None
        )
        p1, p2, p3, p4, _ = _patched(session)
        with p1, p2, p3, p4:
            assert runner.close_target_for_run(session, run) is False

    def test_a_result_with_no_command_id_is_ignored(self):
        session = _Session()
        run = SimpleNamespace(
            id=uuid.uuid4(), command_id=None, success=True, reason=None
        )
        assert runner.close_target_for_run(session, run) is False

    def test_closing_a_target_immediately_releases_the_next_one(self):
        # This is what makes a fleet paced by how fast it answers rather than
        # by a sixty-second clock.
        done = target("queued", command_id="cmd-1")
        waiting = target()
        the_job = job(status="running", concurrency=1, started_at=NOW)
        session = _Session(
            targets=[done, waiting], jobs=[the_job], profiles=[profile()]
        )
        run = SimpleNamespace(
            id=uuid.uuid4(), command_id="cmd-1", success=True, reason=None
        )
        p1, p2, p3, p4, _ = _patched(session)
        with p1, p2, p3, p4:
            runner.close_target_for_run(session, run)
        assert waiting.status == "queued"

    def test_the_last_result_completes_the_job(self):
        tgt = target("queued", command_id="cmd-1")
        the_job = job(status="running", total_targets=1, started_at=NOW)
        session = _Session(targets=[tgt], jobs=[the_job], profiles=[profile()])
        run = SimpleNamespace(
            id=uuid.uuid4(), command_id="cmd-1", success=True, reason=None
        )
        p1, p2, p3, p4, _ = _patched(session)
        with p1, p2, p3, p4:
            runner.close_target_for_run(session, run)
        assert the_job.status == "completed"
        assert the_job.finished_at is not None


class TestStaleTargets:
    def test_a_target_that_never_reports_ages_out(self):
        # Otherwise the job holds its slots forever and shows an outstanding
        # count that never moves -- which reads as a broken feature.
        old = target(
            "queued",
            command_id="cmd-1",
            queued_at=NOW - timedelta(seconds=runner.STALE_TARGET_SECONDS + 60),
        )
        session = _Session(targets=[old], profiles=[profile()])
        the_job = job(status="running", started_at=NOW)
        result, _ = _advance(session, the_job)
        assert result["expired"] == 1
        assert old.status == "failed"
        assert the_job.failed_count == 1

    def test_a_recently_dispatched_target_is_left_alone(self):
        # Dispatched against the real clock, not the module's fixed NOW: the
        # cutoff is computed from the wall clock, so a fixture timestamp from
        # a past month would age out and prove nothing.
        fresh = target("queued", command_id="cmd-1", queued_at=runner.fleet.now_naive())
        session = _Session(targets=[fresh], profiles=[profile()])
        result, _ = _advance(session, job(status="running", started_at=NOW))
        assert result["expired"] == 0
        assert fresh.status == "queued"


class TestCancel:
    def test_cancelling_skips_what_was_never_dispatched(self):
        targets = [target(), target(), target("queued", command_id="c")]
        session = _Session(targets=targets, profiles=[profile()])
        the_job = job(status="running", started_at=NOW)
        with patch.object(runner.fleet.shim, "engine_module", lambda: _Engine()):
            skipped = runner.cancel_job(session, the_job, "operator stopped it")
        assert skipped == 2
        assert the_job.status == "canceled"

    def test_targets_already_in_flight_are_left_alone(self):
        # The command is with the agent and the server cannot recall it;
        # marking it cancelled would claim something untrue.
        in_flight = target("queued", command_id="c")
        session = _Session(targets=[in_flight], profiles=[profile()])
        with patch.object(runner.fleet.shim, "engine_module", lambda: _Engine()):
            runner.cancel_job(session, job(status="running"), "stop")
        assert in_flight.status == "queued"

    def test_a_cancelled_job_is_not_advanced_again(self):
        session = _Session(targets=[target()], profiles=[profile()])
        result, _ = _advance(session, job(status="canceled"))
        assert result["released"] == 0


class TestEmptyInventory:
    def test_a_job_over_zero_hosts_completes_and_says_so(self):
        # A clean success over nothing reads as "the fleet is converged".
        session = _Session(profiles=[profile()])
        inventory = SimpleNamespace(id=uuid.uuid4(), name="empty", all_hosts=False)
        with patch.object(runner.fleet, "resolve_hosts", lambda *_a: []):
            with patch.object(runner.fleet.shim, "engine_module", lambda: _Engine()):
                new_job = runner.create_job(
                    session,
                    SimpleNamespace(
                        id=None,
                        name="t",
                        check_mode=False,
                        concurrency=5,
                        timeout_seconds=None,
                    ),
                    profile(),
                    inventory,
                    "op",
                )
        assert new_job.status == "completed"
        assert "no active hosts" in new_job.detail


class TestTickGating:
    def test_an_unlicensed_server_does_nothing(self):
        with patch.object(runner.shim, "engine_module", lambda: None):
            summary = runner.run_one_tick()
        assert summary == {
            "launched": 0,
            "active": 0,
            "released": 0,
            "skipped": 0,
            "expired": 0,
            "no_cron_engine": False,
        }

    def test_running_jobs_still_advance_without_a_cron_parser(self):
        # Stalling live dispatch because SCHEDULING is unavailable would be a
        # much larger failure than a late launch.
        session = _Session(targets=[target()], profiles=[profile()], jobs=[job()])
        with patch.object(runner.shim, "engine_module", lambda: _Engine()):
            with patch.object(runner, "module_loader_automation", lambda: None):
                with patch.object(
                    runner, "iter_host_databases", lambda: [("d", None, session)]
                ):
                    p1, p2, p3, p4, _ = _patched(session)
                    with p1, p2, p3, p4:
                        summary = runner.run_one_tick()
        assert summary["no_cron_engine"] is True
        assert summary["active"] == 1


class _Cron:
    """Stands in for automation_engine's cron parser."""

    def __init__(self, delta=timedelta(days=1), raises=False):
        self.delta = delta
        self.raises = raises

    def next_run_from_cron(self, _expr, anchor):
        if self.raises:
            raise ValueError("bad cron")
        return anchor + self.delta


INVENTORY = uuid.UUID("55555555-5555-4555-8555-555555555555")


def job_template(**over):
    base = {
        "id": uuid.uuid4(),
        "name": "nightly baseline",
        "profile_id": PROFILE,
        "inventory_id": INVENTORY,
        "check_mode": True,
        "concurrency": 5,
        "timeout_seconds": None,
        "schedule": "0 3 * * *",
        "enabled": True,
        "created_at": NOW - timedelta(days=30),
        # Yesterday: ONE occurrence is due, not a month of them.
        "last_launched_at": NOW - timedelta(days=1, hours=2),
    }
    base.update(over)
    return SimpleNamespace(**base)


def inventory_row(name="web tier"):
    return SimpleNamespace(id=INVENTORY, name=name, all_hosts=True)


class _LaunchSession(_Session):
    """A session that also answers template and inventory queries.

    Targets added during a launch become visible to subsequent queries, which
    the plain fake does not do. That matters here and nowhere else: the launch
    path creates the targets and then immediately asks how many are pending,
    so a session where ``add`` is a dead end would report zero and the first
    wave would never go out -- while the test passed.
    """

    def __init__(self, templates=None, inventories=None, **kw):
        super().__init__(**kw)
        self.templates = templates or []
        self.inventories = inventories or []

    def add(self, row):
        super().add(row)
        if type(row).__name__ == "ConfigJobTarget":
            self.targets.append(row)

    def query(self, entity, *rest):
        name = getattr(entity, "__name__", str(entity))
        if name == "ConfigJobTemplate":
            return _Query(self.templates, self)
        if name == "ConfigInventory":
            return _Query(self.inventories, self)
        return super().query(entity, *rest)


class TestScheduledLaunch:
    def _tick(self, session, cron=None, hosts=None):
        engine = _Engine()
        p1, p2, p3, p4, _ = _patched(session, engine)
        with p1, p2, p3, p4:
            with patch.object(runner.shim, "engine_module", lambda: engine):
                with patch.object(
                    runner, "module_loader_automation", lambda: cron or _Cron()
                ):
                    with patch.object(
                        runner, "iter_host_databases", lambda: [("d", None, session)]
                    ):
                        with patch.object(
                            runner.fleet,
                            "resolve_hosts",
                            lambda *_a: hosts if hosts is not None else [],
                        ):
                            return runner.run_one_tick()

    def test_a_due_template_launches_once(self):
        template = job_template()
        session = _LaunchSession(
            templates=[template],
            inventories=[inventory_row()],
            profiles=[profile()],
        )
        summary = self._tick(session)
        assert summary["launched"] == 1
        # The anchor moves, so the next tick does not fire it again -- and a
        # server that was down overnight launches ONCE rather than replaying
        # every occurrence it slept through.
        assert template.last_launched_at is not None

    def test_a_template_not_yet_due_is_left_alone(self):
        template = job_template(last_launched_at=NOW)
        session = _LaunchSession(
            templates=[template], inventories=[inventory_row()], profiles=[profile()]
        )
        summary = self._tick(session, cron=_Cron(delta=timedelta(days=365)))
        assert summary["launched"] == 0

    def test_a_disabled_template_never_launches(self):
        session = _LaunchSession(
            templates=[job_template(enabled=False)],
            inventories=[inventory_row()],
            profiles=[profile()],
        )
        assert self._tick(session)["launched"] == 0

    def test_a_malformed_cron_skips_that_template_not_the_tick(self):
        # One bad expression must not stop every other template from firing.
        session = _LaunchSession(
            templates=[job_template()],
            inventories=[inventory_row()],
            profiles=[profile()],
        )
        assert self._tick(session, cron=_Cron(raises=True))["launched"] == 0

    def test_a_due_template_whose_inventory_vanished_says_so_loudly(self, caplog):
        # A schedule that stops firing with no explanation is the worst
        # failure this feature has, so the ids go in the log.
        template = job_template()
        session = _LaunchSession(
            templates=[template], inventories=[], profiles=[profile()]
        )
        with caplog.at_level("ERROR"):
            self._tick(session)
        assert "is due but its profile" in caplog.text
        # The anchor still advances: re-deciding this every minute produces an
        # identical failure and a flooded log.
        assert template.last_launched_at is not None

    def test_a_scheduled_launch_names_no_operator(self):
        # requested_by stays NULL: writing "system" into an audit field would
        # make the record claim somebody acted.
        template = job_template()
        session = _LaunchSession(
            templates=[template], inventories=[inventory_row()], profiles=[profile()]
        )
        self._tick(session)
        jobs = [row for row in session.added if hasattr(row, "requested_by")]
        assert jobs and jobs[0].requested_by is None

    def test_a_scheduled_launch_dispatches_its_first_wave(self):
        hosts = [
            SimpleNamespace(id=uuid.uuid4(), fqdn=f"h{n}.invalid") for n in range(3)
        ]
        template = job_template()
        session = _LaunchSession(
            templates=[template], inventories=[inventory_row()], profiles=[profile()]
        )
        summary = self._tick(session, hosts=hosts)
        assert summary["launched"] == 1
        assert summary["released"] >= 1
