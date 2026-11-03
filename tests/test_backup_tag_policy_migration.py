# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q75backuptagpolicy: backup_tag_policy and backup_policy.tag_policy_id are
added idempotently and removed by a downgrade (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in rows.fetchall()}
    finally:
        conn.close()


def _policy_columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(backup_policy)")}
    finally:
        conn.close()


def _present(db_path):
    return "backup_tag_policy" in _tables(db_path) and "tag_policy_id" in (
        _policy_columns(db_path)
    )


def test_the_tag_policy_table_and_column_are_added_idempotently_and_reversibly():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
        _alembic(["stamp", "q74backupdrift"], db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
        _alembic(["downgrade", "q74backupdrift"], db_path)
        assert "backup_tag_policy" not in _tables(db_path)
        assert "tag_policy_id" not in _policy_columns(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
    finally:
        os.unlink(db_path)
