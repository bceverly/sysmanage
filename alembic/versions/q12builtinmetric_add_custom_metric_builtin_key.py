# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_custom_metric_builtin_key

Phase 21.5: built-in metric graphs.  The five host-level series (CPU, memory,
swap, load, fullest disk) are stored as SYSTEM-DEFINED custom metrics, so the
retention prune, samples API, Prometheus exporter and alerting condition all
apply to them unchanged.  ``builtin_key`` names which built-in a row is
(``host.cpu_percent`` ...); NULL for every operator-defined metric.

A unique index, not a unique constraint: both SQLite and PostgreSQL allow any
number of NULLs in a unique index, which is exactly "every operator metric is
NULL, every built-in appears once".

Expand-only (a nullable column and an index), so it is safe under the
expand-contract guard.  Idempotent + cross-dialect.

Revision ID: q12builtinmetric
Revises: q11posture
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q12builtinmetric"
down_revision: Union[str, None] = "q11posture"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "custom_metric"
COLUMN = "builtin_key"
INDEX = "ix_custom_metric_builtin_key"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in set(inspector.get_table_names()):
        return
    if COLUMN not in {col["name"] for col in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(64), nullable=True))
    if INDEX not in {ix["name"] for ix in inspector.get_indexes(TABLE)}:
        op.create_index(INDEX, TABLE, [COLUMN], unique=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in set(inspector.get_table_names()):
        return
    if INDEX in {ix["name"] for ix in inspector.get_indexes(TABLE)}:
        op.drop_index(INDEX, table_name=TABLE)
    if COLUMN in {col["name"] for col in inspector.get_columns(TABLE)}:
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
