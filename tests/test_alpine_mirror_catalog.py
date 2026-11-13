# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Alpine in the mirror version catalog (s19alpinemirror) and in the server's
mirror dispatch (2026-11-13): the mirroring engine mirrors Alpine now, and
the air-gap collector stages it as ``alpine/<version>``."""

import os
import sqlite3
import tempfile

from tests.test_cve_shared_partition_migration import _alembic


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT version_key, os_family, default_upstream_url FROM shared_mirror_known_version "
            "WHERE platform = 'apk' ORDER BY version_key"
        ).fetchall()
    finally:
        conn.close()


def test_the_alpine_releases_come_and_go_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db_path)
        rows = _rows(db_path)
        assert [r[0] for r in rows] == ["3.21", "3.22", "3.23", "3.24"]
        assert rows[1] == (
            "3.22",
            "alpine",
            "rsync://rsync.alpinelinux.org/alpine/v3.22/main",
        )
        _alembic(["--name", "shared", "stamp", "s18malwarefeed"], db_path)
        _alembic(["--name", "shared", "upgrade", "head"], db_path)  # already there
        assert len(_rows(db_path)) == 4
        _alembic(["--name", "shared", "downgrade", "s18malwarefeed"], db_path)
        assert _rows(db_path) == []
    finally:
        os.unlink(db_path)


def test_the_server_dispatches_alpine_mirrors_to_the_engine():
    import inspect  # noqa: PLC0415  pylint: disable=import-outside-toplevel

    from backend.api import (
        repository_mirroring,
        repository_mirroring_helpers,
    )  # noqa: PLC0415
    from backend.api import repository_mirroring_setup  # noqa: PLC0415

    for module in (repository_mirroring, repository_mirroring_helpers):
        assert '"apk": engine.build_apk_mirror_sync_plan' in inspect.getsource(module)
    assert (
        "apk" in repository_mirroring_setup._VALID_PLATFORMS
    )  # pylint: disable=protected-access
