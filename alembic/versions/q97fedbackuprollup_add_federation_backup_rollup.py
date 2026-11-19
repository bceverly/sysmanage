# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add federation_backup_rollup (Phase 27.1 -- backup status per site).

Each federated site server owns its own backup target and all of its
backup data; the coordinator receives only a status snapshot from each
site (hosts covered, hosts needing attention, the oldest last good backup,
total repository size, verification states).  A pure additive
``CREATE TABLE``, idempotent and identical on SQLite and PostgreSQL.

Revision ID: q97fedbackuprollup
Revises: q96autoupdaterollout
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q97fedbackuprollup"
down_revision: Union[str, None] = "q96autoupdaterollout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "federation_backup_rollup"
_INDEX = "ix_federation_backup_rollup_site_snapshot"


def _guid_type():
    """UUID-typed column for the live dialect (Postgres UUID / String(36)).

    Mirrors ``backend.persistence.models.core.GUID`` without importing the
    app package (Alembic runs against a bare engine).
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    """Create ``federation_backup_rollup`` + its index.  Idempotent: skips
    the table / index if it already exists from a prior partial run."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    guid = _guid_type()

    if _TABLE not in set(inspector.get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "site_id",
                guid,
                sa.ForeignKey("federation_sites.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("snapshot_at", sa.DateTime(), nullable=False),
            sa.Column(
                "configured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "target_problem",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "hosts_with_policy",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "attention_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "never_backed_up",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "repository_bytes",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("oldest_last_good_at", sa.DateTime(), nullable=True),
            sa.Column("status_counts_json", sa.Text(), nullable=True),
            sa.Column("verification_counts_json", sa.Text(), nullable=True),
            sa.Column("attention_hosts_json", sa.Text(), nullable=True),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if _INDEX not in existing_indexes:
        op.create_index(_INDEX, _TABLE, ["site_id", "snapshot_at"])


def downgrade() -> None:
    """Drop ``federation_backup_rollup`` (+ index) if present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if _INDEX in existing_indexes:
        op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
