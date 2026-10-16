# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The OS end-of-life registry refreshes itself (Phase 14.3).

It used to fill only when someone pressed "Refresh EOL data", so a new server
showed every host as Unknown (production, 2026-10-16: 0 releases).  Now:
empty -> refresh; last success older than a day -> refresh; a failure is
retried after an hour, not on every pass; nothing runs unlicensed."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import os_lifecycle_tick as tick

NOW = datetime(2026, 10, 16, 12, 0, 0)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            models.SharedOsLifecycle.__table__,
            models.OsLifecycleIngestionLog.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _release(db):
    columns = {c.name for c in models.SharedOsLifecycle.__table__.columns}
    row = models.SharedOsLifecycle(os_name="Ubuntu", os_version="26.04")
    for name, value in (("id", uuid.uuid4()), ("source", "endoflife.date")):
        if name in columns:
            setattr(row, name, value)
    for column in models.SharedOsLifecycle.__table__.columns:
        if (
            not column.nullable
            and getattr(row, column.name) is None
            and column.default is None
        ):
            setattr(row, column.name, NOW if "at" in column.name else "x")
    db.add(row)
    db.commit()


def _log(db, status, started, completed=None):
    db.add(
        models.OsLifecycleIngestionLog(
            source="endoflife.date",
            status=status,
            started_at=started,
            completed_at=completed,
        )
    )
    db.commit()


def test_an_empty_registry_is_due(db):
    assert tick.refresh_due(db, NOW) == "empty"


def test_an_empty_registry_after_a_recent_failure_waits_an_hour(db):
    _log(db, "failed", NOW - timedelta(minutes=10), NOW - timedelta(minutes=9))
    assert tick.refresh_due(db, NOW) is None
    assert tick.refresh_due(db, NOW + timedelta(hours=1)) == "empty"


def test_a_fresh_success_is_not_due_and_a_day_old_one_is(db):
    _release(db)
    _log(db, "success", NOW - timedelta(hours=2), NOW - timedelta(hours=2))
    assert tick.refresh_due(db, NOW) is None
    assert tick.refresh_due(db, NOW + timedelta(days=1)) == "stale"


def test_rows_with_no_successful_refresh_on_record_are_stale(db):
    _release(db)  # e.g. seeded, or the log was pruned
    assert tick.refresh_due(db, NOW) == "stale"


def test_the_tick_refreshes_through_the_engine_when_due():
    engine = MagicMock()
    engine._lifecycle_service.refresh_eol.return_value = {"releases_processed": 42}
    session = MagicMock()
    with patch.object(tick, "_engine", return_value=engine), patch.object(
        tick, "shared_sessionmaker", return_value=lambda: session
    ), patch.object(tick, "refresh_due", return_value="empty"):
        assert tick.run_one_tick() == "empty"
    engine._lifecycle_service.refresh_eol.assert_called_once_with(session, tick.models)
    session.close.assert_called_once()


def test_a_failed_refresh_is_contained():
    engine = MagicMock()
    engine._lifecycle_service.refresh_eol.side_effect = RuntimeError("offline")
    session = MagicMock()
    with patch.object(tick, "_engine", return_value=engine), patch.object(
        tick, "shared_sessionmaker", return_value=lambda: session
    ), patch.object(tick, "refresh_due", return_value="stale"):
        assert tick.run_one_tick() is None
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_nothing_runs_or_starts_unlicensed():
    with patch.object(tick, "_engine", return_value=None):
        assert tick.run_one_tick() is None
        assert tick.start_if_licensed() is None
