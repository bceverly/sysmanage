# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""When automatic updates happen, end to end on the real compiled automation
engine and a real database: only inside a host's maintenance windows, never
in a blackout, never past one on an emergency override, reboots inside the
window (26.2); and only after the policy's waiting periods, with patches for
critical CVEs on their own, shorter count (26.3)."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.api import auto_updates as auto_updates_api
from backend.persistence import models
from backend.services import (
    auto_update_evidence,
    auto_update_results,
    auto_update_runner,
)
from backend.websocket import outbound_processor


@pytest.fixture(name="automation")
def _automation(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("automation_engine")
    if not hasattr(eng, "window_start"):
        pytest.fail(
            "automation_engine is older than 26.2: rebuild it (make build-modules)"
        )
    monkeypatch.setattr(auto_update_runner, "engine", lambda: eng)
    return eng


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _host(session, fqdn="web1", **kw):
    host = models.Host(fqdn=fqdn, ipv4="10.0.0.1", active=True, status="up",
                       approval_status="approved", **kw)  # fmt: skip
    session.add(host)
    session.flush()
    return host


def _update(session, host, name, age_days=0, version="1.1", kind="security"):
    now = _now()
    session.add(
        models.PackageUpdate(
            host_id=host.id, package_name=name, current_version="1.0",
            available_version=version, package_manager="apt", update_type=kind,
            status="available", discovered_at=now - timedelta(days=age_days),
            created_at=now, updated_at=now,
        )
    )  # fmt: skip


def _policy(session, name="nightly", **kw):
    profile = models.UpgradeProfile(
        name=name, cron="0 3 * * *", enabled=True, auto_apply=True,
        next_run=_now() - timedelta(minutes=1), **kw,
    )  # fmt: skip
    session.add(profile)
    session.flush()
    return profile


def _window(session, start, end, kind="allow"):
    window = models.MaintenanceWindow(name=f"{kind} {start}", kind=kind,
                                      recurrence="once", starts_at=start, ends_at=end,
                                      enabled=True)  # fmt: skip
    session.add(window)
    session.flush()
    session.add(models.MaintenanceWindowScope(window_id=window.id, scope_type="all"))
    session.flush()
    return window


def _commands(session, host, kind):
    out = []
    for row in session.query(models.MessageQueue).filter(
        models.MessageQueue.host_id == host.id
    ):
        data = json.loads(row.message_data)
        if data.get("data", {}).get("command_type") == kind:
            out.append((row, data["data"]["parameters"]))
    return out


def _tick(session, automation, now=None):
    summary = {"queued": 0, "timed_out": 0, "held": False}
    auto_update_runner.tick_database(session, automation, now or _now(), summary)
    return summary


# --- 26.2: maintenance windows ----------------------------------------------


def test_outside_its_window_a_run_waits_and_is_planned_again_when_it_opens(
    session, automation
):
    now = _now()
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    opens = now + timedelta(hours=2)
    _window(session, opens, opens + timedelta(hours=2))
    session.commit()

    _tick(session, automation, now)
    run = session.query(models.AutoUpdateRun).one()
    assert run.status == "waiting" and run.release_at == opens
    assert run.completed_at is None
    assert _commands(session, host, "apply_updates") == []

    # The window is still closed: nothing is sent, nothing new is planned.
    _policy_due(session)
    _tick(session, automation, now + timedelta(minutes=30))
    assert session.query(models.AutoUpdateRun).count() == 1

    # An update that appeared while it waited goes out with it.  (The policy
    # is not due again meanwhile, whatever time of day the test runs.)
    _update(session, host, "curl")
    for profile in session.query(models.UpgradeProfile):
        profile.next_run = opens + timedelta(days=1)
    session.commit()
    _tick(session, automation, opens + timedelta(minutes=1))
    run = session.query(models.AutoUpdateRun).one()
    assert run.status == "queued"
    sent = _commands(session, host, "apply_updates")
    assert len(sent) == 1
    assert sorted(p["package_name"] for p in sent[0][1]["packages"]) == [
        "curl",
        "openssl",
    ]
    assert sent[0][0].correlation_id == str(run.id)


def _policy_due(session):
    for profile in session.query(models.UpgradeProfile):
        profile.next_run = _now() - timedelta(minutes=1)
    session.commit()


def test_inside_an_open_window_a_run_starts_at_once(session, automation):
    now = _now()
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    _window(session, now - timedelta(hours=1), now + timedelta(hours=1))
    session.commit()

    _tick(session, automation, now)
    assert session.query(models.AutoUpdateRun).one().status == "queued"
    assert len(_commands(session, host, "apply_updates")) == 1


def test_a_run_that_would_not_finish_in_the_window_is_skipped_and_says_why(
    session, automation
):
    now = _now()
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    _window(session, now - timedelta(hours=1), now + timedelta(minutes=3))
    session.commit()

    _tick(session, automation, now)
    run = session.query(models.AutoUpdateRun).one()
    assert (run.status, run.reason) == ("skipped", "no_window_long_enough")


def test_a_blackout_holds_a_host_without_allow_windows(session, automation):
    now = _now()
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    ends = now + timedelta(hours=1)
    _window(session, now - timedelta(hours=1), ends, kind="blackout")
    session.commit()

    _tick(session, automation, now)
    run = session.query(models.AutoUpdateRun).one()
    assert run.status == "waiting" and run.release_at == ends


def test_a_host_with_no_window_runs_exactly_as_before(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    session.commit()
    _tick(session, automation)
    assert session.query(models.AutoUpdateRun).one().status == "queued"


def test_an_emergency_override_never_lets_an_automatic_run_through(session, automation):
    now = _now()
    host = _host(session)
    _window(session, now + timedelta(hours=5), now + timedelta(hours=6))
    run = models.AutoUpdateRun(profile_name="p", host_id=host.id, status="queued",
                               queued_at=now)  # fmt: skip
    session.add(run)
    session.add(models.MaintenanceOverride(host_id=host.id, reason="incident",
                                           expires_at=now + timedelta(hours=1)))  # fmt: skip
    session.flush()
    automatic = SimpleNamespace(correlation_id=str(run.id))
    by_hand = SimpleNamespace(correlation_id=None)

    held = outbound_processor.automatic_held(
        session, host.id, now, [automatic, by_hand]
    )
    assert held == [automatic]


def _finished_run(session, host, profile):
    run = models.AutoUpdateRun(profile_id=profile.id, profile_name=profile.name,
                               host_id=host.id, status="succeeded", queued_at=_now(),
                               completed_at=_now(), applied_count=1,
                               reboot_needed=True)  # fmt: skip
    session.add(run)
    session.flush()
    return run


def test_reboot_only_inside_a_window_waits_for_the_next_one(session, automation):
    now = _now()
    host = _host(session, reboot_required=True)
    profile = _policy(session, reboot_mode="in_window")
    opens = now + timedelta(hours=3)
    _window(session, opens, opens + timedelta(hours=1))
    run = _finished_run(session, host, profile)

    auto_update_results.reboot(session, automation, run, host, profile, now)
    assert run.reboot_status == "next_window"
    assert _commands(session, host, "reboot_system") == []
    session.commit()

    auto_update_results.follow_reboots(
        session, automation, opens + timedelta(minutes=1)
    )
    assert run.reboot_status == "queued"
    sent = _commands(session, host, "reboot_system")
    assert len(sent) == 1 and sent[0][0].correlation_id == str(run.id)


def test_a_waiting_reboot_is_dropped_when_no_longer_needed_or_wanted(
    session, automation
):
    now = _now()
    host = _host(session, reboot_required=True)
    profile = _policy(session, reboot_mode="in_window")
    _window(session, now + timedelta(hours=3), now + timedelta(hours=4))
    run = _finished_run(session, host, profile)
    run.reboot_status = "next_window"
    profile.reboot_mode = "never"
    session.commit()
    auto_update_results.follow_reboots(
        session, automation, now + timedelta(hours=3, minutes=5)
    )
    assert run.reboot_status == "not_wanted"

    run.reboot_status, host.reboot_required = "next_window", False
    session.commit()
    auto_update_results.follow_reboots(session, automation, now)
    assert run.reboot_status == "not_needed"
    assert _commands(session, host, "reboot_system") == []


# --- 26.3: waiting periods ----------------------------------------------------


def test_a_regular_patch_waits_its_days(session, automation):
    host = _host(session)
    _update(session, host, "vim", age_days=2)
    _update(session, host, "bash", age_days=8)
    _policy(session, wait_days_regular=7)
    session.commit()

    _tick(session, automation)
    run = session.query(models.AutoUpdateRun).one()
    assert [p["package_name"] for p in run.packages] == ["bash"]
    waiting = {s["package_name"]: s for s in run.skipped}
    assert waiting["vim"]["reason"] == "waiting_period"
    assert waiting["vim"]["kind"] == "regular"
    assert waiting["vim"]["eligible_at"].startswith(
        (_now() + timedelta(days=5)).date().isoformat()
    )


def _critical_finding(session, host, package, fixed="1.1"):
    vuln = models.Vulnerability(cve_id="CVE-2026-1234", severity="CRITICAL")
    session.add(vuln)
    scan = models.HostVulnerabilityScan(host_id=host.id, scanned_at=_now())
    session.add(scan)
    session.flush()
    session.add(models.HostVulnerabilityFinding(
        scan_id=scan.id, vulnerability_id=vuln.id, package_name=package,
        installed_version="1.0", fixed_version=fixed, severity="CRITICAL",
    ))  # fmt: skip
    session.flush()


@pytest.fixture(name="cve_data")
def _cve_data(session, monkeypatch):
    monkeypatch.setattr(auto_update_evidence, "_loaded", lambda code: True)
    monkeypatch.setattr(auto_update_evidence, "_shared",
                        lambda query_fn, default: query_fn(session))  # fmt: skip


def test_a_patch_fixing_a_critical_cve_waits_the_critical_count(
    session, automation, cve_data
):
    host = _host(session)
    _update(session, host, "openssl", age_days=0)
    _update(session, host, "vim", age_days=0)
    _critical_finding(session, host, "openssl")
    _policy(session, wait_days_regular=7, wait_days_critical=0)
    session.commit()

    _tick(session, automation)
    run = session.query(models.AutoUpdateRun).one()
    assert [(p["package_name"], p["kind"], p["fix_id"]) for p in run.packages] == [
        ("openssl", "critical", "CVE-2026-1234")
    ]
    assert [s["package_name"] for s in run.skipped] == ["vim"]


def test_without_waiting_periods_a_critical_patch_is_still_recorded_as_one(
    session, automation, cve_data
):
    # 26.5's report measures "critical patch to applied" for every policy,
    # not only those that wait (lab, 2026-11-17: always N/A without waits).
    host = _host(session)
    _update(session, host, "openssl", age_days=2)
    _critical_finding(session, host, "openssl")
    _policy(session)
    session.commit()

    _tick(session, automation)
    package = session.query(models.AutoUpdateRun).one().packages[0]
    assert (package["kind"], package["fix_id"]) == ("critical", "CVE-2026-1234")
    assert package["first_seen"].startswith(
        (_now() - timedelta(days=2)).date().isoformat()
    )


def test_the_host_view_shows_when_each_update_becomes_eligible(
    session, automation, cve_data
):
    host = _host(session)
    _update(session, host, "openssl")
    _update(session, host, "vim", age_days=1)
    _update(session, host, "zlib", version="1.0.9")
    _critical_finding(session, host, "zlib", fixed="1.2")  # this update is too old
    profile = _policy(session, wait_days_regular=3, wait_days_critical=0)
    session.commit()
    chosen = auto_update_runner.profile_dict(profile)

    pending = auto_updates_api._pending(session, automation, host, chosen)
    rows = {r["package_name"]: r for r in pending["updates"]}
    assert rows["vim"]["reason"] == "waiting_period"
    assert rows["vim"]["eligible_at"].startswith(
        (_now() + timedelta(days=2)).date().isoformat()
    )
    assert rows["zlib"]["kind"] == "regular"
    assert pending["sources"] == {"vulnerability": True, "advisory": True}


def test_without_cve_data_the_critical_count_never_applies(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    _critical_finding(session, host, "openssl")
    _policy(session, wait_days_regular=7, wait_days_critical=0)
    session.commit()

    _tick(session, automation)
    run = session.query(models.AutoUpdateRun).one()
    assert run.status == "nothing_to_do"
    assert run.skipped[0]["kind"] == "regular"


def test_a_first_sighting_read_back_timezone_aware_is_counted_as_written(automation):
    # PostgreSQL returns discovered_at labeled with the session's time zone;
    # the engine compares it with a naive UTC "now".  This raised in the lab
    # (2026-11-17) and no policy could fire.
    written = datetime(2026, 11, 17, 2, 28, 29)
    read_back = written.replace(tzinfo=timezone(timedelta(hours=-5)))
    assert auto_update_runner.as_written(read_back) == written
    assert auto_update_runner.as_written(written) == written
    update = {"package_name": "curl", "package_manager": "apt", "status": "available",
              "update_type": "security", "available_version": "1",
              "discovered_at": auto_update_runner.as_written(read_back)}  # fmt: skip
    policy = {"wait_days_regular": 7, "wait_days_critical": 0}
    got = automation.update_eligibility(update, policy, {}, written)
    assert got["eligible_at"] == written + timedelta(days=7)
