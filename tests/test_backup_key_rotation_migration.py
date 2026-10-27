# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q66backupkeyrotate: the key history table and rotation columns are added
idempotently and removed by a downgrade, and a policy encrypted before it
gets its one key as the first row (SQLite)."""

import os
import sqlite3
import tempfile
import uuid

from tests.test_backup_rules_migration import _alembic


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _present(db_path):
    return (
        "encrypt_rotated_at" in _columns(db_path, "backup_policy")
        and "key_rotation_days" in _columns(db_path, "backup_target")
        and {"policy_id", "fingerprint", "key_ref", "replaced_at", "retired_at"}
        <= _columns(db_path, "backup_policy_key")
    )


def _absent(db_path):
    return (
        "encrypt_rotated_at" not in _columns(db_path, "backup_policy")
        and "key_rotation_days" not in _columns(db_path, "backup_target")
        and not _columns(db_path, "backup_policy_key")
    )


def _insert_encrypted_policy(db_path):
    """A minimal backup_policy row with a key: every NOT NULL column filled."""
    conn = sqlite3.connect(db_path)
    try:
        values = {}
        for _cid, name, kind, notnull, _default, _pk in conn.execute(
            "PRAGMA table_info(backup_policy)"
        ):
            if notnull:
                kind = (kind or "").upper()
                values[name] = (
                    1
                    if "INT" in kind or "BOOL" in kind
                    else (
                        "2026-10-01 00:00:00"
                        if "DATE" in kind or "TIME" in kind
                        else "x"
                    )
                )
        policy_id = uuid.uuid4().hex
        values.update(id=policy_id, encrypt_fingerprint="A" * 40,
                      encrypt_key_ref="secret/data/secrets/backup_key/server/1",
                      encrypted_at="2026-10-25 12:00:00")  # fmt: skip
        names = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        conn.execute(f"INSERT INTO backup_policy ({names}) VALUES ({marks})",
                     list(values.values()))  # fmt: skip
        conn.commit()
    finally:
        conn.close()


def _key_rows(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT fingerprint, key_ref, created_at FROM backup_policy_key"
        ).fetchall()
    finally:
        conn.close()


def test_key_rotation_schema_is_added_idempotently_and_reversibly():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
        _alembic(["stamp", "q65backupequip"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: no error
        assert _present(db_path)
        _alembic(["downgrade", "q65backupequip"], db_path)
        assert _absent(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _present(db_path)
    finally:
        os.unlink(db_path)


def test_a_policy_encrypted_before_rotation_keeps_its_key_as_the_first_row():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "q65backupequip"], db_path)
        _insert_encrypted_policy(db_path)
        _alembic(["upgrade", "head"], db_path)
        rows = _key_rows(db_path)
        assert len(rows) == 1 and rows[0][0] == "A" * 40
        assert rows[0][1].endswith("/backup_key/server/1")
        _alembic(["stamp", "q65backupequip"], db_path)
        _alembic(["upgrade", "head"], db_path)  # not backfilled twice
        assert len(_key_rows(db_path)) == 1
    finally:
        os.unlink(db_path)
