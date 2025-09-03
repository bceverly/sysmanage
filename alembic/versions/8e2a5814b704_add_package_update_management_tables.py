"""Add package update management tables

Revision ID: 8e2a5814b704
Revises: 444e7d9e388c
Create Date: 2025-09-02 13:59:52.176062

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e2a5814b704'
down_revision: Union[str, None] = '444e7d9e388c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create package_updates table
    op.create_table('package_updates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('host_id', sa.Integer(), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('current_version', sa.String(length=100), nullable=True),
        sa.Column('available_version', sa.String(length=100), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('is_security_update', sa.Boolean(), nullable=False),
        sa.Column('is_system_update', sa.Boolean(), nullable=False),
        sa.Column('requires_reboot', sa.Boolean(), nullable=False),
        sa.Column('update_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('bundle_id', sa.String(length=255), nullable=True),
        sa.Column('repository', sa.String(length=100), nullable=True),
        sa.Column('channel', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_package_updates_package_name', 'package_updates', ['package_name'])
    op.create_index('ix_package_updates_package_manager', 'package_updates', ['package_manager'])
    op.create_index('ix_package_updates_is_security_update', 'package_updates', ['is_security_update'])
    op.create_index('ix_package_updates_is_system_update', 'package_updates', ['is_system_update'])
    op.create_index('ix_package_updates_status', 'package_updates', ['status'])

    # Create update_execution_log table
    op.create_table('update_execution_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('host_id', sa.Integer(), nullable=False),
        sa.Column('package_update_id', sa.Integer(), nullable=True),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('from_version', sa.String(length=100), nullable=True),
        sa.Column('to_version', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_log', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['package_update_id'], ['package_updates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_update_execution_log_status', 'update_execution_log', ['status'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_update_execution_log_status')
    op.drop_table('update_execution_log')

    op.drop_index('ix_package_updates_status')
    op.drop_index('ix_package_updates_is_system_update')
    op.drop_index('ix_package_updates_is_security_update')
    op.drop_index('ix_package_updates_package_manager')
    op.drop_index('ix_package_updates_package_name')
    op.drop_table('package_updates')
