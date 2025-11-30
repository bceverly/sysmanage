"""Drop firewall_role_closed_port table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2025-11-28 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from backend.persistence.models.core import GUID

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the firewall_role_closed_port table since we use default-deny and only track open ports."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Drop the closed port table if it exists
    if "firewall_role_closed_port" in tables:
        op.drop_index("ix_firewall_role_closed_port_port", "firewall_role_closed_port")
        op.drop_index(
            "ix_firewall_role_closed_port_role_id", "firewall_role_closed_port"
        )
        op.drop_table("firewall_role_closed_port")


def downgrade() -> None:
    """Recreate the firewall_role_closed_port table."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "firewall_role_closed_port" not in tables:
        op.create_table(
            "firewall_role_closed_port",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("firewall_role_id", GUID(), nullable=False),
            sa.Column("port_number", sa.Integer, nullable=False),
            sa.Column(
                "tcp", sa.Boolean, nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "udp", sa.Boolean, nullable=False, server_default=sa.text("false")
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["firewall_role_id"],
                ["firewall_role.id"],
                name="fk_closed_port_firewall_role",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_firewall_role_closed_port_role_id",
            "firewall_role_closed_port",
            ["firewall_role_id"],
        )
        op.create_index(
            "ix_firewall_role_closed_port_port",
            "firewall_role_closed_port",
            ["port_number"],
        )
