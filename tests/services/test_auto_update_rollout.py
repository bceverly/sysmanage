# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet-by-fleet rollout of automatic updates (26.4), end to end on the
real compiled automation engine and a real database: one fleet at a time,
the canary first, a health gate and a soak between fleets, each host once,
and a halted rollout that waits for a person."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import upgrade_profiles as profiles_api
from backend.persistence import models
from backend.services import (
    auto_update_results,
    auto_update_rollout,
    auto_update_runner,
)


@pytest.fixture(name="automation")
def _automation(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("automation_engine")
    if not hasattr(eng, "rollout_gate"):
        pytest.fail(
            "automation_engine is older than 26.4: rebuild it (make build-modules)"
        )
    monkeypatch.setattr(auto_update_runner, "engine", lambda: eng)
    return eng


NOW = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _tag(session, name):
    tag = models.Tag(name=name, created_at=NOW, updated_at=NOW)
    session.add(tag)
    session.flush()
    return tag


def _host(session, fqdn, *tags):
    host = models.Host(fqdn=fqdn, ipv4="10.0.0.1", active=True, status="up",
                       approval_status="approved")  # fmt: skip
    session.add(host)
    session.flush()
    for tag in tags:
        session.add(models.HostTag(host_id=host.id, tag_id=tag.id, created_at=NOW))
    session.add(
        models.PackageUpdate(
            host_id=host.id, package_name="openssl", current_version="1.0",
            available_version="1.1", package_manager="apt", update_type="security",
            status="available", discovered_at=NOW, created_at=NOW, updated_at=NOW,
        )
    )  # fmt: skip
    session.flush()
    return host


def _policy(session, stages, **kw):
    profile = models.UpgradeProfile(
        name="nightly", cron="0 3 * * *", enabled=True, auto_apply=True,
        next_run=NOW - timedelta(minutes=1), rollout_enabled=True, **kw,
    )  # fmt: skip
    session.add(profile)
    session.flush()
    for position, (name, tag, soak) in enumerate(stages):
        session.add(
            models.UpgradeProfileRolloutStage(
                profile_id=profile.id, position=position, name=name,
                tag_id=tag.id, soak_minutes=soak,
            )
        )  # fmt: skip
    session.commit()
    return profile


def _sent(session, host):
    out = 0
    for row in session.query(models.MessageQueue).filter(
        models.MessageQueue.host_id == host.id
    ):
        data = json.loads(row.message_data)
        if data.get("data", {}).get("command_type") == "apply_updates":
            out += 1
    return out


def _tick(session, automation, now):
    summary = {"queued": 0, "timed_out": 0, "held": False}
    auto_update_runner.tick_database(session, automation, now, summary)
    session.commit()
    return summary


def _finish(session, host, now, ok=True):
    run = (
        session.query(models.AutoUpdateRun)
        .filter_by(host_id=host.id, status="queued")
        .one()
    )
    for log in session.query(models.UpdateExecutionLog).filter_by(run_id=run.id):
        log.execution_status = "success" if ok else "failed"
        log.error_log = None if ok else "E: broken"
    session.flush()
    auto_update_results.note_results(session, host.id, [run.id], False, now)
    session.commit()


def _rollout(session):
    return session.query(models.AutoUpdateRollout).one()


def _fleets(session):
    tags = SimpleNamespace(canary=_tag(session, "canary"), web=_tag(session, "web"))
    hosts = SimpleNamespace(
        a=_host(session, "a", tags.canary),
        b=_host(session, "b", tags.web),
        c=_host(session, "c", tags.web),
    )
    return tags, hosts


def test_the_canary_goes_first_alone(session, automation):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 60), ("Web", tags.web, 0)])

    _tick(session, automation, NOW)
    rollout = _rollout(session)
    assert rollout.status == "running" and rollout.stage_index == 0
    assert [s["host_ids"] for s in rollout.stages] == [
        [str(hosts.a.id)], [str(hosts.b.id), str(hosts.c.id)]]  # fmt: skip
    assert (_sent(session, hosts.a), _sent(session, hosts.b), _sent(session, hosts.c)) == (
        1, 0, 0)  # fmt: skip


def test_after_a_healthy_soak_the_next_fleet_starts_then_the_rollout_completes(
    session, automation
):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 60), ("Web", tags.web, 0)])
    _tick(session, automation, NOW)
    _finish(session, hosts.a, NOW + timedelta(minutes=5))

    _tick(session, automation, NOW + timedelta(minutes=6))
    rollout = _rollout(session)
    assert rollout.stage_index == 0 and rollout.stages[0]["soak_until"]
    assert _sent(session, hosts.b) == 0  # soaking

    _tick(session, automation, NOW + timedelta(minutes=67))
    rollout = _rollout(session)
    assert rollout.stage_index == 1 and rollout.stages[0]["status"] == "done"
    assert (_sent(session, hosts.b), _sent(session, hosts.c)) == (1, 1)

    later = NOW + timedelta(minutes=70)
    _finish(session, hosts.b, later)
    _finish(session, hosts.c, later)
    _tick(session, automation, later + timedelta(minutes=1))
    assert _rollout(session).status == "completed"


