# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add Remove Package security role

Adds the ``Remove Package`` security role that gates package *uninstall*
(``backend/api/packages_operations.py`` checks ``SecurityRoles.REMOVE_PACKAGE``
for uninstall, mirroring ``ADD_PACKAGE`` for install — the role definition was
missing, so the check would raise ``AttributeError`` at runtime).

Backfills it to every user who already holds ``Add Package`` so install/uninstall
stay paired and an upgrade doesn't lock anyone out of a capability they had.

Idempotent and SQLite + PostgreSQL safe.

Revision ID: p13rmpkgrole
Revises: o12mgttenant
Create Date: 2026-06-17 00:00:00.000000
"""

from alembic import op
from sqlalchemy import inspect

revision = "p13rmpkgrole"
down_revision = "o12mgttenant"
branch_labels = None
depends_on = None

REMOVE_PACKAGE_ROLE_ID = "10000000-0000-0000-0000-0000000000a1"
PACKAGE_GROUP_ID = "00000000-0000-0000-0000-000000000002"  # "Package" management group
ADD_PACKAGE_ROLE_ID = "10000000-0000-0000-0000-000000000007"

# SQLite expression that produces a hyphenated UUID string (GUID() stores
# hyphenated strings on SQLite, matching the seed rows in 54fcacb0e742).
_SQLITE_UUID = (
    "lower("
    "substr(hex(randomblob(4)),1,8)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(6)),1,12))"
)


def _has_table(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    cast = "::uuid" if is_pg else ""

    if _has_table(bind, "security_roles"):
        op.execute(
            f"""
            INSERT INTO security_roles (id, name, description, group_id)
            SELECT '{REMOVE_PACKAGE_ROLE_ID}'{cast}, 'Remove Package',
                   'Remove packages from hosts',
                   '{PACKAGE_GROUP_ID}'{cast}
            WHERE NOT EXISTS (
                SELECT 1 FROM security_roles WHERE id = '{REMOVE_PACKAGE_ROLE_ID}'{cast}
            );
            """
        )

    # Backfill: grant "Remove Package" to every user who already holds
    # "Add Package", so install/uninstall stay paired for existing users.
    if _has_table(bind, "user_security_roles"):
        new_id = "gen_random_uuid()" if is_pg else _SQLITE_UUID
        now = "now()" if is_pg else "datetime('now')"
        op.execute(
            f"""
            INSERT INTO user_security_roles (id, user_id, role_id, granted_at)
            SELECT {new_id}, usr.user_id, '{REMOVE_PACKAGE_ROLE_ID}'{cast}, {now}
            FROM user_security_roles usr
            WHERE usr.role_id = '{ADD_PACKAGE_ROLE_ID}'{cast}
              AND NOT EXISTS (
                SELECT 1 FROM user_security_roles ex
                WHERE ex.user_id = usr.user_id
                  AND ex.role_id = '{REMOVE_PACKAGE_ROLE_ID}'{cast}
              );
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    cast = "::uuid" if is_pg else ""

    if _has_table(bind, "user_security_roles"):
        op.execute(
            f"DELETE FROM user_security_roles "
            f"WHERE role_id = '{REMOVE_PACKAGE_ROLE_ID}'{cast};"
        )
    if _has_table(bind, "security_roles"):
        op.execute(
            f"DELETE FROM security_roles "
            f"WHERE id = '{REMOVE_PACKAGE_ROLE_ID}'{cast};"
        )
