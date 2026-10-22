# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q56backupaddr: storage_client_address is added and every policy's
config_version bumped, so storage hosts are re-sent the host's address and
the service account; a re-run is harmless and a downgrade removes the column
(SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _state(db_path):
    conn = sqlite3.connect(db_path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(backup_policy)")}
        row = conn.execute("SELECT config_version FROM backup_policy").fetchone()
    finally:
        conn.close()
    return "storage_client_address" in columns, row[0] if row else None


def test_the_address_column_is_added_and_job_files_re_sent():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "q55backupaudit"], db_path)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO backup_target (id, name, host_mount_point, max_concurrent,"
                " seal_mode, created_at, updated_at) VALUES ('t1', 'nas', '/mnt/b', 2,"
                " 'none', '2026-10-22', '2026-10-22')"
            )
            conn.execute(
                "INSERT INTO host (id, fqdn, active, approval_status) VALUES"
                " ('h1', 'h.lab', 1, 'approved')"
            )
            conn.execute(
                "INSERT INTO backup_policy (id, host_id, target_id, enabled,"
                " interval_hours, keep_last, check_interval_days, quiesce,"
                " config_version, host_acked_version, storage_acked_version,"
                " created_at, updated_at) VALUES ('p1', 'h1', 't1', 1, 24, 14, 7, 0,"
                " 7, 7, 7, '2026-10-22', '2026-10-22')"
            )
            conn.commit()
        finally:
            conn.close()
        _alembic(["upgrade", "q56backupaddr"], db_path)
        assert _state(db_path) == (True, 8)
        _alembic(["stamp", "q55backupaudit"], db_path)
        _alembic(["upgrade", "head"], db_path)  # column already there
        assert _state(db_path)[0]
        _alembic(["downgrade", "q55backupaudit"], db_path)
        assert not _state(db_path)[0]
        _alembic(["upgrade", "head"], db_path)
        assert _state(db_path)[0]
    finally:
        os.unlink(db_path)