def test_a_failed_canary_halts_the_rollout_until_a_person_resumes_it(
    session, automation
):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 0), ("Web", tags.web, 0)])
    _tick(session, automation, NOW)
    _finish(session, hosts.a, NOW + timedelta(minutes=5), ok=False)

    _tick(session, automation, NOW + timedelta(minutes=6))
    rollout = _rollout(session)
    assert rollout.status == "halted" and rollout.halt_reason == "run_failures"
    assert rollout.halt_detail["culprits"] == [str(hosts.a.id)]
    _tick(session, automation, NOW + timedelta(hours=3))
    assert _sent(session, hosts.b) == 0  # nothing more until someone looks

    # The policy firing again does not start another rollout.
    for profile in session.query(models.UpgradeProfile):
        profile.next_run = NOW
    session.commit()
    assert _tick(session, automation, NOW + timedelta(hours=4))["queued"] == 0
    assert session.query(models.AutoUpdateRollout).count() == 1

    auto_update_rollout.resume(
        session, rollout, "admin", "known flaky mirror", NOW + timedelta(hours=5)
    )
    session.commit()
    _tick(session, automation, NOW + timedelta(hours=5, minutes=1))
    assert _rollout(session).stage_index == 1
    assert (_sent(session, hosts.b), _sent(session, hosts.c)) == (1, 1)


def test_failures_within_the_threshold_do_not_halt(session, automation):
    tags = SimpleNamespace(canary=_tag(session, "canary"), web=_tag(session, "web"))
    canaries = [_host(session, f"c{i}", tags.canary) for i in range(4)]
    _host(session, "w", tags.web)
    _policy(session, [("Canary", tags.canary, 0), ("Web", tags.web, 0)],
            rollout_max_failure_pct=25)  # fmt: skip
    _tick(session, automation, NOW)
    for i, host in enumerate(canaries):
        _finish(session, host, NOW + timedelta(minutes=5), ok=i != 0)
    _tick(session, automation, NOW + timedelta(minutes=6))
    assert _rollout(session).stage_index == 1


def test_a_host_in_two_fleets_is_patched_once_and_hosts_in_none_go_last(
    session, automation
):
    tags = SimpleNamespace(canary=_tag(session, "canary"), web=_tag(session, "web"))
    both = _host(session, "both", tags.canary, tags.web)
    web = _host(session, "web", tags.web)
    loose = _host(session, "loose")
    _policy(session, [("Canary", tags.canary, 0), ("Web", tags.web, 0)])
    _tick(session, automation, NOW)
    stages = _rollout(session).stages
    assert [s["host_ids"] for s in stages] == [
        [str(both.id)], [str(web.id)], [str(loose.id)]]  # fmt: skip
    assert stages[2]["name"] == "remaining"


def test_a_new_critical_alert_on_the_canary_halts_during_the_soak(session, automation):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 120), ("Web", tags.web, 0)])
    _tick(session, automation, NOW)
    _finish(session, hosts.a, NOW + timedelta(minutes=5))
    _tick(session, automation, NOW + timedelta(minutes=6))
    session.add(models.Alert(host_id=hosts.a.id, severity="critical",
                             title="Service down", message="nginx is down",
                             triggered_at=NOW + timedelta(minutes=30)))  # fmt: skip
    session.commit()
    _tick(session, automation, NOW + timedelta(minutes=31))
    rollout = _rollout(session)
    assert rollout.status == "halted" and rollout.halt_reason == "critical_alerts"
    assert _sent(session, hosts.b) == 0


def test_a_canary_host_waiting_for_its_window_keeps_the_fleet_open(session, automation):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 0), ("Web", tags.web, 0)])
    opens = NOW + timedelta(hours=3)
    window = models.MaintenanceWindow(name="night", kind="allow", recurrence="once",
                                      starts_at=opens, ends_at=opens + timedelta(hours=2),
                                      enabled=True)  # fmt: skip
    session.add(window)
    session.flush()
    session.add(models.MaintenanceWindowScope(window_id=window.id, scope_type="host",
                                              host_id=hosts.a.id))  # fmt: skip
    session.commit()
    _tick(session, automation, NOW)
    for profile in session.query(models.UpgradeProfile):
        profile.next_run = NOW + timedelta(days=1)
    session.commit()
    _tick(session, automation, NOW + timedelta(hours=1))
    rollout = _rollout(session)
    assert rollout.stage_index == 0 and rollout.stages[0]["counts"]["in_flight"] == 1
    assert _sent(session, hosts.b) == 0


def test_a_canceled_rollout_patches_no_further_fleet(session, automation):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 0), ("Web", tags.web, 0)])
    _tick(session, automation, NOW)
    auto_update_rollout.end(
        session, _rollout(session), "canceled", NOW, "admin", "freeze"
    )
    session.commit()
    _finish(session, hosts.a, NOW + timedelta(minutes=5))
    _tick(session, automation, NOW + timedelta(minutes=6))
    assert _sent(session, hosts.b) == 0


