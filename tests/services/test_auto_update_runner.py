# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic update policies (ROADMAP 26.1) end to end on the real compiled
automation engine and a real database: a due policy queues an
``apply_updates`` naming exactly the eligible packages; held packages, an
opted-out host, a pending run and a hold are respected; the agent's results
close the run; a policy that may reboot queues one reboot and follows it."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.api.update_handlers import handle_update_apply_result
from backend.persistence import models
from backend.services import auto_update_results, auto_update_runner


@pytest.fixture(name="automation")
def _automation(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("automation_engine")
    if not hasattr(eng, "plan_host_run"):
        pytest.fail(
            "automation_engine is older than 26.1: rebuild it (make build-modules)"
        )
    monkeypatch.setattr(auto_update_runner, "engine", lambda: eng)
    return eng


@pytest.fixture(name="mock_connection")
def _mock_connection():
    connection = MagicMock()
    connection.websocket = AsyncMock()
    return connection


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host(session, fqdn="web1", **kw):
    host = models.Host(
        fqdn=fqdn,
        ipv4="10.0.0.1",
        active=True,
        status="up",
        approval_status="approved",
        **kw,
    )
    session.add(host)
    session.flush()
    return host


def _update(session, host, name, kind="security", **kw):
    now = _now()
    session.add(
        models.PackageUpdate(
            host_id=host.id, package_name=name, current_version="1.0",
            available_version="1.1", package_manager=kw.pop("manager", "apt"),
            update_type=kind, status="available", discovered_at=now,
            created_at=now, updated_at=now, **kw,
        )
    )  # fmt: skip


def _policy(session, name="nightly", **kw):
    kw.setdefault("cron", "0 3 * * *")
    profile = models.UpgradeProfile(
        name=name, enabled=True, auto_apply=True,
        next_run=_now() - timedelta(minutes=1), **kw,
    )  # fmt: skip
    session.add(profile)
    session.flush()
    return profile


def _commands(session, host, kind):
    rows = session.query(models.MessageQueue).filter(
        models.MessageQueue.host_id == host.id
    )
    out = []
    for row in rows:
        data = json.loads(row.message_data)
        if data.get("data", {}).get("command_type") == kind:
            out.append(data["data"]["parameters"])
    return out


def _tick(session, automation):
    summary = {"queued": 0, "timed_out": 0, "held": False}
    auto_update_runner.tick_database(session, automation, _now(), summary)
    return summary


def test_a_due_policy_applies_exactly_the_eligible_updates(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    _update(session, host, "postgresql-16", held=True)
    _update(session, host, "vim", kind="enhancement")
    _update(session, host, "sysmanage-agent", kind="enhancement")
    policy = _policy(session, security_only=True)
    session.commit()

    assert _tick(session, automation)["queued"] == 1

    commands = _commands(session, host, "apply_updates")
    assert len(commands) == 1
    command = commands[0]
    assert [p["package_name"] for p in command["packages"]] == ["openssl"]
    run = session.query(models.AutoUpdateRun).one()
    assert run.status == "queued" and run.profile_id == policy.id
    reasons = {s["package_name"]: s["reason"] for s in run.skipped}
    assert reasons == {
        "postgresql-16": "held", "vim": "not_security", "sysmanage-agent": "sysmanage_agent"
    }  # fmt: skip
    log = session.query(models.UpdateExecutionLog).one()
    assert log.run_id == run.id and log.execution_method == "automatic"
    assert session.get(models.UpgradeProfile, policy.id).next_run > _now()
    assert (
        session.query(models.AuditLog)
        .filter(models.AuditLog.entity_id == str(host.id))
        .count()
        == 1
    )


def test_an_opted_out_host_is_skipped_and_says_why(session, automation):
    host = _host(session, auto_update_opt_out=True, auto_update_opt_out_reason="db")
    _update(session, host, "openssl")
    _policy(session)
    session.commit()
    _tick(session, automation)
    assert _commands(session, host, "apply_updates") == []
    run = session.query(models.AutoUpdateRun).one()
    assert (run.status, run.reason) == ("skipped", "opted_out")


def test_a_hold_stops_every_run(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    auto_update_runner.settings_row(session).hold_all = True
    session.commit()
    assert _tick(session, automation)["held"] is True
    assert _commands(session, host, "apply_updates") == []
    assert session.query(models.AutoUpdateRun).count() == 0


def test_a_held_policy_does_not_fire(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session, held=True, hold_reason="change freeze")
    session.commit()
    _tick(session, automation)
    assert session.query(models.AutoUpdateRun).count() == 0


def test_never_a_second_run_while_one_is_pending(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    policy = _policy(session, cron="* * * * *")
    session.commit()
    _tick(session, automation)
    policy.next_run = _now() - timedelta(minutes=1)
    session.commit()
    _tick(session, automation)
    statuses = sorted(r.status for r in session.query(models.AutoUpdateRun))
    assert statuses == ["queued", "skipped"]
    assert len(_commands(session, host, "apply_updates")) == 1


def test_the_most_specific_policy_wins(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    _update(session, host, "vim", kind="enhancement")
    _policy(session, name="everything")
    mine = _policy(session, name="just web1", security_only=True)
    session.add(models.UpgradeProfileHost(profile_id=mine.id, host_id=host.id))
    session.commit()
    _tick(session, automation)
    run = session.query(models.AutoUpdateRun).one()
    assert run.profile_id == mine.id
    assert [p["package_name"] for p in run.packages] == ["openssl"]


@pytest.mark.asyncio
async def test_results_close_the_run_and_a_needed_reboot_is_queued(
    session, automation, mock_connection
):
    host = _host(session)
    _update(session, host, "openssl")
    _update(session, host, "curl")
    _policy(session, reboot_mode="when_needed")
    session.commit()
    _tick(session, automation)

    mock_connection.host_id = host.id
    await handle_update_apply_result(
        session,
        mock_connection,
        {
            "hostname": "web1",
            "updated_packages": [{"package_name": "openssl", "package_manager": "apt"}],
            "failed_packages": [
                {"package_name": "curl", "package_manager": "apt", "error": "E: broken"}
            ],
            "requires_reboot": True,
        },
    )
    session.expire_all()
    run = session.query(models.AutoUpdateRun).one()
    assert (run.status, run.applied_count, run.failed_count) == ("partial", 1, 1)
    assert run.failures[0]["error"] == "E: broken"
    assert run.reboot_status == "queued"
    assert len(_commands(session, host, "reboot_system")) == 1

    # The host boots after the reboot was asked for: it came back.
    session.get(models.Host, host.id).boot_time = _now() + timedelta(minutes=2)
    session.commit()
    auto_update_results.follow_reboots(
        session, automation, _now() + timedelta(minutes=3)
    )
    assert session.query(models.AutoUpdateRun).one().reboot_status == "back"


@pytest.mark.asyncio
async def test_never_reboot_leaves_the_host_reboot_required(
    session, automation, mock_connection
):
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)  # reboot_mode defaults to never
    session.commit()
    _tick(session, automation)
    mock_connection.host_id = host.id
    await handle_update_apply_result(
        session,
        mock_connection,
        {
            "hostname": "web1",
            "updated_packages": [{"package_name": "openssl", "package_manager": "apt"}],
            "failed_packages": [],
            "requires_reboot": True,
        },
    )
    session.expire_all()
    run = session.query(models.AutoUpdateRun).one()
    assert run.status == "succeeded" and run.reboot_status == "not_wanted"
    assert session.get(models.Host, host.id).reboot_required is True
    assert _commands(session, host, "reboot_system") == []


def test_a_reboot_that_never_comes_back_is_flagged(session, automation):
    host = _host(session, boot_time=_now() - timedelta(days=3))
    run = models.AutoUpdateRun(
        profile_name="nightly", host_id=host.id, status="succeeded",
        reboot_status="queued", reboot_queued_at=_now() - timedelta(minutes=45),
        queued_at=_now() - timedelta(hours=1),
    )  # fmt: skip
    session.add(run)
    session.commit()
    auto_update_results.follow_reboots(session, automation, _now())
    assert session.get(models.AutoUpdateRun, run.id).reboot_status == "not_back"


def test_a_run_that_never_reports_times_out(session, automation):
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    session.commit()
    _tick(session, automation)
    later = _now() + timedelta(hours=13)
    assert auto_update_runner.expire_stale_runs(session, later) == 1
    session.commit()
    assert session.query(models.AutoUpdateRun).one().status == "timed_out"
    log = session.query(models.UpdateExecutionLog).one()
    assert log.execution_status == "failed"


def test_without_the_engine_nothing_runs(session, monkeypatch):
    monkeypatch.setattr(auto_update_runner, "engine", lambda: None)
    host = _host(session)
    _update(session, host, "openssl")
    _policy(session)
    session.commit()
    assert auto_update_runner.run_one_tick()["queued"] == 0


def test_timezone_aware_columns_do_not_stop_the_tick(session, automation):
    """PostgreSQL returns some timestamps timezone-aware; comparing them with
    naive UTC raised and stopped every automatic run in the tenant (lab,
    2026-11-16)."""
    host = _host(session, boot_time=_now() - timedelta(days=1))
    profile = _policy(session, reboot_mode="when_needed")
    run = models.AutoUpdateRun(
        profile_id=profile.id, profile_name="nightly", host_id=host.id,
        status="succeeded", reboot_status="none", applied_count=1,
        queued_at=_now() - timedelta(minutes=10),
        completed_at=_now() - timedelta(minutes=5),
    )  # fmt: skip
    session.add(run)
    session.commit()
    with session.no_autoflush:
        loaded = session.get(models.Host, host.id)
        loaded.reboot_required = True
        loaded.reboot_required_updated_at = datetime.now(timezone.utc)  # aware
        auto_update_results.follow_reboots(session, automation, _now())
    assert run.reboot_status == "queued"
    assert auto_update_results.naive_utc(datetime.now(timezone.utc)).tzinfo is None


@pytest.mark.asyncio
async def test_a_policy_changed_later_never_reboots_for_an_old_run(
    session, automation, mock_connection
):
    """A run made under "never" stays that way: switching the policy to
    "when needed" afterwards rebooted the host for the old run (lab,
    2026-11-16)."""
    host = _host(session)
    _update(session, host, "openssl")
    profile = _policy(session)  # never
    session.commit()
    _tick(session, automation)
    mock_connection.host_id = host.id
    await handle_update_apply_result(
        session,
        mock_connection,
        {
            "hostname": "web1",
            "updated_packages": [{"package_name": "openssl", "package_manager": "apt"}],
            "failed_packages": [],
            "requires_reboot": False,
        },
    )
    session.expire_all()
    profile = session.get(models.UpgradeProfile, profile.id)
    profile.reboot_mode = "when_needed"
    loaded = session.get(models.Host, host.id)
    loaded.reboot_required, loaded.reboot_required_updated_at = True, _now()
    session.commit()
    auto_update_results.follow_reboots(session, automation, _now())
    assert _commands(session, host, "reboot_system") == []


def test_never_a_second_reboot_while_one_is_pending(session, automation):
    host = _host(session)
    first = models.AutoUpdateRun(
        profile_name="nightly", host_id=host.id, status="succeeded",
        reboot_status="queued", reboot_queued_at=_now(), queued_at=_now(),
    )  # fmt: skip
    second = models.AutoUpdateRun(
        profile_name="nightly", host_id=host.id, status="succeeded",
        reboot_status="none", queued_at=_now(),
    )  # fmt: skip
    session.add_all([first, second])
    session.commit()
    auto_update_results.queue_reboot(session, second, host, _now())
    session.commit()
    assert _commands(session, host, "reboot_system") == []
    assert second.reboot_status == "queued"


def test_an_agent_that_cannot_apply_is_skipped_and_the_others_still_run(
    session, automation
):
    """An agent advertising no apply_updates refused the command at queue
    time, and the exception aborted the whole policy (2026-11-16)."""
    old = _host(
        session,
        fqdn="old-agent",
        agent_capabilities=json.dumps({"commands": ["check_updates"]}),
    )
    new = _host(session, fqdn="new-agent")
    for host in (old, new):
        _update(session, host, "openssl")
    _policy(session)
    session.commit()
    assert _tick(session, automation)["queued"] == 1
    runs = {r.host_id: r for r in session.query(models.AutoUpdateRun)}
    assert (runs[old.id].status, runs[old.id].reason) == (
        "skipped",
        "agent_cannot_apply",
    )
    assert runs[new.id].status == "queued"
