# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_policy: the address the storage side was last given (2026-10-22)

Tenant data.  ``backup_policy.storage_client_address`` is the backed-up
host's address as last sent to the storage host (whom the repository's
export may serve, and what its audit checks the export against).  When the
host's address changes, the scheduler re-sends the storage side's job files,
and a repository that was prepared is prepared again for the new address.

Also bumps every policy's ``config_version``: q55 taught the storage side
to audit against the host's address and the service account, but job files
already acknowledged were never re-sent, so storage hosts still had neither.

Additive. Idempotent in effect (a second run only re-sends once more); safe
on SQLite + PostgreSQL.

Revision ID: q56backupaddr
Revises: q55backupaudit
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q56backupaddr"
down_revision: Union[str, None] = "q55backupaudit"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_policy"
_COLUMN = "storage_client_address"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _COLUMN not in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))
    op.execute(sa.text(f"UPDATE {_TABLE} SET config_version = config_version + 1"))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
