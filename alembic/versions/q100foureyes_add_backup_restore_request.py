# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Four-eyes restore approval (27.2): ``backup_restore_request``.

A restore over a host's own files waits here for a second approver when the
tenant has turned four-eyes approval on (Enterprise backup_ops_engine).  A
pure additive CREATE TABLE; idempotent and identical on SQLite and
PostgreSQL.

Revision ID: q100foureyes
Revises: q99backuprpo
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q100foureyes"
down_revision: Union[str, None] = "q99backuprpo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "backup_restore_request"
_INDEXES = (
    ("ix_backup_restore_request_host_id", ["host_id"]),
    ("ix_backup_restore_request_status", ["status"]),
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
                "host_id",
                guid,
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("requested_by", sa.String(255), nullable=False),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("decided_by", sa.String(255), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("run_id", guid, nullable=True),
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
