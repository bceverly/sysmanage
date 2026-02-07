"""add_proplus_plugin_cache_table

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-02-05 00:00:00.000000

Adds the proplus_plugin_cache table for tracking downloaded
Pro+ JavaScript plugin bundles.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """Check if a table already exists."""
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not table_exists("proplus_plugin_cache"):
        op.create_table(
            "proplus_plugin_cache",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("module_code", sa.String(100), nullable=False, index=True),
            sa.Column("version", sa.String(50), nullable=False),
            sa.Column("file_path", sa.String(500), nullable=False),
            sa.Column("file_hash", sa.String(128), nullable=False),
            sa.Column("downloaded_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("proplus_plugin_cache")
