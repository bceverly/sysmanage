# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q70backupreach: the backup_reach table is created idempotently and removed
by a downgrade (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _has_table(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='backup_reach'"
        ).fetchall()
    finally:
        conn.close()
    return bool(rows)


def test_backup_reach_is_created_idempotently_and_reversibly():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _has_table(db_path)
        _alembic(["stamp", "q69backupverify"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: no error
        assert _has_table(db_path)
        _alembic(["downgrade", "q69backupverify"], db_path)
        assert not _has_table(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _has_table(db_path)
    finally:
        os.unlink(db_path)


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(backup_reach)")}
    finally:
        conn.close()


NAT_COLUMNS = {"local_port", "peers_command_id", "seen_as", "nat_checked_at"}


def test_the_nat_columns_are_added_idempotently_and_reversibly():
    """q81reachnat (25.8): hosts behind NAT, said plainly."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert NAT_COLUMNS <= _columns(db_path)
        _alembic(["stamp", "q80hostcertmtls"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: no error
        _alembic(["downgrade", "q80hostcertmtls"], db_path)
        assert not NAT_COLUMNS & _columns(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert NAT_COLUMNS <= _columns(db_path)
    finally:
        os.unlink(db_path)


def _policy_columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(backup_policy)")}
    finally:
        conn.close()


def test_the_server_preset_column_is_added_idempotently_and_reversibly():
    """q82serverbackup (25.9): the SysManage server backs itself up."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "server_preset" in _policy_columns(db_path)
        _alembic(["stamp", "q81reachnat"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: no error
        _alembic(["downgrade", "q81reachnat"], db_path)
        assert "server_preset" not in _policy_columns(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert "server_preset" in _policy_columns(db_path)
    finally:
        os.unlink(db_path)
