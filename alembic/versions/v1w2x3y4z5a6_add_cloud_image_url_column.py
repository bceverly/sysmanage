"""add_cloud_image_url_column

Revision ID: v1w2x3y4z5a6
Revises: u0v1w2x3y4z5
Create Date: 2025-12-31 15:00:00.000000

This migration adds cloud_image_url and iso_url columns to the
child_host_distribution table for KVM and VMM distributions.
It also populates cloud_image_url for existing KVM distributions
from their install_identifier field.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "v1w2x3y4z5a6"
down_revision: Union[str, None] = "u0v1w2x3y4z5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cloud_image_url and iso_url columns to child_host_distribution."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Add cloud_image_url column
    op.add_column(
        "child_host_distribution",
        sa.Column("cloud_image_url", sa.String(500), nullable=True),
    )

    # Add iso_url column
    op.add_column(
        "child_host_distribution",
        sa.Column("iso_url", sa.String(500), nullable=True),
    )

    # Populate cloud_image_url for existing KVM distributions from install_identifier
    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET cloud_image_url = install_identifier
            WHERE child_type = 'kvm'
              AND install_identifier IS NOT NULL
              AND install_identifier LIKE 'http%'
            """
        )
    )

    # Populate iso_url for existing VMM distributions from install_identifier
    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET iso_url = install_identifier
            WHERE child_type = 'vmm'
              AND install_identifier IS NOT NULL
              AND install_identifier LIKE 'http%'
            """
        )
    )


def downgrade() -> None:
    """Remove cloud_image_url and iso_url columns."""
    op.drop_column("child_host_distribution", "iso_url")
    op.drop_column("child_host_distribution", "cloud_image_url")
