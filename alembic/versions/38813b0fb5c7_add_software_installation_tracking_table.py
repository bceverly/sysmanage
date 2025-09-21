"""add software installation tracking table

Revision ID: 38813b0fb5c7
Revises: ad66ac11e167
Create Date: 2025-09-20 14:25:38.783619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38813b0fb5c7'
down_revision: Union[str, None] = 'ad66ac11e167'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table already exists before creating it
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'software_installation_log' in existing_tables:
        print("Table 'software_installation_log' already exists, skipping creation")
        return

    # Create software_installation_log table
    op.create_table('software_installation_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('host_id', sa.Integer(), sa.ForeignKey('host.id', ondelete='CASCADE'), nullable=False),

        # Installation request details
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('requested_version', sa.String(length=100), nullable=True),
        sa.Column('requested_by', sa.String(length=100), nullable=False),  # User who requested installation

        # Request tracking
        sa.Column('installation_id', sa.String(length=36), nullable=False, unique=True),  # UUID for tracking
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),  # pending, queued, installing, completed, failed, cancelled

        # Timestamps
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),

        # Installation results
        sa.Column('installed_version', sa.String(length=100), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('installation_log', sa.Text(), nullable=True),  # Command output/logs

        # Metadata
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for efficient querying
    op.create_index('ix_software_installation_log_host_id', 'software_installation_log', ['host_id'])
    op.create_index('ix_software_installation_log_installation_id', 'software_installation_log', ['installation_id'])
    op.create_index('ix_software_installation_log_status', 'software_installation_log', ['status'])
    op.create_index('ix_software_installation_log_requested_at', 'software_installation_log', ['requested_at'])
    op.create_index('ix_software_installation_log_package_name', 'software_installation_log', ['package_name'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_software_installation_log_package_name', table_name='software_installation_log')
    op.drop_index('ix_software_installation_log_requested_at', table_name='software_installation_log')
    op.drop_index('ix_software_installation_log_status', table_name='software_installation_log')
    op.drop_index('ix_software_installation_log_installation_id', table_name='software_installation_log')
    op.drop_index('ix_software_installation_log_host_id', table_name='software_installation_log')

    # Drop table
    op.drop_table('software_installation_log')
