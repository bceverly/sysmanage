# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisory tick (2026-11-23): the vendor advisory catalog -- now every
distribution's feed -- was filled only when someone pressed Refresh, and a
host's applicable advisories recomputed only from its own page.  The tick
refreshes a catalog that is empty or a day old, then recomputes every
approved host in every host database."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisory_tick as tick

NOW = datetime(2026, 11, 23, 12, 0, 0)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[models.AdvisoryIngestionLog.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _log(db, status, started, completed=None):
    db.add(models.AdvisoryIngestionLog(source="debian", status=status,
                                       started_at=started, completed_at=completed))  # fmt: skip
    db.commit()


def test_a_catalog_never_refreshed_is_due(db):
    assert tick.refresh_due(db, NOW) == "empty"


def test_a_recent_failure_waits_an_hour(db):
    _log(db, "failed", NOW - timedelta(minutes=10), NOW - timedelta(minutes=9))
    assert tick.refresh_due(db, NOW) is None
    assert tick.refresh_due(db, NOW + timedelta(hours=1)) == "empty"


def test_a_fresh_success_is_not_due_and_a_day_old_one_is(db):
    _log(db, "success", NOW - timedelta(hours=2), NOW - timedelta(hours=2))
    assert tick.refresh_due(db, NOW) is None
    assert tick.refresh_due(db, NOW + timedelta(days=1)) == "stale"


def test_the_tick_refreshes_then_recomputes_every_approved_host():
    engine = MagicMock()
    service = engine._advisory_service  # pylint: disable=protected-access
    service.refresh_advisories.return_value = {"processed": {"debian": 3}}
    tenant_db = MagicMock()
    tenant_db.query.return_value.filter.return_value.all.return_value = [
        ("h1",),
        ("h2",),
    ]
    with patch.object(tick, "_engine", return_value=engine), \
            patch.object(tick, "shared_sessionmaker", return_value=MagicMock), \
            patch.object(tick, "refresh_due", return_value="stale"), \
            patch.object(tick, "iter_host_databases", return_value=[("tenant", "t1", tenant_db)]):  # fmt: skip
        assert tick.run_one_tick() == "stale"
    assert service.refresh_advisories.called
    assert [
        c.args[0] for c in service.compute_applicable_advisories.call_args_list
    ] == ["h1", "h2"]


def test_one_hosts_failure_does_not_stop_the_rest():
    engine = MagicMock()
    service = engine._advisory_service  # pylint: disable=protected-access
    service.compute_applicable_advisories.side_effect = [RuntimeError("boom"), {}]
    tenant_db = MagicMock()
    tenant_db.query.return_value.filter.return_value.all.return_value = [
        ("h1",),
        ("h2",),
    ]
    with patch.object(
        tick, "iter_host_databases", return_value=[("t", "t1", tenant_db)]
    ):
        assert (
            tick._recompute_all(engine, MagicMock()) == 1
        )  # pylint: disable=protected-access
    assert tenant_db.rollback.called


def test_nothing_runs_or_starts_unlicensed():
    with patch.object(tick, "_engine", return_value=None):
        assert tick.run_one_tick() is None
        assert tick.start_if_licensed() is None
