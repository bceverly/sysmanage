# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q51backupdu: every backup policy's config_version is bumped, so the
scheduler re-sends job files with the storage-side du (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def test_the_migration_bumps_every_policy_and_survives_a_down_and_up():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "q50backuprules"], db_path)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO backup_target (id, name, host_mount_point, max_concurrent,"
                " seal_mode, created_at, updated_at) VALUES ('t1', 'nas', '/mnt/b', 2,"
                " 'none', '2026-10-20', '2026-10-20')"
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
                " 3, 3, 3, '2026-10-20', '2026-10-20')"
            )
            conn.commit()
        finally:
            conn.close()
        _alembic(["upgrade", "head"], db_path)
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT config_version, storage_acked_version FROM backup_policy"
            ).fetchone()
        finally:
            conn.close()
        # behind (q51, and q56 again): the storage host gets new job files
        assert row[0] > row[1] == 3
        _alembic(["downgrade", "q50backuprules"], db_path)
        _alembic(["upgrade", "head"], db_path)
    finally:
        os.unlink(db_path)
