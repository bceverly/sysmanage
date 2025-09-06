"""Add message queue tables for server communication

Revision ID: 4cb500a6864b
Revises: 8e2a5814b704
Create Date: 2025-09-04 14:57:47.064728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cb500a6864b'
down_revision: Union[str, None] = '8e2a5814b704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create message queue table
    op.create_table('message_queue',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('host_id', sa.Integer(), nullable=True),
    sa.Column('message_id', sa.String(length=36), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('message_type', sa.String(length=50), nullable=False),
    sa.Column('message_data', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('priority', sa.String(length=10), nullable=False),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('max_retries', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('correlation_id', sa.String(length=36), nullable=True),
    sa.Column('reply_to', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for message queue
    op.create_index('idx_queue_cleanup', 'message_queue', ['status', 'completed_at'], unique=False)
    op.create_index('idx_queue_host_direction', 'message_queue', ['host_id', 'direction', 'status'], unique=False)
    op.create_index('idx_queue_processing', 'message_queue', ['direction', 'status', 'priority', 'scheduled_at'], unique=False)
    op.create_index('idx_queue_retry', 'message_queue', ['status', 'retry_count', 'max_retries'], unique=False)
    op.create_index(op.f('ix_message_queue_correlation_id'), 'message_queue', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_message_queue_direction'), 'message_queue', ['direction'], unique=False)
    op.create_index(op.f('ix_message_queue_host_id'), 'message_queue', ['host_id'], unique=False)
    op.create_index(op.f('ix_message_queue_message_id'), 'message_queue', ['message_id'], unique=True)
    op.create_index(op.f('ix_message_queue_message_type'), 'message_queue', ['message_type'], unique=False)
    op.create_index(op.f('ix_message_queue_priority'), 'message_queue', ['priority'], unique=False)
    op.create_index(op.f('ix_message_queue_reply_to'), 'message_queue', ['reply_to'], unique=False)
    op.create_index(op.f('ix_message_queue_status'), 'message_queue', ['status'], unique=False)

    # Create queue metrics table
    op.create_table('queue_metrics',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('metric_name', sa.String(length=50), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('host_id', sa.Integer(), nullable=True),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('total_time_ms', sa.Integer(), nullable=False),
    sa.Column('avg_time_ms', sa.Integer(), nullable=False),
    sa.Column('min_time_ms', sa.Integer(), nullable=True),
    sa.Column('max_time_ms', sa.Integer(), nullable=True),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for queue metrics
    op.create_index('idx_metrics_host', 'queue_metrics', ['host_id', 'metric_name', 'direction'], unique=False)
    op.create_index('idx_metrics_latest', 'queue_metrics', ['metric_name', 'direction', 'updated_at'], unique=False)
    op.create_index('idx_metrics_period', 'queue_metrics', ['metric_name', 'direction', 'period_start', 'period_end'], unique=False)
    op.create_index(op.f('ix_queue_metrics_direction'), 'queue_metrics', ['direction'], unique=False)
    op.create_index(op.f('ix_queue_metrics_host_id'), 'queue_metrics', ['host_id'], unique=False)
    op.create_index(op.f('ix_queue_metrics_metric_name'), 'queue_metrics', ['metric_name'], unique=False)


def downgrade() -> None:
    # Drop queue metrics table and indexes
    op.drop_index(op.f('ix_queue_metrics_metric_name'), table_name='queue_metrics')
    op.drop_index(op.f('ix_queue_metrics_host_id'), table_name='queue_metrics')
    op.drop_index(op.f('ix_queue_metrics_direction'), table_name='queue_metrics')
    op.drop_index('idx_metrics_period', table_name='queue_metrics')
    op.drop_index('idx_metrics_latest', table_name='queue_metrics')
    op.drop_index('idx_metrics_host', table_name='queue_metrics')
    op.drop_table('queue_metrics')

    # Drop message queue table and indexes
    op.drop_index(op.f('ix_message_queue_status'), table_name='message_queue')
    op.drop_index(op.f('ix_message_queue_reply_to'), table_name='message_queue')
    op.drop_index(op.f('ix_message_queue_priority'), table_name='message_queue')
    op.drop_index(op.f('ix_message_queue_message_type'), table_name='message_queue')
    op.drop_index(op.f('ix_message_queue_message_id'), table_name='message_queue')
    op.drop_index(op.f('ix_message_queue_host_id'), table_name='message_queue')
    op.drop_index(op.f('ix_message_queue_direction'), table_name='message_queue')
    op.drop_index(op.f('ix_message_queue_correlation_id'), table_name='message_queue')
    op.drop_index('idx_queue_retry', table_name='message_queue')
    op.drop_index('idx_queue_processing', table_name='message_queue')
    op.drop_index('idx_queue_host_direction', table_name='message_queue')
    op.drop_index('idx_queue_cleanup', table_name='message_queue')
    op.drop_table('message_queue')
