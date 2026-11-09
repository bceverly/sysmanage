# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q84backupproxy: a target's transport and its hosts' token hashes
(restate-proxy, 25.5) -- added idempotently, removed by the downgrade, and
every target until now on NFS (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic

_TARGET = {"transport", "proxy_host", "proxy_port", "proxy_pin_sha256",
           "proxy_ca_pem", "proxy_clients"}  # fmt: skip
_POLICY = {"proxy_token_sha256", "proxy_token_sha256_old",
           "proxy_previous_token_sha256"}  # fmt: skip


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_the_columns_come_and_go_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert _TARGET <= set(_columns(db_path, "backup_target"))
        assert _POLICY <= set(_columns(db_path, "backup_policy"))
        # transport: NOT NULL, every target until now on NFS.
        transport = _columns(db_path, "backup_target")["transport"]
        assert transport[3] == 1 and "nfs" in str(transport[4])
        _alembic(["stamp", "q83escrowkeyref"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: nothing to do
        _alembic(["downgrade", "q83escrowkeyref"], db_path)
        assert not _TARGET & set(_columns(db_path, "backup_target"))
        assert not _POLICY & set(_columns(db_path, "backup_policy"))
        _alembic(["upgrade", "head"], db_path)
        assert _TARGET <= set(_columns(db_path, "backup_target"))
    finally:
        os.unlink(db_path)
