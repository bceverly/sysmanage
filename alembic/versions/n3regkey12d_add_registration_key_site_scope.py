# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_registration_key_site_scope

Phase 12.4: optional federation-site scope on registration keys.

Adds a nullable ``site_id`` column to ``registration_keys`` plus a
covering index.  When set, a key restricts the hosts it can enroll
to the named subordinate site — used by the coordinator's
"generate enrollment key for site X" workflow.

Idempotent — re-runnable on a database that already has the column
or the index.  FK targets ``federation_sites.id`` (added by
``m1fedschema``) with ``ON DELETE SET NULL`` so removing a site
preserves its historical keys.  Column is nullable and lacks a
default so existing OSS rows survive untouched.

Revision ID: n3regkey12d
Revises: m2fed12c
Create Date: 2026-05-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "n3regkey12d"
down_revision: Union[str, None] = "m2fed12c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "registration_keys"
_COLUMN_NAME = "site_id"
_INDEX_NAME = "ix_registration_keys_site_id"
_FK_NAME = "fk_registration_keys_site_id_federation_sites"


def _guid_type():
    """Dialect-portable UUID column type — mirrors the m1fedschema
    helper so the two migrations agree on column type."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Parent table check — if registration_keys doesn't exist yet
    # (clean install before phase-8.1 migrations applied), let those
    # earlier revisions re-run first.
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN_NAME not in existing_columns:
        # SQLite can't add columns with inline FKs portably, so we
        # add the column without the FK then attach it via batch
        # alter — alembic's ``batch_alter_table`` handles the table-
        # rebuild dance on SQLite while emitting a plain ALTER on PG.
        op.add_column(
            _TABLE, sa.Column(_COLUMN_NAME, _guid_type(), nullable=True)
        )

        # Only attempt the named FK on PostgreSQL — SQLite's
        # ``ALTER TABLE ADD CONSTRAINT`` would require a batch
        # rebuild, and the SET NULL semantic is already what we want
        # at the application layer.  The PG branch keeps referential
        # integrity strict; SQLite test fixtures use the ORM which
        # honors the relationship.
        if bind.dialect.name == "postgresql":
            op.create_foreign_key(
                _FK_NAME,
                source_table=_TABLE,
                referent_table="federation_sites",
                local_cols=[_COLUMN_NAME],
                remote_cols=["id"],
                ondelete="SET NULL",
            )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if _INDEX_NAME not in existing_indexes:
        op.create_index(_INDEX_NAME, _TABLE, [_COLUMN_NAME], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if _INDEX_NAME in existing_indexes:
        op.drop_index(_INDEX_NAME, table_name=_TABLE)

    if bind.dialect.name == "postgresql":
        # Drop the FK before the column.  ``op.drop_constraint`` is a
        # no-op-with-warning when the constraint name doesn't exist,
        # so the partial-rollback case stays safe.
        existing_fks = {
            fk.get("name") for fk in inspector.get_foreign_keys(_TABLE)
        }
        if _FK_NAME in existing_fks:
            op.drop_constraint(_FK_NAME, _TABLE, type_="foreignkey")

    existing_columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN_NAME in existing_columns:
        op.drop_column(_TABLE, _COLUMN_NAME)
