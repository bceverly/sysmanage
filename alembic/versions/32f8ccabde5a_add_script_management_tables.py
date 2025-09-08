"""Add script management tables

Revision ID: 32f8ccabde5a
Revises: 4cb500a6864b
Create Date: 2025-09-06 19:04:18.306577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32f8ccabde5a'
down_revision: Union[str, None] = '4cb500a6864b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create saved_scripts table
    op.create_table(
        'saved_scripts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('shell_type', sa.String(50), nullable=False),
        sa.Column('platform', sa.String(50), nullable=True),
        sa.Column('run_as_user', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for saved_scripts
    op.create_index('idx_saved_scripts_name', 'saved_scripts', ['name'])
    op.create_index('idx_saved_scripts_platform', 'saved_scripts', ['platform'])
    op.create_index('idx_saved_scripts_active', 'saved_scripts', ['is_active'])

    # Create script_execution_log table
    op.create_table(
        'script_execution_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('host_id', sa.Integer(), nullable=False),
        sa.Column('saved_script_id', sa.Integer(), nullable=True),
        sa.Column('script_name', sa.String(255), nullable=True),
        sa.Column('script_content', sa.Text(), nullable=False),
        sa.Column('shell_type', sa.String(50), nullable=False),
        sa.Column('run_as_user', sa.String(100), nullable=True),
        sa.Column('requested_by', sa.String(100), nullable=False),
        sa.Column('execution_id', sa.String(36), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('stdout_output', sa.Text(), nullable=True),
        sa.Column('stderr_output', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['saved_script_id'], ['saved_scripts.id'], ondelete='SET NULL')
    )

    # Create indexes for script_execution_log
    op.create_index('idx_script_exec_host', 'script_execution_log', ['host_id'])
    op.create_index('idx_script_exec_status', 'script_execution_log', ['status'])
    op.create_index('idx_script_exec_execution_id', 'script_execution_log', ['execution_id'], unique=True)
    op.create_index('idx_script_exec_created', 'script_execution_log', ['created_at'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_script_exec_created', table_name='script_execution_log')
    op.drop_index('idx_script_exec_execution_id', table_name='script_execution_log')
    op.drop_index('idx_script_exec_status', table_name='script_execution_log')
    op.drop_index('idx_script_exec_host', table_name='script_execution_log')
    op.drop_index('idx_saved_scripts_active', table_name='saved_scripts')
    op.drop_index('idx_saved_scripts_platform', table_name='saved_scripts')
    op.drop_index('idx_saved_scripts_name', table_name='saved_scripts')

    # Drop tables
    op.drop_table('script_execution_log')
    op.drop_table('saved_scripts')
