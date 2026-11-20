# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Restore readiness (ROADMAP 27.1, Enterprise backup_ops_engine): the facts
gathered from a policy's runs, the real compiled engine's verdict, the API
and its 402 without the engine."""

# pylint: disable=redefined-outer-name

import json
import uuid
from datetime import timedelta

import pytest

from backend.api import backups_readiness as api
from backend.persistence import models
from backend.services import backup_readiness as readiness
from tests.services.test_backup_results import _setup
from tests.services.test_backup_tick import NOW
from tests.test_backups_api import MANAGER, NOBODY, _status

GB = 1000 * 1000 * 1000


@pytest.fixture
def ops_engine(monkeypatch):
    from tests._engine_loader import (  # pylint: disable=import-outside-toplevel
        require_engine,
    )

    eng = require_engine("backup_ops_engine")
    monkeypatch.setattr(readiness, "engine", lambda: eng)
    return eng


def _run(session, policy, host_id, action, at, result, status="ok"):
    session.add(
        models.BackupRun(
            id=uuid.uuid4(), policy_id=policy.id, host_id=host_id, action=action,
            status=status, queued_at=at, finished_at=at, result=json.dumps(result),
        )
    )  # fmt: skip
    session.flush()


def _backed_up(session, hours_ago=10):
    s = _setup(session)
    _run(session, s.policy, s.host.id, "capture", NOW - timedelta(hours=hours_ago),
         {"seconds": 100, "read_bytes": 2 * GB, "reused_bytes": 40 * GB,
          "new_bytes": 10 * GB})  # fmt: skip
    session.commit()
    return s


def test_facts_come_from_the_runs(session):
    s = _backed_up(session)
    s.policy.verify_interval_days = 7
    _run(session, s.policy, s.host.id, "verify", NOW - timedelta(days=2),
         {"seconds": 1000, "check": {"bytes": 100 * GB, "read_all": True}})  # fmt: skip
    _run(session, s.policy, s.host.id, "restore", NOW - timedelta(days=1),
         {"seconds": 18, "restore": {"bytes": 8}})  # fmt: skip
    session.commit()

    facts = readiness.facts(session, s.policy)

    assert facts["interval_hours"] == 24 and facts["rpo_hours"] is None
    assert facts["last_good_at"] == NOW - timedelta(hours=10)
    assert facts["snapshot_bytes"] == 50 * GB
    assert facts["evidence"] == [
        {"kind": "verify", "passed_at": NOW - timedelta(days=2), "max_age_days": 7}
    ]
    kinds = sorted(t["kind"] for t in facts["throughputs"])
    assert kinds == ["capture", "restore", "verify"]


def test_the_fleet_view_from_the_real_engine(session, ops_engine, monkeypatch):
    s = _backed_up(session)
    s.policy.verify_interval_days = 7
    _run(session, s.policy, s.host.id, "verify", NOW - timedelta(days=2),
         {"seconds": 1000, "check": {"bytes": 100 * GB}})  # fmt: skip
    session.commit()

    out = readiness.fleet(session, ops_engine, NOW)

    row = out["hosts"][0]
    assert row["state"] == "ready"
    # 50 GB at the verification's 100 MB/s.
    assert row["rto"] == {"seconds": 500, "basis": "verify", "mb_per_s": 100.0}
    assert row["proof"]["kind"] == "verify" and row["proof"]["fresh"] is True
    assert out["counts"]["ready"] == 1


def test_without_proof_a_recent_backup_is_unproven(session, ops_engine):
    _backed_up(session)
    row = readiness.fleet(session, ops_engine, NOW)["hosts"][0]
    assert row["state"] == "unproven" and row["reasons"] == ["never_proven"]


def test_an_old_backup_breaches_its_rpo(session, ops_engine):
    s = _backed_up(session, hours_ago=60)
    row = readiness.fleet(session, ops_engine, NOW)["hosts"][0]
    assert row["state"] == "rpo_breached" and row["rpo"]["target_hours"] == 48
    s.policy.rpo_hours = 72
    session.commit()
    assert readiness.fleet(session, ops_engine, NOW)["hosts"][0]["state"] == "unproven"


@pytest.mark.asyncio
async def test_the_api_needs_the_engine(session, monkeypatch):
    monkeypatch.setattr(readiness, "engine", lambda: None)
    assert await _status(lambda: api.backups_readiness(session)) == 402
    s = _backed_up(session)
    body = api.ReadinessBody(rpo_hours=12)
    assert (
        await _status(
            lambda: api.put_backup_readiness(str(s.host.id), body, session, MANAGER)
        )
        == 402
    )


@pytest.mark.asyncio
async def test_setting_the_rpo_needs_the_role_and_a_policy(session, ops_engine):
    s = _backed_up(session)
    body = api.ReadinessBody(rpo_hours=12)
    assert (
        await _status(
            lambda: api.put_backup_readiness(str(s.host.id), body, session, NOBODY)
        )
        == 403
    )
    verdict = api.put_backup_readiness(str(s.host.id), body, session, MANAGER)
    assert verdict["rpo"]["target_hours"] == 12
    assert session.get(models.BackupPolicy, s.policy.id).rpo_hours == 12
    api.put_backup_readiness(str(s.host.id), api.ReadinessBody(), session, MANAGER)
    assert session.get(models.BackupPolicy, s.policy.id).rpo_hours is None


def test_the_rpo_is_bounded():
    with pytest.raises(ValueError):
        api.ReadinessBody(rpo_hours=0)
    with pytest.raises(ValueError):
        api.ReadinessBody(rpo_hours=api.MAX_RPO_HOURS + 1)
