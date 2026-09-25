# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The advisor's own fact collection -- Phase 21.2 S2b.

Without it every fact rule is ``not_collected`` forever. The cases that matter
are the ones that would either spam hosts (re-dispatching to an offline host
every tick) or quietly stop collecting (a new rule's table never asked for),
plus bounded storage: query-pack runs have no retention of their own.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import advisor_collection as col

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
QUERIES = [
    {
        "name": "advisor.mounts",
        "sql": "SELECT path FROM mounts",
        "required_tables": ["mounts"],
    }
]


class Engine:  # pylint: disable=too-few-public-methods
    def __init__(self, queries=None):
        self.queries = QUERIES if queries is None else queries

    def collection_queries(self, _rules, prefix):
        assert prefix == "advisor."
        return self.queries


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def _host(db, active=True):
    host = models.Host(
        id=uuid.uuid4(), fqdn="h", active=active, approval_status="approved"
    )
    db.add(host)
    db.commit()
    return host


def _run(db, host, started, completed=True, names=("advisor.mounts",), **kw):
    run = models.QueryPackRun(
        id=uuid.uuid4(),
        host_id=host.id,
        pack_name=col.ADVISOR_PACK_NAME,
        status="success",
        started_at=started,
        completed_at=started + timedelta(minutes=1) if completed else None,
        **kw,
    )
    db.add(run)
    db.flush()
    for name in names if completed else ():
        db.add(
            models.QueryPackResultRow(
                id=uuid.uuid4(),
                run_id=run.id,
                query_name=name,
                status="ok",
                collected_at=started,
            )
        )
    db.commit()
    return run


def _collect(db, hosts, engine=None, payload=("q",)):
    summary = {
        k: 0
        for k in (
            "collections_queued",
            "collections_refused",
            "collections_nothing_to_run",
            "collections_no_engine",
            "collections_pruned",
        )
    }
    built = None if payload is None else {"queries": list(payload)}
    with patch.object(col.dispatch, "build_payload", return_value=built), patch.object(
        col.dispatch, "queue_run"
    ) as queued:
        col.collect(engine or Engine(), db, hosts, [], NOW, summary)
    return summary, queued


class TestDueness:
    def test_a_host_never_collected_is_asked(self, db):
        host = _host(db)
        summary, queued = _collect(db, [host])
        assert summary["collections_queued"] == 1 and queued.called
        run = db.query(models.QueryPackRun).one()
        assert run.pack_name == col.ADVISOR_PACK_NAME and run.completed_at is None

    def test_a_recent_collection_is_not_repeated(self, db):
        host = _host(db)
        _run(db, host, NOW - timedelta(hours=1))
        summary, _ = _collect(db, [host])
        assert summary["collections_queued"] == 0

    def test_an_old_collection_is_refreshed_inside_the_freshness_limit(self, db):
        host = _host(db)
        _run(db, host, NOW - col.COLLECT_INTERVAL)
        assert _collect(db, [host])[0]["collections_queued"] == 1
        assert col.COLLECT_INTERVAL <= timedelta(days=1) / 2

    def test_a_new_rules_table_does_not_wait_for_the_interval(self, db):
        host = _host(db)
        _run(db, host, NOW - timedelta(hours=1), names=("advisor.users",))
        assert _collect(db, [host])[0]["collections_queued"] == 1

    def test_a_pending_run_blocks_another_until_the_grace_ends(self, db):
        """An offline host must not collect a queued command every tick."""
        host = _host(db)
        _run(db, host, NOW - timedelta(hours=1), completed=False)
        assert _collect(db, [host])[0]["collections_queued"] == 0
        db.query(models.QueryPackRun).update(
            {"started_at": NOW - col.PENDING_GRACE - timedelta(minutes=1)}
        )
        db.commit()
        assert _collect(db, [host])[0]["collections_queued"] == 1

    def test_a_down_host_is_not_dispatched_to(self, db):
        host = _host(db, active=False)
        assert _collect(db, [host])[0]["collections_queued"] == 0

    def test_no_fact_rules_means_no_collection(self, db):
        host = _host(db)
        summary, queued = _collect(db, [host], engine=Engine(queries=[]))
        assert summary["collections_queued"] == 0 and not queued.called


class TestDispatch:
    def test_a_host_serving_none_of_the_tables_is_not_asked(self, db):
        host = _host(db)
        summary, queued = _collect(db, [host], payload=())
        assert summary["collections_nothing_to_run"] == 1 and not queued.called
        assert db.query(models.QueryPackRun).count() == 0

    def test_no_query_pack_engine_stops_the_pass(self, db):
        hosts = [_host(db), _host(db)]
        summary, _ = _collect(db, hosts, payload=None)
        assert summary["collections_no_engine"] == 1

    def test_a_refused_command_leaves_no_run_and_keeps_other_writes(self, db):
        host = _host(db)
        db.add(
            models.AdvisorResult(
                host_id=host.id,
                rule_source="shared",
                rule_key="A",
                outcome="fires",
                evaluated_at=NOW,
            )
        )
        with patch.object(
            col.dispatch, "build_payload", return_value={"queries": ["q"]}
        ), patch.object(col.dispatch, "queue_run", side_effect=ValueError("old agent")):
            summary = {
                k: 0
                for k in (
                    "collections_queued",
                    "collections_refused",
                    "collections_pruned",
                )
            }
            col.collect(Engine(), db, [host], [], NOW, summary)
        db.commit()
        assert summary["collections_refused"] == 1
        assert db.query(models.QueryPackRun).count() == 0
        assert db.query(models.AdvisorResult).count() == 1


class TestPruning:
    def test_only_the_newest_completed_run_is_kept(self, db):
        host = _host(db)
        newest = _run(db, host, NOW - timedelta(hours=1))
        _run(db, host, NOW - timedelta(hours=13))
        _run(db, host, NOW - timedelta(hours=25))
        summary, _ = _collect(db, [host])
        db.commit()
        assert summary["collections_pruned"] == 2
        assert [r.id for r in db.query(models.QueryPackRun).all()] == [newest.id]
        assert {r.run_id for r in db.query(models.QueryPackResultRow).all()} == {
            newest.id
        }

    def test_an_abandoned_pending_run_is_pruned(self, db):
        host = _host(db)
        _run(db, host, NOW - timedelta(hours=1))
        _run(db, host, NOW - col.PENDING_GRACE - timedelta(hours=1), completed=False)
        assert _collect(db, [host])[0]["collections_pruned"] == 1

    def test_other_packs_runs_are_never_touched(self, db):
        host = _host(db)
        _run(db, host, NOW - timedelta(hours=1))
        other = models.QueryPackRun(
            id=uuid.uuid4(),
            host_id=host.id,
            pack_name="mine",
            status="success",
            started_at=NOW - timedelta(days=9),
            completed_at=NOW - timedelta(days=9),
        )
        db.add(other)
        db.commit()
        _collect(db, [host])
        db.commit()
        assert db.get(models.QueryPackRun, other.id) is not None
