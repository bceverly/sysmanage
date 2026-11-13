# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q87tokennext: the token a host will rotate to (restate-proxy) -- added
idempotently, removed by the downgrade, no rotation under way until now
(SQLite)."""

import os
import tempfile

from tests.test_backup_proxy_migration import _columns
from tests.test_backup_rules_migration import _alembic


def test_the_column_comes_and_goes_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        column = _columns(db_path, "backup_policy")["proxy_token_sha256_next"]
        assert column[3] == 0  # nullable: no rotation under way
        _alembic(["stamp", "q86proxybandwidth"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: nothing to do
        _alembic(["downgrade", "q86proxybandwidth"], db_path)
        assert "proxy_token_sha256_next" not in _columns(db_path, "backup_policy")
        _alembic(["upgrade", "head"], db_path)
        assert "proxy_token_sha256_next" in _columns(db_path, "backup_policy")
    finally:
        os.unlink(db_path)
