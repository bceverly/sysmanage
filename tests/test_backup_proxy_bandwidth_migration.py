# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q86proxybandwidth: a target's bandwidth rules (restate-proxy, Pro+) --
added idempotently, removed by the downgrade, no limit on every target until
now (SQLite)."""

import os
import tempfile

from tests.test_backup_proxy_migration import _columns
from tests.test_backup_rules_migration import _alembic


def test_the_column_comes_and_goes_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        column = _columns(db_path, "backup_target")["proxy_bandwidth"]
        assert column[3] == 0  # nullable: no limit
        _alembic(["stamp", "q85proxycert"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: nothing to do
        _alembic(["downgrade", "q85proxycert"], db_path)
        assert "proxy_bandwidth" not in _columns(db_path, "backup_target")
        _alembic(["upgrade", "head"], db_path)
        assert "proxy_bandwidth" in _columns(db_path, "backup_target")
    finally:
        os.unlink(db_path)
