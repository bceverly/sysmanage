# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Moving a host with its backups to another target (27.3): ``backup_move``.

A host that already has backups moves by copy, then switch: its repository
is copied into the new target with ``restate copy``, verified there, and
only then does its policy name the new target.  One row per move.  Additive
only (a new table); idempotent and identical on SQLite and PostgreSQL.

Revision ID: q107move
Revises: q106offsiteread
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q107move"
down_revision: Union[str, None] = "q106offsiteread"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "backup_move"
_INDEXES = (
    ("ix_backup_move_policy_id", ["policy_id"]),
    ("ix_backup_move_target_id", ["target_id"]),
)


def _guid_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def _columns(guid):
    return [
        sa.Column("id", guid, primary_key=True),
        sa.Column(
            "policy_id",
            guid,
            sa.ForeignKey("backup_policy.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The target it moves to, and the one it moves from.
        sa.Column(
            "target_id",
            guid,
            sa.ForeignKey("backup_target.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_target_id",
            guid,
            sa.ForeignKey("backup_target.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("repo_dir", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("acked_version", sa.Integer(), nullable=True),
        sa.Column("prepared_at", sa.DateTime(), nullable=True),
        sa.Column("token_sha256", sa.String(64), nullable=True),
        sa.Column("token_sha256_old", sa.String(64), nullable=True),
        sa.Column("snapshots", sa.Text(), nullable=True),
        sa.Column("pruned", sa.Text(), nullable=True),
        sa.Column("repository_bytes", sa.BigInteger(), nullable=True),
        sa.Column("last_copy_at", sa.DateTime(), nullable=True),
        sa.Column("last_copy_status", sa.String(32), nullable=True),
        sa.Column("last_copy_error", sa.String(1000), nullable=True),
        sa.Column("abilities", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("switched_at", sa.DateTime(), nullable=True),
        # The old repository is kept until then (NULL: kept for good).
        sa.Column("keep_until", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in set(inspector.get_table_names()):
        op.create_table(_TABLE, *_columns(_guid_type()))
    existing = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for name, columns in _INDEXES:
        if name not in existing:
            op.create_index(name, _TABLE, columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE in set(inspector.get_table_names()):
        existing = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
        for name, _unused in _INDEXES:
            if name in existing:
                op.drop_index(name, table_name=_TABLE)
        op.drop_table(_TABLE)