class _FastLaneEngine:
    """The real engine, plus the critical fast lane as the engine built
    2026-11-26 decides it -- so this runs before ``make build-modules``
    packs that build.  Records what the driver told the gate."""

    def __init__(self, eng):
        self._eng = eng
        self.seen = []

    def rollout_gate(self, stage, now):
        self.seen.append([r.get("critical") for r in stage["runs"]])
        got = self._eng.rollout_gate(stage, now)
        applied = any(r.get("critical") and r["status"] in ("succeeded", "partial")
                      for r in stage["runs"])  # fmt: skip
        if got["action"] == "soak" and applied:
            return dict(got, action="advance", reason="critical_fix", until=None)
        return got

    def __getattr__(self, name):
        return getattr(self._eng, name)


def test_a_critical_fix_goes_to_the_next_fleet_without_the_soak(session, automation):
    """2026-11-26: a critical CVE's fix should not wait out the canary soak."""
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 720), ("Web", tags.web, 0)])
    eng = _FastLaneEngine(automation)
    _tick(session, eng, NOW)
    run = session.query(models.AutoUpdateRun).filter_by(host_id=hosts.a.id).one()
    run.packages = [dict(p, kind="critical") for p in run.packages]
    session.commit()
    _finish(session, hosts.a, NOW + timedelta(minutes=5))

    _tick(session, eng, NOW + timedelta(minutes=6))
    assert [True] in eng.seen
    rollout = _rollout(session)
    assert rollout.stage_index == 1 and rollout.stages[0]["status"] == "done"
    assert (_sent(session, hosts.b), _sent(session, hosts.c)) == (1, 1)
    audit = [a.description for a in session.query(models.AuditLog)]
    assert any(
        "moved on from fleet 'Canary' without the waiting time" in d for d in audit
    )


def test_a_regular_update_still_soaks(session, automation):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 720), ("Web", tags.web, 0)])
    eng = _FastLaneEngine(automation)
    _tick(session, eng, NOW)
    _finish(session, hosts.a, NOW + timedelta(minutes=5))
    _tick(session, eng, NOW + timedelta(minutes=6))
    assert [False] in eng.seen
    assert _rollout(session).stage_index == 0 and _sent(session, hosts.b) == 0


class _OldEngine:
    """An automation engine from before 26.4."""

    def __init__(self, eng):
        self._eng = eng

    def __getattr__(self, name):
        if name in ("rollout_gate", "rollout_assign"):
            raise AttributeError(name)
        return getattr(self._eng, name)


def test_with_an_engine_older_than_26_4_every_host_applies_as_before(
    session, automation
):
    tags, hosts = _fleets(session)
    _policy(session, [("Canary", tags.canary, 60), ("Web", tags.web, 0)])
    _tick(session, _OldEngine(automation), NOW)
    assert session.query(models.AutoUpdateRollout).count() == 0
    assert (_sent(session, hosts.a), _sent(session, hosts.b)) == (1, 1)


def test_fleets_need_their_own_tags_and_a_rollout_needs_one(session):
    tag = _tag(session, "canary")
    profile = models.UpgradeProfile(name="p", cron="0 3 * * *", rollout_enabled=True)
    session.add(profile)
    session.flush()
    stage = profiles_api.RolloutStageRequest(
        name="A", tag_id=str(tag.id), soak_hours=1.5
    )
    with pytest.raises(HTTPException):
        profiles_api._set_stages(session, profile, [stage, stage])
    with pytest.raises(HTTPException):
        profiles_api._set_stages(session, profile, [])
    profiles_api._set_stages(session, profile, [stage])
    rows = auto_update_rollout.stage_rows(session, profile.id)
    assert [(r.name, r.soak_minutes) for r in rows] == [("A", 90)]


def test_an_unfinished_fleet_is_dropped_when_the_rollout_is_off(session):
    """Production, 2026-11-24: ticking "Roll out fleet by fleet" adds an empty
    fleet; unticking it and saving sent that fleet's blank tag, a 400 "bad
    uuid".  With the rollout off a tagless fleet is ignored; a finished one is
    kept for when the rollout is turned back on."""
    tag = _tag(session, "canary")
    profile = models.UpgradeProfile(name="p", cron="0 3 * * *", rollout_enabled=False)
    session.add(profile)
    session.flush()
    blank = profiles_api.RolloutStageRequest(
        name="Canary fleet", tag_id="", soak_hours=24
    )
    done = profiles_api.RolloutStageRequest(name="A", tag_id=str(tag.id), soak_hours=1)
    profiles_api._set_stages(session, profile, [blank])
    assert auto_update_rollout.stage_rows(session, profile.id) == []
    profiles_api._set_stages(session, profile, [done, blank])
    assert [r.name for r in auto_update_rollout.stage_rows(session, profile.id)] == [
        "A"
    ]
    profile.rollout_enabled = True  # on, a tagless fleet is still refused
    with pytest.raises(HTTPException):
        profiles_api._set_stages(session, profile, [done, blank])
