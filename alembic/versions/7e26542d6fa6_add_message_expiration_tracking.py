"""add_message_expiration_tracking

Revision ID: 7e26542d6fa6
Revises: 5cf4689c3227
Create Date: 2025-09-12 13:27:23.848482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e26542d6fa6'
down_revision: Union[str, None] = '5cf4689c3227'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add message expiration tracking to message_queue table."""
    # Add expired_at column to track when messages expire
    op.add_column('message_queue',
                  sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True))

    # Add index for efficient expiration queries
    op.create_index('idx_queue_expiration', 'message_queue', ['status', 'expired_at'])

    # Update existing failed messages with an expiration timestamp (1 hour from creation)
    # This prevents old failed messages from appearing in the queue management UI
    from sqlalchemy import text
    connection = op.get_bind()
    connection.execute(
        text("""
        UPDATE message_queue
        SET expired_at = created_at + INTERVAL '1 hour'
        WHERE status = 'failed' AND expired_at IS NULL
        """)
    )


def downgrade() -> None:
    """Remove message expiration tracking."""
    # Drop the index first
    op.drop_index('idx_queue_expiration', table_name='message_queue')

    # Remove the column
    op.drop_column('message_queue', 'expired_at')
