# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The facts the ``automatic_updates`` alert decides on (26.5), on the real
compiled automation engine and a real database."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.persistence import models
from backend.services import (
    auto_update_evidence,
    auto_update_health,
    auto_update_runner,
)

NOW = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


@pytest.fixture(name="automation")
def _automation(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("automation_engine")
    monkeypatch.setattr(auto_update_runner, "engine", lambda: eng)
    return eng


@pytest.fixture(name="cve_data")
def _cve_data(session, monkeypatch):
    monkeypatch.setattr(auto_update_evidence, "_loaded", lambda code: True)
    monkeypatch.setattr(auto_update_evidence, "_shared",
                        lambda query_fn, default: query_fn(session))  # fmt: skip


def _host(session):
    host = models.Host(fqdn="web1", ipv4="10.0.0.1", active=True, status="up",
                       approval_status="approved")  # fmt: skip
    session.add(host)
    session.flush()
    return host


def _policy(session, host, **kw):
    profile = models.UpgradeProfile(name="nightly", cron="0 3 * * *", enabled=True,
                                    auto_apply=True, **kw)  # fmt: skip
    session.add(profile)
    session.flush()
    session.add(models.UpgradeProfileHost(profile_id=profile.id, host_id=host.id))
    session.flush()
    return profile


def test_a_host_without_automatic_updates_has_no_facts(session, automation):
    host = _host(session)
    facts = auto_update_health.host_facts(session, host)
    assert facts["policy"] is None and facts["last_run"] is None
    assert facts["critical_eligible"] == []


def test_a_failed_run_and_a_long_hold(session, automation):
    host = _host(session)
    _policy(
        session, host, held=True, hold_at=NOW - timedelta(days=9), hold_reason="freeze"
    )
    session.add(models.AutoUpdateRun(profile_name="nightly", host_id=host.id,
                                     status="failed", queued_at=NOW,
                                     reboot_status="none"))  # fmt: skip
    session.commit()
    facts = auto_update_health.host_facts(session, host)
    assert facts["last_run"]["status"] == "failed"
    assert facts["last_run"]["acknowledged"] is False
    assert facts["policy"]["held"] and facts["policy"]["hold_reason"] == "freeze"


def test_the_host_that_halted_a_rollout(session, automation):
    host = _host(session)
    session.add(models.AutoUpdateRollout(
        id=uuid.uuid4(), profile_name="nightly", status="halted", stage_index=0,
        stages=[{"name": "Canary", "host_ids": [str(host.id)]}], started_at=NOW,
        halt_reason="run_failures",
        halt_detail={"stage": 0, "culprits": [str(host.id)]},
    ))  # fmt: skip
    session.commit()
    halt = auto_update_health.host_facts(session, host)["rollout_halt"]
    assert halt["fleet"] == "Canary" and halt["reason"] == "run_failures"


def test_a_critical_patch_the_policy_would_apply_and_since_when(
    session, automation, cve_data
):
    host = _host(session)
    _policy(session, host)
    seen = NOW - timedelta(days=3)
    session.add(models.PackageUpdate(
        host_id=host.id, package_name="openssl", current_version="1.0",
        available_version="1.1", package_manager="apt", update_type="security",
        status="available", discovered_at=seen, created_at=NOW, updated_at=NOW,
    ))  # fmt: skip
    vuln = models.Vulnerability(cve_id="CVE-2026-1234", severity="CRITICAL")
    session.add(vuln)
    scan = models.HostVulnerabilityScan(host_id=host.id, scanned_at=NOW)
    session.add(scan)
    session.flush()
    session.add(models.HostVulnerabilityFinding(
        scan_id=scan.id, vulnerability_id=vuln.id, package_name="openssl",
        installed_version="1.0", fixed_version="1.1", severity="CRITICAL",
    ))  # fmt: skip
    session.commit()
    [item] = auto_update_health.host_facts(session, host)["critical_eligible"]
    assert item["fix_id"] == "CVE-2026-1234"
    assert item["eligible_at"].startswith(seen.date().isoformat())


def test_an_opted_out_host_has_nothing_overdue(session, automation, cve_data):
    host = _host(session)
    host.auto_update_opt_out = True
    _policy(session, host)
    session.commit()
    facts = auto_update_health.host_facts(session, host)
    assert facts["policy"] is None and facts["critical_eligible"] == []
