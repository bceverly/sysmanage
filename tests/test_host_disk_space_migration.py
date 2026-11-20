# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q104diskspace: a host's fullest filesystem -- added idempotently and
removed by the downgrade (SQLite)."""

import os
import tempfile

from tests.test_backup_proxy_migration import _columns
from tests.test_backup_rules_migration import _alembic

_NEW = ("disk_used_percent", "disk_fullest_mount", "disk_available_bytes",
        "disk_checked_at")  # fmt: skip


def test_the_columns_come_and_go_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert set(_NEW) <= set(_columns(db_path, "host"))
        _alembic(["stamp", "q103fedbackuptargets"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: nothing to do
        _alembic(["downgrade", "q103fedbackuptargets"], db_path)
        assert not set(_NEW) & set(_columns(db_path, "host"))
        _alembic(["upgrade", "head"], db_path)
        assert set(_NEW) <= set(_columns(db_path, "host"))
    finally:
        os.unlink(db_path)
