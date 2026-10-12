# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Migrations q33machine, q34assettag and q35heldtag (Phase 23.2 S2/S3/S5): the
machine table, the host identity columns, the asset-tag scheme and its role,
and held tags -- idempotent, downgradable, and the ORM agrees with what they
built."""

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
        assert {"kind", "identifier", "asset_tag", "created_at"} <= _columns(
            db, "held_asset_tag"
        )

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
        assert not _columns(db, "held_asset_tag")
    finally:
        if os.path.exists(db):
            os.unlink(db)


def _grants(db_path, role):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM user_security_roles usr JOIN security_roles sr "
            "ON sr.id = usr.role_id WHERE sr.name = ?",
            (role,),
        ).fetchone()[0]
    finally:
        conn.close()


def test_q36_grants_the_new_role_to_existing_tag_editors_once():
    """On an upgraded server nobody held Manage Asset Tags; tag editors now do."""
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "q35heldtag"], db)
        engine = create_engine(f"sqlite:///{db}")
        with sessionmaker(bind=engine)() as session:
            editor = models.User(
                id=uuid.uuid4(), userid="editor@example.com", active=True
            )
            bystander = models.User(
                id=uuid.uuid4(), userid="viewer@example.com", active=True
            )
            session.add_all([editor, bystander])
            session.flush()
            edit_tags = (
                session.query(models.SecurityRole)
                .filter(models.SecurityRole.name == "Edit Tags")
                .one()
            )
            session.add(
                models.UserSecurityRole(
                    id=uuid.uuid4(),
                    user_id=editor.id,
                    role_id=edit_tags.id,
                    granted_at=datetime.utcnow(),
                )
            )
            session.commit()
        engine.dispose()
        assert _grants(db, "Manage Asset Tags") == 0

        _alembic(["upgrade", "head"], db)
        assert _grants(db, "Manage Asset Tags") == 1
        _alembic(["stamp", "q35heldtag"], db)
        _alembic(["upgrade", "head"], db)
        assert _grants(db, "Manage Asset Tags") == 1  # never granted twice
    finally:
        if os.path.exists(db):
            os.unlink(db)


_CLOCK_COLUMNS = {
    "clock_offset_ms",
    "clock_rtt_ms",
    "clock_samples",
    "clock_method",
    "clock_measured_at",
    "time_service",
    "time_service_running",
    "time_synchronized",
    "time_source",
    "time_stratum",
    "time_reported_offset_ms",
    "time_status_at",
}


def test_q37_adds_the_clock_columns_and_history_idempotently():
    """Phase 23.3 S2: host clock columns + host_clock_sample, re-runnable."""
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "head"], db)
        assert _CLOCK_COLUMNS <= _columns(db, "host")
        assert {"host_id", "measured_at", "offset_ms", "rtt_ms", "method"} <= (
            _columns(db, "host_clock_sample")
        )
        _alembic(["stamp", "q36assettagrole"], db)
        _alembic(["upgrade", "head"], db)  # over the schema it already built
        _alembic(["downgrade", "q36assettagrole"], db)
        assert not _CLOCK_COLUMNS & _columns(db, "host")
        assert not _columns(db, "host_clock_sample")
    finally:
        if os.path.exists(db):
            os.unlink(db)


def test_q38_adds_bounds_and_gives_the_role_to_every_admin_once():
    """Phase 23.3 S3: the role is granted in the same migration (q36 lesson)."""
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "q37clocksync"], db)
        engine = create_engine(f"sqlite:///{db}")
        with sessionmaker(bind=engine)() as session:
            session.add_all(
                [
                    models.User(
                        id=uuid.uuid4(),
                        userid="admin@example.com",
                        active=True,
                        is_admin=True,
                    ),
                    models.User(
                        id=uuid.uuid4(),
                        userid="viewer@example.com",
                        active=True,
                        is_admin=False,
                    ),
                ]
            )
            session.commit()
        engine.dispose()

        _alembic(["upgrade", "head"], db)
        assert {"scope_kind", "scope_ref", "warning_ms", "critical_ms"} <= _columns(
            db, "clock_bound"
        )
        assert _grants(db, "Manage Time Sync") == 1
        _alembic(["stamp", "q37clocksync"], db)
        _alembic(["upgrade", "head"], db)
        assert _grants(db, "Manage Time Sync") == 1  # never granted twice
        _alembic(["downgrade", "q37clocksync"], db)
        assert not _columns(db, "clock_bound")
        assert _grants(db, "Manage Time Sync") == 0
    finally:
        if os.path.exists(db):
            os.unlink(db)
