# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Resolving, dispatching and ingesting file watches — Phase 21.1 S7."""

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence import models
from backend.services import file_watch_service as fws


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


class FakeHost:
    def __init__(self, platform="linux", serves=True, host_id=None):
        self.id = host_id or uuid.uuid4()
        self.platform = platform
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


def _watch(db, name, paths):
    watch = models.FileWatch(id=uuid.uuid4(), name=name)
    db.add(watch)
    db.flush()
    for path, platforms in paths:
        db.add(
            models.FileWatchPath(
                id=uuid.uuid4(),
                watch_id=watch.id,
                path=path,
                platforms=platforms,
            )
        )
    return watch


def _assign(db, watch, host, enabled=True):
    db.add(
        models.FileWatchAssignment(
            id=uuid.uuid4(),
            watch_id=watch.id,
            host_id=host.id,
            enabled=enabled,
        )
    )
    db.flush()


class TestResolution:
    def test_assigned_paths_reach_the_host(self, db):
        host = FakeHost()
        _assign(db, _watch(db, "base", [("/etc/hosts", None)]), host)
        assert fws.resolve_paths(db, host) == ["/etc/hosts"]

    def test_a_disabled_assignment_contributes_nothing(self, db):
        host = FakeHost()
        _assign(db, _watch(db, "base", [("/etc/hosts", None)]), host, enabled=False)
        assert fws.resolve_paths(db, host) == []

    def test_paths_for_another_platform_are_not_sent(self, db):
        """THE DEFECT: a path sent to a host it does not apply to comes back
        ``absent`` -- and absent means 'should be here and is not', i.e.
        drift. A curated list naming /etc/ssh/sshd_config would show every
        Windows box as having deleted it."""
        host = FakeHost(platform="windows")
        _assign(
            db,
            _watch(
                db,
                "mixed",
                [
                    ("/etc/ssh/sshd_config", ["linux", "freebsd"]),
                    ("C:\\Windows\\System32\\drivers\\etc\\hosts", ["windows"]),
                ],
            ),
            host,
        )
        assert fws.resolve_paths(db, host) == [
            "C:\\Windows\\System32\\drivers\\etc\\hosts"
        ]

    def test_no_platform_list_means_every_platform(self, db):
        host = FakeHost(platform="openbsd")
        _assign(db, _watch(db, "base", [("/etc/rc.conf", None)]), host)
        assert fws.resolve_paths(db, host) == ["/etc/rc.conf"]

    def test_duplicates_across_watches_collapse(self, db):
        host = FakeHost()
        _assign(db, _watch(db, "a", [("/etc/hosts", None)]), host)
        _assign(db, _watch(db, "b", [("/etc/hosts", None), ("/etc/motd", None)]), host)
        assert fws.resolve_paths(db, host) == ["/etc/hosts", "/etc/motd"]

    def test_a_dangling_shared_reference_is_logged_not_silent(self, db, caplog):
        """A soft cross-partition reference can outlive its catalog entry.
        Contributing no paths silently would leave the host with an empty
        watch list an operator believes is populated -- and an empty list
        compares as 'nothing to check', not as an error."""
        host = FakeHost()
        db.add(
            models.FileWatchAssignment(
                id=uuid.uuid4(),
                shared_watch_id=uuid.uuid4(),
                host_id=host.id,
                enabled=True,
            )
        )
        db.flush()
        with caplog.at_level("WARNING"):
            assert fws.resolve_paths(db, host, shared_lookup=lambda _id: None) == []
        assert "not in the catalog" in caplog.text


