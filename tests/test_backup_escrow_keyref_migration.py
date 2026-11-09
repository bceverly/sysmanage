# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q83escrowkeyref: an escrow-keyed backup key row has no OpenBAO reference,
so ``backup_policy_key.key_ref`` becomes nullable -- idempotently, and the
downgrade puts NOT NULL back only when no such row exists (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _key_ref_nullable(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(backup_policy_key)").fetchall()
    finally:
        conn.close()
    # PRAGMA table_info: (cid, name, type, notnull, default, pk)
    return next(row[3] == 0 for row in rows if row[1] == "key_ref")


def _insert_escrow_row(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO backup_policy_key (id, policy_id, fingerprint, key_ref, "
            "created_at) VALUES ('k1', 'p1', 'ABCD', NULL, '2026-11-09 02:00:00')"
        )
        conn.commit()
    finally:
        conn.close()


def test_key_ref_becomes_nullable_idempotently_and_reversibly():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _key_ref_nullable(db_path)
        _alembic(["stamp", "q82serverbackup"], db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _key_ref_nullable(db_path)
        _alembic(["downgrade", "q82serverbackup"], db_path)
        assert not _key_ref_nullable(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _key_ref_nullable(db_path)
    finally:
        os.unlink(db_path)


def test_a_downgrade_keeps_escrow_rows_rather_than_failing():
    """The server's escrow-keyed key row (drill, 2026-11-09) has no key_ref."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        _insert_escrow_row(db_path)
        _alembic(["downgrade", "q82serverbackup"], db_path)
        assert _key_ref_nullable(db_path)
    finally:
        os.unlink(db_path)
