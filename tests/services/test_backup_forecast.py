# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Capacity forecasting inputs (Pro+ 24.6): bytes written by the last 30
days of captures, bytes freed by that period's prunes, and the days of
history behind them -- handed to the engine with the filesystem's space."""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.persistence import models
from backend.services import backup_forecast as forecast
from tests.services.test_backup_results import (  # noqa: F401  # pylint: disable=unused-import
    _setup,
    sent,
)

NOW = datetime(2026, 11, 1)


def _snap(session, s, days_ago, new=0, unique=0, gone_days_ago=None):
    session.add(models.BackupSnapshot(
        id=uuid.uuid4(), policy_id=s.policy.id, host_id=s.host.id,
        name=f"2026{days_ago:04d}T000000Z", created_at=NOW - timedelta(days=days_ago),
        seen_at=NOW, new_bytes=new, unique_bytes=unique,
        gone_at=NOW - timedelta(days=gone_days_ago) if gone_days_ago is not None else None,
    ))  # fmt: skip
    session.flush()


def test_inputs_cover_the_last_30_days(session, sent):
    s = _setup(session)
    _snap(session, s, 60, new=999)  # before the period: not written now
    _snap(session, s, 20, new=100)
    _snap(session, s, 5, new=50)
    _snap(session, s, 40, unique=30, gone_days_ago=10)  # freed in the period
    _snap(session, s, 50, unique=70, gone_days_ago=45)  # freed before it
    assert forecast.inputs(session, s.target, NOW) == {
        "written": 150, "freed": 30, "days": 30,
    }  # fmt: skip


def test_young_targets_count_only_their_days(session, sent):
    s = _setup(session)
    _snap(session, s, 6, new=60)
    assert forecast.inputs(session, s.target, NOW)["days"] == 6


def test_no_engine_or_no_space_means_no_forecast(session, sent, monkeypatch):
    s = _setup(session)
    health = {"space": {"total_bytes": 1000, "available_bytes": 400},
              "space_low_percent": 85, "space_critical_percent": 95}  # fmt: skip
    monkeypatch.setattr(forecast, "_engine", lambda: None)
    assert forecast.for_target(session, s.target, health, NOW) is None
    seen = {}
    engine = SimpleNamespace(
        capacity_forecast=lambda *a: seen.setdefault("args", a) and {"ok": 1}
    )
    monkeypatch.setattr(forecast, "_engine", lambda: engine)
    assert forecast.for_target(session, s.target, {"space": None}, NOW) is None
    assert forecast.for_target(session, s.target, health, NOW) == {"ok": 1}
    assert seen["args"][3:] == (1000, 400, 85, 95)
