# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q102multitarget: the default target, a target's location and a tag
policy's target -- added idempotently, the oldest existing target made the
default, removed by the downgrade (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_proxy_migration import _columns
from tests.test_backup_rules_migration import _alembic


def _targets(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return dict(conn.execute("SELECT name, is_default FROM backup_target"))
    finally:
        conn.close()


def _add_targets(db_path):
    conn = sqlite3.connect(db_path)
    try:
        for name, made in (("newer", "2026-11-02"), ("older", "2026-11-01")):
            conn.execute(
                "INSERT INTO backup_target (id, name, host_mount_point,"
                " max_concurrent, seal_mode, transport, created_at, updated_at)"
                " VALUES (?, ?, '/mnt/b', 2, 'none', 'nfs', ?, ?)",
                (name + "-id", name, made, made),
            )
        conn.commit()
    finally:
        conn.close()


def test_the_oldest_target_becomes_the_default_and_the_columns_come_and_go():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "q101legalhold"], db_path)
        _add_targets(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _targets(db_path) == {"older": 1, "newer": None}
        assert "location" in _columns(db_path, "backup_target")
        assert "target_id" in _columns(db_path, "backup_tag_policy")
        _alembic(["stamp", "q101legalhold"], db_path)
        _alembic(["upgrade", "head"], db_path)  # a rerun keeps the default
        assert _targets(db_path) == {"older": 1, "newer": None}
        _alembic(["downgrade", "q101legalhold"], db_path)
        assert "is_default" not in _columns(db_path, "backup_target")
        assert "target_id" not in _columns(db_path, "backup_tag_policy")
        _alembic(["upgrade", "head"], db_path)
        assert _targets(db_path) == {"older": 1, "newer": None}
    finally:
        os.unlink(db_path)
