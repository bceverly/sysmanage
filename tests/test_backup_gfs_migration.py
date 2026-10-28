# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q67backupgfs: the grandfather-father-son columns are added idempotently
and removed by a downgrade (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic

_GFS = {"keep_daily", "keep_weekly", "keep_monthly"}


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(backup_policy)")}
    finally:
        conn.close()


def test_gfs_columns_are_added_idempotently_and_reversibly():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _GFS <= _columns(db_path)
        _alembic(["stamp", "q66backupkeyrotate"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: no error
        assert _GFS <= _columns(db_path)
        _alembic(["downgrade", "q66backupkeyrotate"], db_path)
        assert not _GFS & _columns(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _GFS <= _columns(db_path)
    finally:
        os.unlink(db_path)
