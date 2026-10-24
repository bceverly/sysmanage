# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q61backupcachefix: a database that applied an early q60sealkeep (without
cache_budget_gb and host_abilities) gets both columns (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _drop(db_path, table, column):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()
    finally:
        conn.close()


def test_an_early_q60_database_gets_the_missing_columns():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        # What the lab database looked like after the early q60sealkeep.
        _drop(db_path, "backup_target", "cache_budget_gb")
        _drop(db_path, "backup_policy", "host_abilities")
        _alembic(["stamp", "q60sealkeep"], db_path)
        _alembic(["upgrade", "head"], db_path)
        assert "cache_budget_gb" in _columns(db_path, "backup_target")
        assert "host_abilities" in _columns(db_path, "backup_policy")
        # Already there: a second run changes nothing.
        _alembic(["stamp", "q60sealkeep"], db_path)
        _alembic(["upgrade", "head"], db_path)
        assert "cache_budget_gb" in _columns(db_path, "backup_target")
    finally:
        os.unlink(db_path)
