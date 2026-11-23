# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Advisories for every distribution (2026-11-23): q110srcpkg gives each
installed package the source package it was built from (Debian, Fedora and
Alpine advisories name sources), s20advfrom gives an advisory package the
version a vulnerable range starts at (FreeBSD VuXML).  Both are idempotent
and reversible (SQLite)."""

import os
import sqlite3
import tempfile

from tests.test_cve_shared_partition_migration import _alembic


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_software_package_gains_its_source_package_and_loses_it_on_downgrade():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "source_package" in _columns(db_path, "software_package")
        _alembic(["downgrade", "q109softuserfks"], db_path)
        assert "source_package" not in _columns(db_path, "software_package")
        _alembic(["upgrade", "head"], db_path)
        assert "source_package" in _columns(db_path, "software_package")
    finally:
        os.unlink(db_path)


def test_shared_advisory_package_gains_affected_from():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db_path)
        assert "affected_from" in _columns(db_path, "shared_advisory_package")
        _alembic(["--name", "shared", "stamp", "s19alpinemirror"], db_path)
        _alembic(["--name", "shared", "upgrade", "head"], db_path)  # already there
        _alembic(["--name", "shared", "downgrade", "s19alpinemirror"], db_path)
        assert "affected_from" not in _columns(db_path, "shared_advisory_package")
    finally:
        os.unlink(db_path)
