"""add_audit_log_table

Revision ID: 10ed1b8b7511
Revises: 9992c755bfdf
Create Date: 2025-10-12 19:18:47.823127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10ed1b8b7511'
down_revision: Union[str, None] = '9992c755bfdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'audit_log' not in inspector.get_table_names():
        op.create_table(
            'audit_log',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('timestamp', sa.DateTime(), nullable=False),
            sa.Column('user_id', sa.UUID(), nullable=True),  # Nullable for system actions
            sa.Column('username', sa.String(length=255), nullable=True),  # Denormalized for historical record
            sa.Column('action_type', sa.String(length=50), nullable=False),  # e.g., 'CREATE', 'UPDATE', 'DELETE', 'AGENT_MESSAGE'
            sa.Column('entity_type', sa.String(length=100), nullable=False),  # e.g., 'host', 'user', 'package', 'script'
            sa.Column('entity_id', sa.String(length=255), nullable=True),  # ID of the affected entity
            sa.Column('entity_name', sa.String(length=255), nullable=True),  # Denormalized name for display
            sa.Column('description', sa.Text(), nullable=False),  # Human-readable description
            sa.Column('details', sa.JSON(), nullable=True),  # Additional structured data (old/new values, etc.)
            sa.Column('ip_address', sa.String(length=45), nullable=True),  # IPv4 or IPv6
            sa.Column('user_agent', sa.String(length=500), nullable=True),  # Browser/client info
            sa.Column('result', sa.String(length=20), nullable=False),  # 'SUCCESS', 'FAILURE', 'PENDING'
            sa.Column('error_message', sa.Text(), nullable=True),  # Error details if failed
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes for common queries
        op.create_index(
            op.f('ix_audit_log_timestamp'),
            'audit_log',
            ['timestamp'],
            unique=False
        )
        op.create_index(
            op.f('ix_audit_log_user_id'),
            'audit_log',
            ['user_id'],
            unique=False
        )
        op.create_index(
            op.f('ix_audit_log_action_type'),
            'audit_log',
            ['action_type'],
            unique=False
        )
        op.create_index(
            op.f('ix_audit_log_entity_type'),
            'audit_log',
            ['entity_type'],
            unique=False
        )
        # Composite index for common filtering patterns
        op.create_index(
            op.f('ix_audit_log_user_timestamp'),
            'audit_log',
            ['user_id', 'timestamp'],
            unique=False
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_log_user_timestamp'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_entity_type'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action_type'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_user_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_timestamp'), table_name='audit_log')
    op.drop_table('audit_log')
