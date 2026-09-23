# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The file-watch collection tick -- Phase 21.1 S7.

Without this loop an assignment is storage: an operator binds a watch list to
a host and nothing ever collects it. The cases worth testing are the ones
where dispatching would do HARM, because each of them silently destroys the
baseline the golden-host differ compares against.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence import models
from backend.services import file_watch_service as fws
from backend.services import file_watch_tick as tick


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


NOW = datetime.now(timezone.utc).replace(tzinfo=None)


class FakeHost:
    def __init__(self, serves=True, platform="linux"):
        self.id = uuid.uuid4()
        self.platform = platform
        self.site_id = None
        served = {"users": "native"}
        if serves:
            served[fws.WATCH_TABLE] = "native"
        self.agent_capabilities = json.dumps(
            {
                "schema_version": 1,
                "commands": [],
                "facts": {
                    "contract_version": 2,
                    "served": served,
                    "unsupported": {},
                    "not_applicable": {},
                },
            }
        )


def _assignment(db, host, last=None, interval=60, paths=("/etc/hosts",)):
    watch = models.FileWatch(id=uuid.uuid4(), name=f"w-{uuid.uuid4().hex[:6]}")
    db.add(watch)
    db.flush()
    for path in paths:
        db.add(models.FileWatchPath(id=uuid.uuid4(), watch_id=watch.id, path=path))
    assignment = models.FileWatchAssignment(
        id=uuid.uuid4(),
        watch_id=watch.id,
        host_id=host.id,
        enabled=True,
        interval_minutes=interval,
        last_dispatched_at=last,
    )
    db.add(assignment)
    db.flush()
    return assignment


class TestDueness:
    def test_a_never_dispatched_assignment_is_due_immediately(self, db):
        """Otherwise a newly created assignment sits silent for a full
        interval and an operator thinks it is broken."""
        host = FakeHost()
        _assignment(db, host, last=None)
        assert tick.due_assignments(db, host, NOW)

    def test_an_assignment_inside_its_window_is_not_due(self, db):
        host = FakeHost()
        _assignment(db, host, last=NOW - timedelta(minutes=10), interval=60)
        assert tick.due_assignments(db, host, NOW) == []

    def test_an_assignment_past_its_window_is_due(self, db):
        host = FakeHost()
        _assignment(db, host, last=NOW - timedelta(minutes=61), interval=60)
        assert tick.due_assignments(db, host, NOW)

    def test_an_interval_below_the_floor_is_clamped(self, db):
        """A one-minute watch over a fleet is a self-inflicted outage."""
        host = FakeHost()
        _assignment(db, host, last=NOW - timedelta(minutes=2), interval=1)
        assert tick.due_assignments(db, host, NOW) == []

    def test_a_disabled_assignment_is_never_due(self, db):
        host = FakeHost()
        assignment = _assignment(db, host, last=None)
        assignment.enabled = False
        db.flush()
        assert tick.due_assignments(db, host, NOW) == []


class TestDispatchRefusals:
    """Each of these would silently destroy the differ's baseline."""

    def _summary(self):
        return {
            "due": 0,
            "queued": 0,
            "nothing_to_watch": 0,
            "not_equipped": 0,
            "deferred": 0,
        }

    def test_a_host_with_no_paths_is_not_dispatched_to(self, db):
        """THE DEFECT: an empty watch list comes back a clean success with
        zero rows, and ingestion then DELETES every path recorded for that
        host -- turning a misconfigured assignment into a silent loss of the
        baseline."""
        host = FakeHost()
        assignment = _assignment(db, host, paths=())
        summary = self._summary()
        assert tick._dispatch_one(db, host, [assignment], NOW, summary) is False
        assert summary["nothing_to_watch"] == 1

    def test_an_agent_that_cannot_serve_the_table_is_skipped(self, db):
        """Not an error: an agent too old for the contract would answer with
        an error and the run would grade as a FAILURE, which reads as 'this
        host is broken' rather than 'not equipped yet'."""
        host = FakeHost(serves=False)
        assignment = _assignment(db, host)
        summary = self._summary()
        assert tick._dispatch_one(db, host, [assignment], NOW, summary) is False
        assert summary["not_equipped"] == 1

    def test_the_cursor_advances_even_when_dispatch_did_not_go(self, db):
        """The window arrived; it simply could not be served. Leaving it
        unset re-evaluates the same assignment every tick forever -- for an
        offline host that is a log line a minute until somebody notices."""
        host = FakeHost(serves=False)
        assignment = _assignment(db, host, last=None)
        tick._touch(db, [assignment], NOW)
        assert assignment.last_dispatched_at == NOW


class TestIngestionSafety:
    def test_a_failed_run_does_not_clear_recorded_state(self, db):
        """A host that was ASKED and could not answer must keep the state we
        already hold. Ingesting its empty row set would erase the baseline."""
        from backend.api.handlers import query_pack_handlers as handlers

        host_id = uuid.uuid4()
        fws.ingest_rows(db, host_id, [{"path": "/etc/hosts", "state": "present"}])
        db.commit()

        class Run:
            id = uuid.uuid4()

        Run.host_id = host_id
        handlers._ingest_file_watch(
            db,
            Run,
            {
                "results": [
                    {
                        "name": fws.WATCH_QUERY_NAME,
                        "status": models.QUERY_STATUS_NOT_COVERED,
                        "reason": "provider_failed",
                        "rows": [],
                    }
                ]
            },
        )
        assert db.query(models.HostFileState).filter_by(host_id=host_id).count() == 1

    def test_a_successful_run_is_projected(self, db):
        from backend.api.handlers import query_pack_handlers as handlers

        host_id = uuid.uuid4()

        class Run:
            id = uuid.uuid4()

        Run.host_id = host_id
        handlers._ingest_file_watch(
            db,
            Run,
            {
                "results": [
                    {
                        "name": fws.WATCH_QUERY_NAME,
                        "status": models.QUERY_STATUS_OK,
                        "rows": [
                            {"path": "/etc/hosts", "state": "present", "sha256": "a"},
                            {"path": "/etc/motd", "state": "absent"},
                        ],
                    }
                ]
            },
        )
        assert db.query(models.HostFileState).filter_by(host_id=host_id).count() == 2

    def test_an_ordinary_pack_result_is_left_alone(self, db):
        """Only a file-watch query projects; every other pack is untouched."""
        from backend.api.handlers import query_pack_handlers as handlers

        host_id = uuid.uuid4()

        class Run:
            id = uuid.uuid4()

        Run.host_id = host_id
        handlers._ingest_file_watch(
            db,
            Run,
            {
                "results": [
                    {
                        "name": "listening ports",
                        "status": models.QUERY_STATUS_OK,
                        "rows": [{"port": 22}],
                    }
                ]
            },
        )
        assert db.query(models.HostFileState).count() == 0
