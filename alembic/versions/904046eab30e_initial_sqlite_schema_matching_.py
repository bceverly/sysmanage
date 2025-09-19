"""Initial SQLite schema matching PostgreSQL

Revision ID: 904046eab30e
Revises:
Create Date: 2025-09-19 08:37:18.945032

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '904046eab30e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use SQLAlchemy metadata to auto-generate proper DDL for each dialect
    from backend.persistence.db import Base
    from backend.persistence import models  # Import all models to register them

    # Create all tables using SQLAlchemy metadata - this will generate
    # the correct DDL for each database dialect (PostgreSQL vs SQLite)
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    # Drop all tables using SQLAlchemy metadata
    from backend.persistence.db import Base
    from backend.persistence import models  # Import all models to register them

    Base.metadata.drop_all(op.get_bind())