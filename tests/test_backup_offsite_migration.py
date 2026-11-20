# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q105offsite: a target's off-site copy and ``backup_replica`` -- added
idempotently, removed by the downgrade (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_proxy_migration import _columns
from tests.test_backup_rules_migration import _alembic


def _tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {name for (name,) in rows}
    finally:
        conn.close()


def test_the_off_site_column_and_table_come_and_go():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "replica_target_id" in _columns(db_path, "backup_target")
        assert "backup_replica" in _tables(db_path)
        assert {"token_sha256", "pruned", "newest_at"} <= set(
            _columns(db_path, "backup_replica")
        )
        _alembic(["stamp", "q104diskspace"], db_path)
        _alembic(["upgrade", "head"], db_path)  # a rerun changes nothing
        _alembic(["downgrade", "q104diskspace"], db_path)
        assert "replica_target_id" not in _columns(db_path, "backup_target")
        assert "backup_replica" not in _tables(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert "backup_replica" in _tables(db_path)
    finally:
        os.unlink(db_path)
