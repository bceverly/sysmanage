# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_policy: re-send job files for the storage-side du (ROADMAP 24.5, 2026-10-20)

Tenant data, no schema change.  The storage host now also runs ``restate du``
after each prune (the repository's size and what each snapshot alone would
free), so every storage host needs a new job file.  Bumping each policy's
``config_version`` makes the backup scheduler re-send both sides' job files
on its next pass.

Idempotent in effect: a second run only bumps again, which re-sends the same
job files once more.  Safe on SQLite + PostgreSQL.

Revision ID: q51backupdu
Revises: q50backuprules
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q51backupdu"
down_revision: Union[str, None] = "q50backuprules"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_policy"


def upgrade() -> None:
    if _TABLE not in set(inspect(op.get_bind()).get_table_names()):
        return
    op.execute(sa.text(f"UPDATE {_TABLE} SET config_version = config_version + 1"))


def downgrade() -> None:
    # Nothing to undo: the job files a lower version would send are a subset.
    pass
