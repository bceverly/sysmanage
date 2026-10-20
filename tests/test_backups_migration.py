# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q48backups: the four backup tables and the two roles are created, a re-run
is a no-op, and a downgrade removes both (SQLite; the PostgreSQL path differs
only in the CAST of role ids)."""

import contextlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TABLES = {"backup_target", "backup_policy", "backup_run", "backup_snapshot"}
_ROLES = {"Manage Backups", "Restore Files"}


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


def _state(db_path):
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        roles = set()
        if "security_roles" in tables:
            roles = {r[0] for r in conn.execute("SELECT name FROM security_roles")}
        indexes = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        return tables & _TABLES, roles & _ROLES, indexes
    finally:
        conn.close()


def test_the_migration_is_idempotent_and_reversible():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        tables, roles, indexes = _state(db_path)
        assert tables == _TABLES and roles == _ROLES
        assert "ix_backup_policy_host_id" in indexes
        _alembic(["stamp", "q47hwtemplimit"], db_path)
        _alembic(["upgrade", "head"], db_path)  # everything exists: a no-op
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM security_roles WHERE name = 'Manage Backups'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1
        _alembic(["downgrade", "q47hwtemplimit"], db_path)
        tables, roles, _indexes = _state(db_path)
        assert tables == set() and roles == set()
        _alembic(["upgrade", "head"], db_path)
        assert _state(db_path)[0] == _TABLES
    finally:
        with contextlib.suppress(OSError):
            os.unlink(db_path)
