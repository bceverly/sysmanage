# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q52pkgrevision: software_package.revision widens to 255 so an image
digest fits, and a re-run is a no-op (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _declared(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(software_package)").fetchall()
    finally:
        conn.close()
    return {row[1]: row[2] for row in rows}["revision"].upper()


def test_revision_widens_and_holds_an_image_digest():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "q51backupdu"], db_path)
        assert _declared(db_path) == "VARCHAR(50)"
        _alembic(["upgrade", "head"], db_path)
        assert _declared(db_path) == "VARCHAR(255)"
        _alembic(["stamp", "q51backupdu"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already wide: a no-op
        assert _declared(db_path) == "VARCHAR(255)"
    finally:
        os.unlink(db_path)
