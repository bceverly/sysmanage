# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q112requestkind: four-eyes requests gain ``kind`` and ``target``,
reversible; a request from before is a restore (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_cve_shared_partition_migration import _alembic


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(backup_restore_request)")}
    finally:
        conn.close()


def test_kind_and_target_come_and_go_and_old_requests_are_restores():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "q111ingestnotes"], db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO backup_restore_request (id, host_id, body, status,"
            " requested_by, requested_at) VALUES ('r1', 'h1', '{}', 'pending',"
            " 'a@example.com', '2026-11-24 00:00:00')"
        )
        conn.commit()
        conn.close()
        _alembic(["upgrade", "head"], db_path)
        assert {"kind", "target"} <= _columns(db_path)
        conn = sqlite3.connect(db_path)
        assert conn.execute("SELECT kind FROM backup_restore_request").fetchone() == (
            "restore",
        )
        conn.close()
        _alembic(["downgrade", "q111ingestnotes"], db_path)
        assert not {"kind", "target"} & _columns(db_path)
        _alembic(["upgrade", "head"], db_path)
    finally:
        os.unlink(db_path)


def test_the_host_reenroll_columns_come_and_go():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cols = {"reenroll_code_hash", "reenroll_code_expires_at", "reenroll_code_by"}

    def host_columns():
        conn = sqlite3.connect(db_path)
        try:
            return {r[1] for r in conn.execute("PRAGMA table_info(host)")}
        finally:
            conn.close()

    try:
        _alembic(["upgrade", "head"], db_path)
        assert cols <= host_columns()
        _alembic(["downgrade", "q112requestkind"], db_path)
        assert not cols & host_columns()
        _alembic(["upgrade", "head"], db_path)
    finally:
        os.unlink(db_path)
