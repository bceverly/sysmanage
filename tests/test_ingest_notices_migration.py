# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q111ingestnotes: an air-gap ingest's notices column, reversible (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_cve_shared_partition_migration import _alembic


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(airgap_ingestion_run)")}
    finally:
        conn.close()


def test_the_notices_column_comes_and_goes():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "notices" in _columns(db_path)
        _alembic(["downgrade", "q110srcpkg"], db_path)
        assert "notices" not in _columns(db_path)
        _alembic(["upgrade", "head"], db_path)
    finally:
        os.unlink(db_path)
