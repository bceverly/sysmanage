"""add_enrollment_timestamps

Phase 12.1.C: enrollment refinements.

Adds two timestamp columns to ``federation_sites``:

  ``enrollment_token_expires_at``  — when the pending enrollment
                                     token stops being valid for
                                     ``complete_enrollment``.  NULL
                                     once the token is consumed or
                                     scrubbed.
  ``enrolled_at``                  — when ``complete_enrollment``
                                     last flipped the site to
                                     ``status='enrolled'``.  Survives
                                     suspend/resume cycles (those
                                     don't touch this column).

Idempotent — re-runnable on a database that already has either
column.  Uses naive DateTime so it lands cleanly on both SQLite and
PostgreSQL (matches the convention every other federation column
already uses).

Revision ID: m2fed12c
Revises: m1fedschema
Create Date: 2026-05-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "m2fed12c"
down_revision: Union[str, None] = "m1fedschema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "federation_sites"
_NEW_COLUMNS = (
    ("enrollment_token_expires_at", sa.DateTime()),
    ("enrolled_at", sa.DateTime()),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # If the parent table itself doesn't exist yet (e.g. partial
    # rollback of m1fedschema), there's nothing to add.  Let the
    # m1fedschema upgrade re-run first and replay this one.
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing = {col["name"] for col in inspector.get_columns(_TABLE)}
    for name, type_ in _NEW_COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {col["name"] for col in inspector.get_columns(_TABLE)}
    for name, _ in reversed(_NEW_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
