# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Legal hold (27.2): ``backup_legal_hold``.

A held snapshot is kept by every prune of its repository until released
(restate 3.4.0.0 ``keep_snapshot``).  A pure additive CREATE TABLE;
idempotent and identical on SQLite and PostgreSQL.

Revision ID: q101legalhold
Revises: q100foureyes
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q101legalhold"
down_revision: Union[str, None] = "q100foureyes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "backup_legal_hold"
_INDEXES = (
    ("ix_backup_legal_hold_policy_id", ["policy_id"]),
    ("ix_backup_legal_hold_host_id", ["host_id"]),
)


def _guid_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    guid = _guid_type()
    if _TABLE not in set(inspector.get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "policy_id",
                guid,
                sa.ForeignKey("backup_policy.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "host_id",
                guid,
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("snapshot", sa.String(255), nullable=False),
            sa.Column("owner", sa.String(255), nullable=False),
            sa.Column("reason", sa.String(1000), nullable=False),
            sa.Column("placed_by", sa.String(255), nullable=False),
            sa.Column("placed_at", sa.DateTime(), nullable=False),
            sa.Column("released_by", sa.String(255), nullable=True),
            sa.Column("released_at", sa.DateTime(), nullable=True),
        )
    existing = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for name, columns in _INDEXES:
        if name not in existing:
            op.create_index(name, _TABLE, columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for name, _columns in _INDEXES:
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
