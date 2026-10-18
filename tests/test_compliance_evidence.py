# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Compliance evidence + the scheduled compliance scan (ROADMAP 24.4).

The agent reports what the compliance checks read; the server stores it per
host and scans each host when its evidence is newer than its latest scan, it
was never scanned, or its scan is a day old -- in every host database."""

import asyncio
import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.handlers.compliance_evidence_handlers import (
    handle_compliance_evidence_update,
)
from backend.persistence import models
from backend.persistence.db import Base
from backend.services import compliance_evidence as evidence
from backend.services import compliance_scan_tick as tick
from backend.websocket.messages import MessageType

NOW = datetime(2026, 10, 18, 12, 0, 0)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _host(db, fqdn="h.example.invalid", approved=True, active=True):
    host = models.Host(
        id=uuid.uuid4(), fqdn=fqdn, active=active,
        approval_status="approved" if approved else "pending",
    )  # fmt: skip
    db.add(host)
    db.commit()
    return host


def _scan(db, host, when):
    db.add(
        models.HostComplianceScan(
            host_id=host.id, scanned_at=when, compliance_grade="N/A", results=[]
        )
    )
    db.commit()


# -- storing ---------------------------------------------------------------------


def test_sections_keep_their_engine_types_and_nothing_else():
    cleaned = evidence.clean_sections(
        {"ssh_config": {"PermitRootLogin": "no"}, "umask": 27, "fips_enabled": False,
         "pam_modules": ["pam_unix.so"], "bogus": {"x": 1}}
    )  # fmt: skip
    assert cleaned["ssh_config"] == {"PermitRootLogin": "no"}
    assert cleaned["umask"] is None  # not a string: not collected
    assert cleaned["fips_enabled"] is False  # real evidence: FIPS off
    assert cleaned["pam_modules"] == ["pam_unix.so"]
    assert "bogus" not in cleaned
    assert cleaned["sysctl"] is None
    assert evidence.clean_sections("junk")["ssh_config"] is None


def test_a_report_replaces_the_hosts_previous_one(db):
    host = _host(db)
    evidence.apply_report(db, host, {"sections": {"umask": "022"}}, now=NOW)
    db.commit()
    evidence.apply_report(
        db, host,
        {"platform": "Linux", "sections": {"umask": "027"},
         "sources": {"umask": "ran", "junk": "x"},
         "collected_at": "2026-10-18T11:59:00+00:00"},
        now=NOW + timedelta(minutes=5),
    )  # fmt: skip
    db.commit()
    row = db.query(models.HostComplianceEvidence).one()
    assert json.loads(row.sections)["umask"] == "027"
    assert json.loads(row.sources) == {"umask": "ran"}
    assert row.platform == "Linux"
    assert row.collected_at == datetime(2026, 10, 18, 11, 59)
    assert row.received_at == NOW + timedelta(minutes=5)
    assert evidence.host_sections(db, host.id)["umask"] == "027"
    assert evidence.host_sections(db, uuid.uuid4()) is None


def test_an_oversized_report_is_refused(db):
    host = _host(db)
    huge = {"audit_rules": ["x" * 1024] * 600}
    assert evidence.apply_report(db, host, {"sections": huge}) is None
    assert db.query(models.HostComplianceEvidence).count() == 0


def test_the_handler_stores_and_refuses_unknown_hosts(db):
    host = _host(db)
    message = {"data": {"sections": {"umask": "027"}}}
    reply = asyncio.run(
        handle_compliance_evidence_update(db, SimpleNamespace(host_id=host.id), message)
    )
    assert reply == {"message_type": "success", "data": {"stored": True}}
    assert evidence.host_sections(db, host.id)["umask"] == "027"
    stranger = asyncio.run(
        handle_compliance_evidence_update(
            db, SimpleNamespace(host_id=uuid.uuid4()), message
        )
    )
    assert stranger["error_type"] == "host_not_registered"
    no_host = asyncio.run(
        handle_compliance_evidence_update(db, SimpleNamespace(), message)
    )
    assert no_host["message_type"] == "error"


def test_the_router_dispatches_the_new_message_type():
    from backend.websocket import (
        message_router,
    )  # pylint: disable=import-outside-toplevel

    assert MessageType.COMPLIANCE_EVIDENCE_UPDATE == "compliance_evidence_update"
    source = Path(message_router.__file__).read_text(encoding="utf-8")
    assert "MessageType.COMPLIANCE_EVIDENCE_UPDATE" in source


# -- which hosts are due -------------------------------------------------------------


def test_due_hosts_never_scanned_first_then_stale_or_fresh_evidence(db):
    never = _host(db, "never")
    fresh = _host(db, "fresh-scan")
    _scan(db, fresh, NOW - timedelta(hours=1))
    stale = _host(db, "stale")
    _scan(db, stale, NOW - timedelta(hours=30))
    changed = _host(db, "new-evidence")
    _scan(db, changed, NOW - timedelta(hours=2))
    evidence.apply_report(db, changed, {"sections": {"umask": "027"}}, now=NOW)
    pending = _host(db, "pending", approved=False)
    inactive = _host(db, "inactive", active=False)
    db.commit()

    due = tick.due_hosts(db, NOW)
    assert due == [never.id, stale.id, changed.id]
    assert fresh.id not in due and pending.id not in due and inactive.id not in due
    assert tick.due_hosts(db, NOW, limit=1) == [never.id]


def test_history_is_pruned_but_each_hosts_latest_scan_is_kept(db):
    host = _host(db)
    old = NOW - timedelta(days=tick.SCAN_RETENTION_DAYS + 10)
    _scan(db, host, old - timedelta(days=1))
    _scan(db, host, old)
    lonely = _host(db, "lonely")
    _scan(db, lonely, old)  # its only scan: kept however old
    _scan(db, host, NOW - timedelta(days=1))
    assert tick.prune_history(db, NOW) == 2
    db.commit()
    assert db.query(models.HostComplianceScan).count() == 2


# -- the tick ---------------------------------------------------------------------------


class FakeEngine:
    def __init__(self, fail_for=()):
        self.scanned = []
        self.fail_for = {str(h) for h in fail_for}

    def scan_host_compliance(self, host_id, db, models_module):
        assert models_module is models
        if host_id in self.fail_for:
            raise RuntimeError("engine broke")
        self.scanned.append(host_id)
        host = db.get(models.Host, uuid.UUID(host_id))
        _scan(db, host, NOW)
        return {}


def _databases(*sessions):
    return lambda: iter([(f"db{i}", None, s) for i, s in enumerate(sessions)])


def test_no_engine_no_scans():
    with patch.object(tick, "engine", return_value=None):
        assert tick.run_one_tick(NOW) == {"scanned": 0, "failed": 0, "engine": False}
        assert tick.start_if_licensed() is None


def test_an_older_engine_scans_through_its_service():
    service = SimpleNamespace(scan_host=lambda *a: {})
    old = SimpleNamespace(_compliance_service=service)
    assert tick._scanner(old) is service.scan_host  # pylint: disable=protected-access
    assert tick._scanner(SimpleNamespace()) is None  # pylint: disable=protected-access


def test_the_tick_scans_due_hosts_in_every_database_and_survives_a_failure(db):
    first = _host(db, "a")
    broken = _host(db, "b")
    engine = FakeEngine(fail_for=[broken.id])
    closed = []
    db.close = lambda: closed.append(True)  # the tick closes what it is given
    with patch.object(tick, "engine", return_value=engine), patch.object(
        tick, "iter_host_databases", _databases(db)
    ):
        totals = tick.run_one_tick(NOW)
    assert totals["scanned"] == 1 and totals["failed"] == 1
    assert engine.scanned == [str(first.id)]
    assert closed == [True]
    # Scanned now: not due again until its evidence changes or a day passes.
    assert first.id not in tick.due_hosts(db, NOW)


def test_the_tick_is_a_leader_only_singleton():
    async def scenario():
        sentinel = asyncio.get_running_loop().create_future()
        sentinel.set_result(None)
        with patch.object(tick, "engine", return_value=FakeEngine()), patch.object(
            tick, "singleton_task", return_value=sentinel
        ) as singleton, patch.object(
            tick, "compliance_scan_tick_service", lambda: None
        ):
            tick._TASK = None  # pylint: disable=protected-access
            assert tick.start_if_licensed() is sentinel
            singleton.assert_called_once()
        tick._TASK = None  # pylint: disable=protected-access

    asyncio.run(scenario())


# -- migration -------------------------------------------------------------------------------


def _alembic(args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = None
    for _attempt in range(4):  # a negative rc is a signal-kill flake
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_REPO_ROOT, env=env, capture_output=True, text=True, check=False,
        )  # fmt: skip
        if result.returncode >= 0:
            break
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()


def test_the_migration_is_idempotent_and_reversible():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "host_compliance_evidence" in _tables(db_path)
        _alembic(["stamp", "q45discnames"], db_path)
        _alembic(["upgrade", "head"], db_path)  # re-run over the table: no-op
        _alembic(["downgrade", "q45discnames"], db_path)
        assert "host_compliance_evidence" not in _tables(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert "host_compliance_evidence" in _tables(db_path)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(db_path)
