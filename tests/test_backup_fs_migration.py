# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q49backupfs: the btrfs seal and storage filesystem columns are added, a
re-run is a no-op, and a downgrade removes them (SQLite)."""

import contextlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COLUMNS = {
    "btrfs_snapshot_dir",
    "storage_fs_type",
    "storage_fs_mount",
    "storage_fs_checked_at",
    "storage_is_btrfs_subvolume",
}


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


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(backup_target)").fetchall()
    finally:
        conn.close()
    return {row[1] for row in rows} & _COLUMNS


def test_the_migration_is_idempotent_and_reversible():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _columns(db_path) == _COLUMNS
        _alembic(["stamp", "q48backups"], db_path)
        _alembic(["upgrade", "head"], db_path)  # every column exists: a no-op
        assert _columns(db_path) == _COLUMNS
        _alembic(["downgrade", "q48backups"], db_path)
        assert _columns(db_path) == set()
        _alembic(["upgrade", "head"], db_path)
        assert _columns(db_path) == _COLUMNS
    finally:
        with contextlib.suppress(OSError):
            os.unlink(db_path)
