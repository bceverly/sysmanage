# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Multiple backup targets (27.3): which target is the default, where each
one is, and the target a tag policy names.

``backup_target.is_default`` -- the target a new host policy uses unless it
names another; the oldest existing target becomes the default here.
``backup_target.location`` -- where the target is (a site, room or
building), for the operator; NULL = not given.
``backup_tag_policy.target_id`` -- the target the hosts it covers back up
to; NULL = the default.  A soft reference, like ``storage_host_id``: a
target in use by a tag policy cannot be deleted.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q102multitarget
Revises: q101legalhold
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q102multitarget"
down_revision: Union[str, None] = "q101legalhold"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _guid_type():
    if op.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def _columns():
    return (
        ("backup_target", "is_default", sa.Boolean()),
        ("backup_target", "location", sa.String(255)),
        ("backup_tag_policy", "target_id", _guid_type()),
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column, kind in _columns():
        if table not in tables:
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, kind, nullable=True))
    if "backup_target" not in tables:
        return
    # The oldest target is the default, unless one already is (a rerun).
    marked = bind.execute(
        sa.text("SELECT COUNT(*) FROM backup_target WHERE is_default = :yes"),
        {"yes": True},
    ).scalar()
    if not marked:
        oldest = bind.execute(
            sa.text("SELECT id FROM backup_target ORDER BY created_at LIMIT 1")
        ).scalar()
        if oldest is not None:
            bind.execute(
                sa.text("UPDATE backup_target SET is_default = :yes WHERE id = :id"),
                {"yes": True, "id": oldest},
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column, _kind in _columns():
        if table not in tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
