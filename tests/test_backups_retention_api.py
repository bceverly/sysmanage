# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Grandfather-father-son retention (ROADMAP 24.6): setting it needs the
Pro+ backup engine, but once set it is always sent with the storage host's
prune -- a lapsed license must never make a prune delete history the
operator chose to keep."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.api import backups as api
from backend.api import backups_retention as retention
from backend.persistence import models
from backend.services import backup_jobs as jobs
from tests.services.test_backup_results import _setup
from tests.test_backups_api import MANAGER, _status

GFS = {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6}


def _engine(preview=None):
    return SimpleNamespace(retention_preview=preview or (lambda names, values: {
        "kept": sorted(names)[-values["keep_last"]:],
        "removed": sorted(names)[: -values["keep_last"]],
    }))  # fmt: skip


@pytest.mark.asyncio
async def test_setting_gfs_needs_the_engine(session):
    s = _setup(session)
    body = api.PolicyBody(keep_last=7, **GFS)
    with patch.object(retention, "_engine", return_value=None):
        assert (
            await _status(api.put_policy(str(s.host.id), body, session, MANAGER)) == 402
        )
    assert s.policy.keep_daily is None
    with patch.object(retention, "_engine", return_value=_engine()):
        saved = await api.put_policy(str(s.host.id), body, session, MANAGER)
    assert (saved["keep_daily"], saved["keep_weekly"], saved["keep_monthly"]) == (
        7,
        4,
        6,
    )


@pytest.mark.asyncio
async def test_a_lapsed_license_keeps_gfs_and_can_still_save_other_settings(session):
    s = _setup(session)
    s.policy.keep_daily, s.policy.keep_weekly, s.policy.keep_monthly = 7, 4, 6
    session.flush()
    unchanged = api.PolicyBody(keep_last=7, interval_hours=12, **GFS)
    with patch.object(retention, "_engine", return_value=None):
        saved = await api.put_policy(str(s.host.id), unchanged, session, MANAGER)
        assert saved["interval_hours"] == 12 and saved["keep_daily"] == 7
        cleared = api.PolicyBody(keep_last=7)
        assert (
            await _status(api.put_policy(str(s.host.id), cleared, session, MANAGER))
            == 402
        )
    assert jobs.prune_keep(s.policy) == {"keep_last": 7, **GFS}  # still honored


def test_the_prune_job_carries_only_the_counts_that_are_set(session):
    s = _setup(session)
    assert jobs.prune_keep(s.policy) == {"keep_last": s.policy.keep_last}
    s.policy.keep_weekly = 8
    assert jobs.prune_keep(s.policy) == {
        "keep_last": s.policy.keep_last,
        "keep_weekly": 8,
    }
    job = jobs.storage_configuration(s.policy, s.target, s.host)
    assert job["jobs"]["prune"] == {"keep_last": s.policy.keep_last, "keep_weekly": 8}


@pytest.mark.asyncio
async def test_out_of_range_counts_are_refused(session):
    s = _setup(session)
    with patch.object(retention, "_engine", return_value=_engine()):
        for bad in ({"keep_daily": 3651}, {"keep_weekly": -1}, {"keep_monthly": 241}):
            body = api.PolicyBody(keep_last=7, **bad)
            assert (
                await _status(api.put_policy(str(s.host.id), body, session, MANAGER))
                == 422
            )


def _snapshot(session, s, name, repository_dir=None):
    session.add(models.BackupSnapshot(
        policy_id=s.policy.id, host_id=s.host.id, name=name, repository_dir=repository_dir,
        created_at=datetime(2026, 10, 20), seen_at=datetime(2026, 10, 20),
    ))  # fmt: skip


@pytest.mark.asyncio
async def test_the_preview_reads_the_current_repository_only(session):
    s = _setup(session)
    for name in ("20261020T030000Z", "20261021T030000Z", "20261022T030000Z"):
        _snapshot(session, s, name)
    _snapshot(session, s, "20261023T030000Z", repository_dir="some-other-repo")
    session.flush()
    seen = {}

    def preview(names, values):
        seen.update(names=sorted(names), values=values)
        return {"kept": [], "removed": []}

    with patch.object(retention, "_engine", return_value=_engine(preview)):
        await retention.retention_preview(
            str(s.host.id), keep_last=2, keep_weekly=3, db=session
        )
    assert seen["names"] == ["20261020T030000Z", "20261021T030000Z", "20261022T030000Z"]
    assert seen["values"] == {
        "keep_last": 2,
        "keep_daily": 0,
        "keep_weekly": 3,
        "keep_monthly": 0,
    }
    with patch.object(retention, "_engine", return_value=None):
        assert await _status(retention.retention_preview(str(s.host.id), keep_last=2,
                                                         db=session)) == 402  # fmt: skip
