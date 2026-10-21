# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q53backuprundismiss: backup_run gains dismissed_at; a re-run is a no-op
and a downgrade removes it (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _has_column(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(backup_run)").fetchall()
    finally:
        conn.close()
    return "dismissed_at" in {row[1] for row in rows}


def test_dismissed_at_is_added_idempotently_and_reversibly():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _has_column(db_path)
        _alembic(["stamp", "q52pkgrevision"], db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _has_column(db_path)
        _alembic(["downgrade", "q52pkgrevision"], db_path)
        assert not _has_column(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _has_column(db_path)
    finally:
        os.unlink(db_path)