class TestDispatch:
    def test_it_is_shaped_as_a_one_query_pack(self):
        """So the agent needs no new command and the result path is the one
        S4 already proved in production."""
        payload = fws.build_dispatch(["/etc/hosts"], run_id="r1")
        assert payload["run_id"] == "r1"
        assert len(payload["queries"]) == 1
        assert payload["queries"][0]["required_tables"] == [fws.WATCH_TABLE]

    def test_the_paths_travel_as_table_params(self):
        """The watched paths are server-held policy; the host cannot know
        them, so they must accompany the dispatch."""
        payload = fws.build_dispatch(["/etc/hosts", "/etc/motd"])
        assert payload["table_params"][fws.WATCH_TABLE]["paths"] == [
            "/etc/hosts",
            "/etc/motd",
        ]

    def test_the_query_names_columns_explicitly(self):
        """A contract that grows a column must not silently change the shape
        of what ingestion receives."""
        assert "*" not in fws.WATCH_SQL
        for column in fws.WATCH_COLUMNS:
            assert column in fws.WATCH_SQL

    def test_only_hosts_that_advertise_the_table_are_dispatched_to(self):
        assert fws.should_dispatch(FakeHost(serves=True)) is True
        assert fws.should_dispatch(FakeHost(serves=False)) is False


class TestIngestion:
    def _rows(self):
        return [
            {
                "path": "/etc/hosts",
                "state": "present",
                "sha256": "a" * 64,
                "mode": "0644",
                "owner": "root",
                "type": "regular",
            },
            {"path": "/etc/motd", "state": "absent"},
            {"path": "/etc/shadow", "state": "unreadable"},
        ]

    def test_every_reported_path_is_stored(self, db):
        host_id = uuid.uuid4()
        assert fws.ingest_rows(db, host_id, self._rows()) == 3
        stored = {
            r.path: r.state
            for r in db.query(models.HostFileState).filter_by(host_id=host_id)
        }
        assert stored == {
            "/etc/hosts": "present",
            "/etc/motd": "absent",
            "/etc/shadow": "unreadable",
        }

    def test_absent_and_unreadable_are_stored_not_skipped(self, db):
        """Storing only the files that exist makes a DELETED config
        indistinguishable from an unwatched one, and the differ then misses
        the deletion entirely."""
        host_id = uuid.uuid4()
        fws.ingest_rows(db, host_id, self._rows())
        states = {
            r.state for r in db.query(models.HostFileState).filter_by(host_id=host_id)
        }
        assert {"absent", "unreadable"} <= states

    def test_a_second_run_updates_rather_than_duplicating(self, db):
        host_id = uuid.uuid4()
        fws.ingest_rows(db, host_id, self._rows())
        changed = self._rows()
        changed[0]["sha256"] = "b" * 64
        fws.ingest_rows(db, host_id, changed)
        rows = db.query(models.HostFileState).filter_by(host_id=host_id).all()
        assert len(rows) == 3
        assert next(r for r in rows if r.path == "/etc/hosts").sha256 == "b" * 64

    def test_a_path_dropped_from_the_watch_list_is_removed(self, db):
        """Stale state is worse than none: the differ would compare a hash
        from weeks ago against a live one and report drift nobody can
        reproduce."""
        host_id = uuid.uuid4()
        fws.ingest_rows(db, host_id, self._rows())
        fws.ingest_rows(db, host_id, self._rows()[:1])
        paths = {
            r.path for r in db.query(models.HostFileState).filter_by(host_id=host_id)
        }
        assert paths == {"/etc/hosts"}

    def test_a_row_with_no_state_is_dropped_not_stored_null(self, db, caplog):
        """A nullable state reintroduces the exact ambiguity the column
        exists to remove."""
        host_id = uuid.uuid4()
        with caplog.at_level("WARNING"):
            fws.ingest_rows(db, host_id, [{"path": "/etc/x"}])
        assert db.query(models.HostFileState).filter_by(host_id=host_id).count() == 0
        assert "no path/state" in caplog.text

    def test_unexpected_columns_from_a_newer_agent_are_ignored(self, db):
        """A newer agent may report a column this server does not model; that
        must not break ingestion of the columns it does."""
        host_id = uuid.uuid4()
        fws.ingest_rows(
            db,
            host_id,
            [{"path": "/etc/hosts", "state": "present", "selinux_label": "x"}],
        )
        assert db.query(models.HostFileState).filter_by(host_id=host_id).count() == 1
