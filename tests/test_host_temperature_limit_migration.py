# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q47hwtemplimit: host.hardware_temp_warning_c is added, re-added as a no-op,
and dropped again on downgrade (SQLite; the PostgreSQL path is the same
add_column)."""

import contextlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COLUMN = "hardware_temp_warning_c"


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


def _host_columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(host)")}
    finally:
        conn.close()


def test_the_migration_is_idempotent_and_reversible():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _COLUMN in _host_columns(db_path)
        _alembic(["stamp", "q46compevid"], db_path)
        _alembic(["upgrade", "head"], db_path)  # the column exists: a no-op
        _alembic(["downgrade", "q46compevid"], db_path)
        assert _COLUMN not in _host_columns(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _COLUMN in _host_columns(db_path)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(db_path)
