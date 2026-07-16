# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Soften package_profiles.created_by from a hard FK to a soft GUID reference

``package_profiles`` is an unprefixed = TENANT-partition table (Phase 13.1).
Its ``created_by`` column carried a hard foreign key to the server-global
``user`` table — but once a profile lives in a tenant database that FK is
unsatisfiable: the tenant DB's ``user`` table is empty (users are server-global,
in the bootstrap/registry DB).  Creating a package profile while a tenant is
active therefore failed with::

    ForeignKeyViolation: package_profiles_created_by_fkey
    DETAIL: Key (created_by)=(...) is not present in table "user".

This drops the cross-partition FK, leaving ``created_by`` as a SOFT GUID
reference (matching ``audit_log.user_id``, which is already a bare GUID).  No
data is lost and no column is removed — the value still records who created the
profile; it simply isn't enforced across the partition boundary.  This is the
"no cross-partition FKs — soft refs" invariant of the multi-tenancy design.

Idempotent and SQLite + PostgreSQL safe.

Revision ID: q14softpkgprofcreatedby
Revises: p13rmpkgrole
Create Date: 2026-06-18 00:00:00.000000
"""

from alembic import op

revision = "q14softpkgprofcreatedby"
down_revision = "p13rmpkgrole"
branch_labels = None
depends_on = None

_FK_NAME = "package_profiles_created_by_fkey"


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # expand-contract-ok: drops a cross-partition FK only.  The
        # ``created_by`` COLUMN is kept (as a soft GUID reference), so this is a
        # pure loosening — old code that read created_by still works, and the FK
        # was already unsatisfiable in tenant databases.  IF EXISTS makes it
        # idempotent (a fresh DB built from the now-FK-less model has nothing to
        # drop).
        op.execute(f"ALTER TABLE package_profiles DROP CONSTRAINT IF EXISTS {_FK_NAME}")
    # SQLite: the FK is stored inline on the table and is unenforced by default
    # (PRAGMA foreign_keys is off), and in the collapsed/dev single-database mode
    # the ``user`` row is co-located so it never bites.  Fresh SQLite databases
    # are built from the updated (FK-less) model.  Nothing to drop here — no-op.


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Re-add the FK (idempotent).  NOTE: this only succeeds where the
        # referenced ``user`` rows are co-located (the bootstrap/collapsed DB);
        # downgrading a TENANT database would fail because its user table is
        # empty — the expected consequence of reverting a soft ref back to a
        # hard cross-partition FK.
        op.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
            f"'{_FK_NAME}') THEN "
            "ALTER TABLE package_profiles ADD CONSTRAINT "
            f"{_FK_NAME} FOREIGN KEY (created_by) "
            'REFERENCES "user"(id) ON DELETE SET NULL; '
            "END IF; END $$;"
        )
