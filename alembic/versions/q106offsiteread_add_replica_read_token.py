# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Restoring from an off-site copy (27.3): the backed-up host's read token.

The host reads its own off-site copy through the copy target's
restate-proxy with a token it made (only the SHA-256 is kept), granted
``read`` there -- so a restore works while its own site's storage is down.
Additive only (two nullable columns); idempotent on SQLite and PostgreSQL.

Revision ID: q106offsiteread
Revises: q105offsite
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q106offsiteread"
down_revision: Union[str, None] = "q105offsite"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "backup_replica"
_COLUMNS = ("read_token_sha256", "read_token_sha256_old")


def _have() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(_TABLE)}


def upgrade() -> None:
    have = _have()
    for name in _COLUMNS:
        if name not in have:
            op.add_column(_TABLE, sa.Column(name, sa.String(64), nullable=True))


def downgrade() -> None:
    have = _have()
    gone = [name for name in _COLUMNS if name in have]
    if gone:
        with op.batch_alter_table(_TABLE) as batch:
            for name in gone:
                batch.drop_column(name)
