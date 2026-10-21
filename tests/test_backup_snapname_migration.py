# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q54backupsnapname: repository-qualified snapshot names become bare names;
a duplicate of an existing bare row is removed; a re-run changes nothing."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic

_STAMP = "'2026-10-21'"


def _seed(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO host (id, fqdn, active, approval_status) VALUES ('h1','h',1,'approved')"
        )
        conn.execute(
            "INSERT INTO backup_target (id, name, host_mount_point, max_concurrent, seal_mode,"
            f" created_at, updated_at) VALUES ('t1','nas','/mnt/b',2,'none',{_STAMP},{_STAMP})"
        )
        conn.execute(
            "INSERT INTO backup_policy (id, host_id, target_id, enabled, interval_hours, keep_last,"
            " check_interval_days, quiesce, config_version, host_acked_version,"
            f" storage_acked_version, created_at, updated_at) VALUES ('p1','h1','t1',1,24,14,7,0,"
            f"1,1,1,{_STAMP},{_STAMP})"
        )
        for sid, name in (("s1", "/mnt/b/h::A"), ("s2", "/mnt/b/h::B"), ("s3", "B")):
            conn.execute(
                "INSERT INTO backup_snapshot (id, policy_id, host_id, name, signed, seen_at)"
                f" VALUES (?, 'p1', 'h1', ?, 0, {_STAMP})",
                (sid, name),
            )
        conn.execute(
            "INSERT INTO backup_run (id, policy_id, host_id, action, status, queued_at, snapshot)"
            f" VALUES ('r1','p1','h1','capture','ok',{_STAMP},'/mnt/b/h::A')"
        )
        conn.commit()
    finally:
        conn.close()


def _state(db_path):
    conn = sqlite3.connect(db_path)
    try:
        snaps = sorted(r[0] for r in conn.execute("SELECT name FROM backup_snapshot"))
        run = conn.execute("SELECT snapshot FROM backup_run").fetchone()[0]
    finally:
        conn.close()
    return snaps, run


def test_snapshot_names_become_bare_and_duplicates_go():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "q53backuprundismiss"], db_path)
        _seed(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _state(db_path) == (["A", "B"], "A")
        _alembic(["stamp", "q53backuprundismiss"], db_path)
        _alembic(["upgrade", "head"], db_path)
        assert _state(db_path) == (["A", "B"], "A")
    finally:
        os.unlink(db_path)
