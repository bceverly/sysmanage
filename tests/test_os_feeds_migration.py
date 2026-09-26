# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""s16osfeeds: existing installs get the per-OS CVE feeds.

A settings row lists the sources enabled when it was created, so a feed added
later would never run and every host it covers would stay "not assessable".
Runs the real shared chain on a scratch SQLite database.
"""

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _alembic(args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = None
    for _attempt in range(4):  # a negative rc is a signal-kill flake, not a failure
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "--name", "shared", *args],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode >= 0:
            break
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"


def _sources(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, enabled_sources FROM shared_cve_refresh_settings ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: json.loads(row[1]) if row[1] else None for row in rows}


def test_existing_settings_gain_the_bsd_feeds_and_keep_their_choices():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    try:
        _alembic(["upgrade", "s15advisordefault"], db)
        conn = sqlite3.connect(db)
        try:
            for row_id, sources in (
                ("a", ["nvd", "ubuntu", "debian", "redhat"]),
                ("b", ["nvd", "freebsd"]),
                ("c", []),
            ):
                conn.execute(
                    "INSERT INTO shared_cve_refresh_settings "
                    "(id, enabled, refresh_interval_hours, enabled_sources, "
                    "created_at, updated_at) VALUES (?, 1, 24, ?, "
                    "'2026-01-01', '2026-01-01')",
                    (row_id, json.dumps(sources)),
                )
            conn.commit()
        finally:
            conn.close()

        _alembic(["upgrade", "head"], db)
        assert _sources(db) == {
            "a": [
                "nvd",
                "ubuntu",
                "debian",
                "redhat",
                "microsoft",
                "freebsd",
                "netbsd",
                "macos",
            ],
            "b": ["nvd", "freebsd", "microsoft", "netbsd", "macos"],
            "c": ["microsoft", "freebsd", "netbsd", "macos"],
        }

        # Idempotent: running it again adds nothing.
        _alembic(["stamp", "s15advisordefault"], db)
        _alembic(["upgrade", "head"], db)
        assert _sources(db)["a"].count("freebsd") == 1
    finally:
        with contextlib.suppress(OSError):
            os.unlink(db)
