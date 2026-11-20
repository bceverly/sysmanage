# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""q103fedbackuptargets: a site's targets in its backup status at the
controller, and who manages a backup tag policy -- added idempotently and
removed by the downgrade (SQLite)."""

import os
import tempfile

from tests.test_backup_proxy_migration import _columns
from tests.test_backup_rules_migration import _alembic


def test_the_columns_come_and_go_idempotently():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        _alembic(["upgrade", "head"], db_path)
        assert "targets_json" in _columns(db_path, "federation_backup_rollup")
        assert "managed_by" in _columns(db_path, "backup_tag_policy")
        _alembic(["stamp", "q102multitarget"], db_path)
        _alembic(["upgrade", "head"], db_path)  # already there: nothing to do
        _alembic(["downgrade", "q102multitarget"], db_path)
        assert "targets_json" not in _columns(db_path, "federation_backup_rollup")
        assert "managed_by" not in _columns(db_path, "backup_tag_policy")
        _alembic(["upgrade", "head"], db_path)
        assert "managed_by" in _columns(db_path, "backup_tag_policy")
    finally:
        os.unlink(db_path)
