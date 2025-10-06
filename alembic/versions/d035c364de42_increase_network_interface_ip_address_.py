"""Increase network interface IP address field lengths

Revision ID: d035c364de42
Revises: ed9659130b39
Create Date: 2025-10-05 10:10:03.314917

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd035c364de42'
down_revision: Union[str, None] = 'ed9659130b39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # Check if network_interface table exists and if columns need to be altered
    inspector = sa.inspect(bind)
    if 'network_interface' not in inspector.get_table_names():
        # Table doesn't exist yet (fresh install from scratch), skip this migration
        return

    # Get current column info to check if migration is needed
    columns = {col['name']: col for col in inspector.get_columns('network_interface')}

    # Check if columns already have the correct length (fresh DB from schema)
    needs_migration = False
    for col_name in ['ipv4_address', 'ipv6_address', 'netmask', 'broadcast']:
        if col_name in columns:
            col_type = columns[col_name]['type']
            # Check if the column type is String and length is less than 45
            if hasattr(col_type, 'length') and col_type.length and col_type.length < 45:
                needs_migration = True
                break

    if not needs_migration:
        # Columns already have correct length, skip migration
        return

    # Increase IP address field lengths to support IPv6 and extended formats
    if is_sqlite:
        # SQLite doesn't support ALTER COLUMN, use batch operations
        with op.batch_alter_table('network_interface', schema=None) as batch_op:
            batch_op.alter_column('ipv4_address',
                                existing_type=sa.String(15),
                                type_=sa.String(45),
                                existing_nullable=True)
            batch_op.alter_column('ipv6_address',
                                existing_type=sa.String(39),
                                type_=sa.String(45),
                                existing_nullable=True)
            batch_op.alter_column('netmask',
                                existing_type=sa.String(15),
                                type_=sa.String(45),
                                existing_nullable=True)
            batch_op.alter_column('broadcast',
                                existing_type=sa.String(15),
                                type_=sa.String(45),
                                existing_nullable=True)
    else:
        # PostgreSQL supports ALTER COLUMN directly
        op.alter_column('network_interface', 'ipv4_address',
                        existing_type=sa.String(15),
                        type_=sa.String(45),
                        existing_nullable=True)
        op.alter_column('network_interface', 'ipv6_address',
                        existing_type=sa.String(39),
                        type_=sa.String(45),
                        existing_nullable=True)
        op.alter_column('network_interface', 'netmask',
                        existing_type=sa.String(15),
                        type_=sa.String(45),
                        existing_nullable=True)
        op.alter_column('network_interface', 'broadcast',
                        existing_type=sa.String(15),
                        type_=sa.String(45),
                        existing_nullable=True)


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # Revert IP address field lengths to original sizes
    if is_sqlite:
        # SQLite doesn't support ALTER COLUMN, use batch operations
        with op.batch_alter_table('network_interface', schema=None) as batch_op:
            batch_op.alter_column('broadcast',
                                existing_type=sa.String(45),
                                type_=sa.String(15),
                                existing_nullable=True)
            batch_op.alter_column('netmask',
                                existing_type=sa.String(45),
                                type_=sa.String(15),
                                existing_nullable=True)
            batch_op.alter_column('ipv6_address',
                                existing_type=sa.String(45),
                                type_=sa.String(39),
                                existing_nullable=True)
            batch_op.alter_column('ipv4_address',
                                existing_type=sa.String(45),
                                type_=sa.String(15),
                                existing_nullable=True)
    else:
        # PostgreSQL supports ALTER COLUMN directly
        op.alter_column('network_interface', 'broadcast',
                        existing_type=sa.String(45),
                        type_=sa.String(15),
                        existing_nullable=True)
        op.alter_column('network_interface', 'netmask',
                        existing_type=sa.String(45),
                        type_=sa.String(15),
                        existing_nullable=True)
        op.alter_column('network_interface', 'ipv6_address',
                        existing_type=sa.String(45),
                        type_=sa.String(39),
                        existing_nullable=True)
        op.alter_column('network_interface', 'ipv4_address',
                        existing_type=sa.String(45),
                        type_=sa.String(15),
                        existing_nullable=True)
