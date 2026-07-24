# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add snap channel/revision/confinement to software_package (Phase 17.1 — S2)

Channel-aware snap detection: ``snap list`` exposes each snap's tracking
channel, revision, and (best-effort) confinement, which the agent now captures
structurally instead of folding the channel into ``source``.  These columns are
nullable and only populated for snap packages; all other package managers leave
them NULL.

Part of the TENANT chain (``software_package`` is per-host inventory, unprefixed),
chained off ``q16clmexport``.  Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q17snapchan
Revises: q16clmexport
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "q17snapchan"
down_revision: Union[str, None] = "q16clmexport"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "software_package"
_COLUMNS = (
    ("channel", sa.String(length=100)),
    ("revision", sa.String(length=50)),
    ("confinement", sa.String(length=20)),
)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, coltype in _COLUMNS:
        if name not in existing:
            # ADD COLUMN (nullable) is supported natively on SQLite + PostgreSQL.
            op.add_column(_TABLE, sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    # expand-contract-ok: reverse of this revision's add_column set.  Batch mode
    # so DROP COLUMN works on SQLite (table-rebuild) as well as PostgreSQL.
    to_drop = [name for name, _ in reversed(_COLUMNS) if name in existing]
    if to_drop:
        with op.batch_alter_table(_TABLE) as batch:
            for name in to_drop:
                batch.drop_column(name)
