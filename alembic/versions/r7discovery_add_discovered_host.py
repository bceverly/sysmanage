# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add discovered_host + install_source.purpose — Phase 18.2 S5

The "discovered hosts" parking lot: unmanaged machines that netbooted the
ephemeral RAM discovery probe and registered their hardware without touching
disk.  ``install_source.purpose`` distinguishes a discovery image from an OS
install source in the same catalog.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r7discovery
Revises: r6installsrc
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "r7discovery"
down_revision: Union[str, None] = "r6installsrc"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "discovered_host"


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if insp.has_table("install_source"):
        cols = {c["name"] for c in insp.get_columns("install_source")}
        if "purpose" not in cols:
            # Deliberately NOT indexed.  Two distinct values on a table with a
            # handful of rows gains nothing — and on SQLite the downgrade's
            # batch_alter_table recreates the table and replays reflected
            # indexes, so an index over the column being dropped makes
            # downgrade fail with "no such column: purpose".
            op.add_column(
                "install_source",
                sa.Column(
                    "purpose",
                    sa.String(length=20),
                    nullable=False,
                    server_default="install",
                ),
            )

    if insp.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("mac_address", sa.String(length=17), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("cpu_model", sa.String(length=255), nullable=True),
        sa.Column("cpu_count", sa.Integer(), nullable=True),
        sa.Column("memory_mb", sa.Integer(), nullable=True),
        sa.Column("disk_count", sa.Integer(), nullable=True),
        sa.Column("primary_disk", sa.String(length=120), nullable=True),
        sa.Column("manufacturer", sa.String(length=120), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mac_address"),
    )
    op.create_index("ix_discovered_host_mac", _TABLE, ["mac_address"])
    op.create_index("ix_discovered_host_state", _TABLE, ["state"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        op.drop_table(_TABLE)
    if insp.has_table("install_source"):
        cols = {c["name"] for c in insp.get_columns("install_source")}
        if "purpose" in cols:
            # batch_alter_table for old SQLite, which cannot DROP COLUMN.
            with op.batch_alter_table("install_source") as batch:
                batch.drop_column("purpose")
