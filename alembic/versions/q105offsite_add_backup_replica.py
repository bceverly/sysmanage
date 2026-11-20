# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Off-site copies (27.3): ``backup_target.replica_target_id`` and
``backup_replica``.

A target may name another target as its off-site copy; each host's
repository there is one ``backup_replica`` row.  Additive only (a nullable
column and a new table); idempotent and identical on SQLite and PostgreSQL.

Revision ID: q105offsite
Revises: q104diskspace
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q105offsite"
down_revision: Union[str, None] = "q104diskspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TARGET = "backup_target"
_COLUMN = "replica_target_id"
_TABLE = "backup_replica"
_INDEXES = (
    ("ix_backup_replica_policy_id", ["policy_id"]),
    ("ix_backup_replica_target_id", ["target_id"]),
)
_UNIQUE = "uq_backup_replica_policy_target"


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
        sa.Column(
            "target_id",
            guid,
            sa.ForeignKey("backup_target.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("repo_dir", sa.String(255), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("acked_version", sa.Integer(), nullable=True),
        sa.Column("prepared_at", sa.DateTime(), nullable=True),
        sa.Column("token_sha256", sa.String(64), nullable=True),
        sa.Column("token_sha256_old", sa.String(64), nullable=True),
        sa.Column("snapshots", sa.Text(), nullable=True),
        sa.Column("pruned", sa.Text(), nullable=True),
        sa.Column("newest_snapshot", sa.String(255), nullable=True),
        sa.Column("newest_at", sa.DateTime(), nullable=True),
        sa.Column("repository_bytes", sa.BigInteger(), nullable=True),
        sa.Column("last_copy_at", sa.DateTime(), nullable=True),
        sa.Column("last_copy_status", sa.String(32), nullable=True),
        sa.Column("last_copy_error", sa.String(1000), nullable=True),
        sa.Column("abilities", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("policy_id", "target_id", name=_UNIQUE),
    ]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    guid = _guid_type()
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TARGET)}:
        op.add_column(_TARGET, sa.Column(_COLUMN, guid, nullable=True))
    if _TABLE not in set(inspector.get_table_names()):
        op.create_table(_TABLE, *_columns(guid))
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
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TARGET)}:
        with op.batch_alter_table(_TARGET) as batch:
            batch.drop_column(_COLUMN)
