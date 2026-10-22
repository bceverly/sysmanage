# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q58vmmopenbsd80: OpenBSD 7.9 and 8.0 are offered for VMM child hosts and
the unsupported releases are withdrawn (kept, inactive); idempotent and
reversible (SQLite)."""

import json
import os
import sqlite3
import tempfile

from tests.test_backup_rules_migration import _alembic


def _openbsd(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT distribution_version, is_active, install_identifier,"
            " agent_install_commands FROM child_host_distribution"
            " WHERE child_type = 'vmm' AND distribution_name = 'OpenBSD'"
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: r[1:] for r in rows}


def test_only_the_supported_releases_are_offered_and_it_reverses():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        rows = _openbsd(db_path)
        assert {v for v, r in rows.items() if r[0]} == {"7.9", "8.0"}
        assert {"7.4", "7.7"} <= set(rows)  # kept, inactive
        assert rows["8.0"][1].endswith("/OpenBSD/8.0/amd64/install80.iso")
        cmds = json.loads(rows["7.9"][2])
        assert any("openbsd79.tgz" in c for c in cmds)
        _alembic(["stamp", "q57backupnfspath"], db_path)
        _alembic(["upgrade", "head"], db_path)  # re-run: no duplicates
        assert len(_openbsd(db_path)) == len(rows)
        _alembic(["downgrade", "q57backupnfspath"], db_path)
        back = _openbsd(db_path)
        assert back["7.7"][0] and not back["8.0"][0]
        _alembic(["upgrade", "head"], db_path)
        assert {v for v, r in _openbsd(db_path).items() if r[0]} == {"7.9", "8.0"}
    finally:
        os.unlink(db_path)
