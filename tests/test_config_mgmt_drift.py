# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Drift reconciliation (Phase 20.2).

The whole feature rests on one claim: a check-mode run IS a drift report. What
makes that safe rather than clever is the set of rules below, and every one of
them exists because the naive version is wrong in a way that shows up only in
production:

* a LIVE run that changed something is not drift, it is us changing something;
* a FAILED check run knows nothing about the host, so its silence must not
  close findings;
* a task that failed is an error, not a divergence;
* "drifting since" must mean the CURRENT episode, or the number is a lie.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.persistence import models
from backend.services import config_mgmt_drift as drift

NOW = datetime(2026, 8, 28, 12, 0, 0)
HOST = uuid.UUID("22222222-2222-4222-8222-222222222222")
PROFILE = uuid.UUID("44444444-4444-4444-8444-444444444444")


def run(**over):
    base = {
        "id": uuid.uuid4(),
        "host_id": HOST,
        "profile_id": PROFILE,
        "profile_name": "baseline",
        "check_mode": True,
        "success": True,
    }
    base.update(over)
    return SimpleNamespace(**base)


def finding(**over):
    base = {
        "id": uuid.uuid4(),
        "host_id": HOST,
        "profile_id": PROFILE,
        "profile_name": "baseline",
        "task_name": "ensure sshd config",
        "detail": None,
        "first_seen_at": NOW - timedelta(days=3),
        "last_seen_at": NOW - timedelta(days=1),
        "resolved_at": None,
        "last_run_id": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def all(self):
        return list(self._rows)

    def order_by(self, *_a):
        return self


class _Session:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added = []

    def query(self, _entity):
        return _Query(self.rows)

    def add(self, obj):
        self.added.append(obj)


def task(name, changed=True, msg=None, status="changed"):
    return {"task": name, "changed": changed, "msg": msg, "status": status}


def reconcile(session, the_run, tasks, module_loaded=True):
    with_now = drift._now
    drift._now = lambda: NOW
    try:
        return drift.reconcile_run(session, the_run, tasks, module_loaded=module_loaded)
    finally:
        drift._now = with_now


class TestWhatCounts:
    def test_a_changed_task_is_a_finding(self):
        assert drift.changed_tasks([task("a")])[0]["name"] == "a"

    def test_an_unchanged_task_is_not(self):
        assert drift.changed_tasks([task("a", changed=False)]) == []

    def test_a_failed_task_is_an_error_not_a_divergence(self):
        # Reporting it as drift would send an operator to remediate something
        # that cannot run.
        assert drift.changed_tasks([task("a", changed=False, status="failed")]) == []

    def test_a_nameless_task_is_skipped(self):
        # Without a name there is no identity across runs, so it would open a
        # brand-new finding on every single tick.
        assert drift.changed_tasks([task(None)]) == []
        assert drift.changed_tasks([task("")]) == []

    def test_non_dict_entries_are_ignored(self):
        assert drift.changed_tasks(["nonsense", None, 5]) == []

    def test_a_very_long_task_name_is_capped(self):
        got = drift.changed_tasks([task("x" * 900)])
        assert len(got[0]["name"]) == 500


class TestGating:
    def test_an_unlicensed_server_records_nothing(self):
        session = _Session()
        out = reconcile(session, run(), [task("a")], module_loaded=False)
        assert session.added == []
        assert out == {"opened": 0, "still_open": 0, "resolved": 0}

    def test_a_live_run_is_not_drift(self):
        # It changed things because we told it to.
        session = _Session()
        reconcile(session, run(check_mode=False), [task("a")])
        assert session.added == []

    def test_an_ad_hoc_run_with_no_profile_is_not_drift(self):
        # Drift is divergence from a BASELINE; a pasted playbook has none.
        session = _Session()
        reconcile(session, run(profile_id=None), [task("a")])
        assert session.added == []


class TestOpening:
    def test_a_new_divergence_opens_a_finding(self):
        session = _Session()
        out = reconcile(
            session, run(), [task("ensure sshd config", msg="would set 0600")]
        )
        assert out["opened"] == 1
        added = session.added[0]
        assert added.task_name == "ensure sshd config"
        assert added.detail == "would set 0600"
        assert added.first_seen_at == NOW
        assert added.resolved_at is None

    def test_a_repeat_divergence_keeps_its_original_first_seen(self):
        # This is the "since when" column. Refreshing it every run would make
        # every drift look brand new and the number meaningless.
        row = finding()
        original = row.first_seen_at
        session = _Session([row])
        out = reconcile(session, run(), [task("ensure sshd config")])
        assert out["still_open"] == 1
        assert session.added == []
        assert row.first_seen_at == original
        assert row.last_seen_at == NOW

    def test_the_detail_is_refreshed_on_each_sighting(self):
        row = finding(detail="old reason")
        session = _Session([row])
        reconcile(session, run(), [task("ensure sshd config", msg="new reason")])
        assert row.detail == "new reason"

    def test_an_over_long_detail_is_capped(self):
        row = finding()
        session = _Session([row])
        reconcile(session, run(), [task("ensure sshd config", msg="y" * 5000)])
        assert len(row.detail) == drift.MAX_DETAIL_CHARS


class TestResolving:
    def test_a_successful_run_that_no_longer_sees_it_resolves_it(self):
        row = finding()
        session = _Session([row])
        out = reconcile(session, run(success=True), [])
        assert out["resolved"] == 1
        assert row.resolved_at == NOW

    def test_a_FAILED_check_run_must_not_resolve_anything(self):
        # The run does not know the host's state. Closing findings on the
        # strength of an error is how a dashboard reports "all clear" for a
        # fleet it could not reach.
        row = finding()
        session = _Session([row])
        out = reconcile(session, run(success=False), [])
        assert out["resolved"] == 0
        assert row.resolved_at is None

    def test_an_already_resolved_finding_is_not_resolved_twice(self):
        row = finding(resolved_at=NOW - timedelta(days=1))
        session = _Session([row])
        out = reconcile(session, run(), [])
        assert out["resolved"] == 0
        assert row.resolved_at == NOW - timedelta(days=1)

    def test_a_regression_reopens_and_restarts_the_clock(self):
        # "Drifting since" must describe the CURRENT episode. Keeping the old
        # first_seen would claim continuous drift across a period when the
        # host was actually compliant.
        row = finding(resolved_at=NOW - timedelta(days=5))
        session = _Session([row])
        out = reconcile(session, run(), [task("ensure sshd config")])
        assert out["opened"] == 1
        assert row.resolved_at is None
        assert row.first_seen_at == NOW

    def test_other_findings_are_untouched_by_an_unrelated_sighting(self):
        seen = finding(task_name="a")
        other = finding(task_name="b")
        session = _Session([seen, other])
        reconcile(session, run(success=True), [task("a")])
        assert seen.resolved_at is None
        # b was not observed by a SUCCESSFUL run, so it resolves.
        assert other.resolved_at == NOW


class TestResilience:
    def test_a_bookkeeping_failure_never_propagates(self):
        # The run row is the more valuable record: losing drift state is
        # recoverable on the next check, losing the run is not.
        class Exploding(_Session):
            def query(self, _entity):
                raise RuntimeError("db is down")

        out = reconcile(Exploding(), run(), [task("a")])
        assert out == {"opened": 0, "still_open": 0, "resolved": 0}


class TestSerialisation:
    def test_naive_timestamps_come_back_marked_utc(self):
        # A naive value renders as LOCAL time in a browser, which would
        # misreport the one number this feature exists to show.
        out = drift.finding_to_dict(finding(), host_fqdn="h.invalid")
        assert out["first_seen_at"].tzinfo is timezone.utc
        assert out["host_fqdn"] == "h.invalid"

    def test_a_resolved_finding_reports_its_resolution_time(self):
        out = drift.finding_to_dict(finding(resolved_at=NOW))
        assert out["resolved_at"].tzinfo is timezone.utc

    def test_a_finding_whose_profile_was_deleted_still_serialises(self):
        # profile_id is ON DELETE SET NULL so history survives the profile.
        out = drift.finding_to_dict(finding(profile_id=None))
        assert out["profile_id"] is None

    def test_as_utc_leaves_an_aware_value_alone(self):
        aware = datetime(2026, 8, 28, tzinfo=timezone.utc)
        assert drift.as_utc(aware) is aware

    def test_as_utc_passes_none_through(self):
        assert drift.as_utc(None) is None


class TestAlertingContract:
    """Fields the Pro+ ``config_drift`` alert evaluator reads (Phase 20.2, S3).

    That evaluator is compiled into the licensed alerting engine and is built
    from a DIFFERENT repository, whose CI never checks this one out. So nothing
    but this test connects a rename here to the breakage it causes there: the
    evaluator would stop matching, the rule would quietly never fire, and a
    silent alert rule is worse than no alert rule -- the operator believes they
    are covered.

    Renaming any of these is allowed. Renaming them WITHOUT updating
    ``alerting_evaluators.pxi`` is the thing this catches.
    """

    REQUIRED = ("host_id", "resolved_at", "profile_name", "first_seen_at")

    @pytest.mark.parametrize("field", REQUIRED)
    def test_the_evaluator_can_still_filter_on_this_column(self, field):
        column = getattr(models.ConfigDriftFinding, field, None)
        assert column is not None, (
            f"ConfigDriftFinding.{field} was removed or renamed; the Pro+ "
            "config_drift alert evaluator filters on it"
        )

    def test_open_findings_are_expressed_as_a_null_resolved_at(self):
        # The evaluator selects open findings with `resolved_at.is_(None)`.
        # Were this to become a status enum, that filter would silently match
        # everything.
        assert models.ConfigDriftFinding.resolved_at.nullable is True

    def test_first_seen_at_is_a_timestamp_the_evaluator_can_subtract(self):
        # min_hours does `now - first_seen_at`; a string column would raise
        # inside the evaluator, where the failure surfaces as a dropped alert.
        from sqlalchemy import DateTime  # noqa: PLC0415

        assert isinstance(models.ConfigDriftFinding.first_seen_at.type, DateTime)
