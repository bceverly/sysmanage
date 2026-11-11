# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q85proxycert: the proxy's certificate on the target -- added
idempotently, removed by the downgrade (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(backup_target)")}
    finally:
        conn.close()


def test_the_column_comes_and_goes_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "proxy_cert_pem" in _columns(db_path)
        _alembic(["stamp", "q84backupproxy"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: nothing to do
        _alembic(["downgrade", "q84backupproxy"], db_path)
        assert "proxy_cert_pem" not in _columns(db_path)
        _alembic(["upgrade", "head"], db_path)
        assert "proxy_cert_pem" in _columns(db_path)
    finally:
        os.unlink(db_path)
