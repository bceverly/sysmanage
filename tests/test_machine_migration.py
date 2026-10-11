# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Migrations q33machine and q34assettag (Phase 23.2 S2/S3): the machine table,
the host identity columns, the asset-tag scheme and its role -- idempotent,
downgradable, and the ORM agrees with what they built."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.services import machine_identity

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOST_COLUMNS = {
    "machine_id",
    "hw_match_key",
    "hw_system_uuid",
    "hw_system_serial",
    "hw_board_serial",
    "hw_identity_status",
    "hw_identity_updated_at",
    "machine_conflict_id",
    "machine_conflict_reason",
}


def _alembic(args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = None
    for _attempt in range(4):  # a negative rc is a signal-kill flake
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode >= 0:
            break
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _role_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM security_roles WHERE name = 'Manage Asset Tags'"
        ).fetchone()[0]
    finally:
        conn.close()


def test_the_migration_builds_the_schema_reruns_cleanly_and_the_orm_agrees():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "head"], db)
        assert {"match_key", "asset_tag", "is_virtual"} <= _columns(db, "machine")
        assert _HOST_COLUMNS <= _columns(db, "host")
        assert {"mode", "prefix", "digits", "pattern", "enforce"} <= _columns(
            db, "asset_tag_scheme"
        )
        assert _role_count(db) == 1

        # Idempotent: run q33machine again over the schema it already built.
        _alembic(["stamp", "q32ssostate"], db)
        _alembic(["upgrade", "head"], db)
        assert _role_count(db) == 1  # seeded once, not again on a re-run

        engine = create_engine(f"sqlite:///{db}")
        with sessionmaker(bind=engine)() as session:
            host = models.Host(
                id=uuid.uuid4(),
                fqdn="ubuntu.t480",
                active=True,
                approval_status="approved",
            )
            session.add(host)
            session.flush()
            machine_identity.record_identity(
                session,
                host,
                {
                    "system_uuid": "1a2b3c4d-5e6f-11b2-a85c-0f1e2d3c4b5a",
                    "system_serial": "PF9ZQ7X1",
                    "match_key": "1a2b3c4d-5e6f-11b2-a85c-0f1e2d3c4b5a",
                    "status": {"system_uuid": "ran"},
                },
            )
            session.commit()
            machine = session.get(models.Machine, host.machine_id)
            assert machine.system_serial == "PF9ZQ7X1"
            assert machine.created_at <= datetime.utcnow()
        engine.dispose()

        _alembic(["downgrade", "q32ssostate"], db)
        assert not _HOST_COLUMNS & _columns(db, "host")
        assert _role_count(db) == 0
    finally:
        if os.path.exists(db):
            os.unlink(db)
