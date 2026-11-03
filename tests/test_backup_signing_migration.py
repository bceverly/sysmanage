# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q73backupsigning: the signer columns on backup_target and signer on
backup_snapshot are added idempotently and removed by a downgrade (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic

TARGET = {"sign_public_key", "sign_fingerprint", "sign_key_ref", "signing_enabled_at"}


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        conn.close()
    return {row[1] for row in rows}


def _present(db_path):
    return TARGET <= _columns(db_path, "backup_target") and "signer" in _columns(
        db_path, "backup_snapshot"
    )


def test_the_signing_columns_are_added_idempotently_and_reversibly():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
        _alembic(["stamp", "q72scriptapproval"], db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
        _alembic(["downgrade", "q72scriptapproval"], db_path)
        assert not TARGET & _columns(db_path, "backup_target")
        assert "signer" not in _columns(db_path, "backup_snapshot")
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
    finally:
        os.unlink(db_path)
