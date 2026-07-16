# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add Manage Tenants security role (Phase 13.1)

Adds the ``Manage Tenants`` security role that gates control-plane tenant
provisioning/deletion, and backfills it to existing admin-tier users (those
who already hold ``Add User``) so an upgrade doesn't lock anyone out of a
capability they previously had via the interim ``Add User`` gate.

Idempotent and SQLite + PostgreSQL safe.

Revision ID: o12mgttenant
Revises: n11cfgsettings
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op
from sqlalchemy import inspect

revision = "o12mgttenant"
down_revision = "n11cfgsettings"
branch_labels = None
depends_on = None

MANAGE_TENANTS_ROLE_ID = "10000000-0000-0000-0000-0000000000a0"
USER_GROUP_ID = "00000000-0000-0000-0000-000000000004"  # "User" management group
ADD_USER_ROLE_ID = "10000000-0000-0000-0000-000000000015"

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
            SELECT '{MANAGE_TENANTS_ROLE_ID}'{cast}, 'Manage Tenants',
                   'Provision and delete tenants in the multi-tenancy control plane',
                   '{USER_GROUP_ID}'{cast}
            WHERE NOT EXISTS (
                SELECT 1 FROM security_roles WHERE id = '{MANAGE_TENANTS_ROLE_ID}'{cast}
            );
            """
        )

    # Backfill: grant the new role to every user who already has "Add User"
    # (the interim admin-tier gate), so existing admins keep the capability.
    if _has_table(bind, "user_security_roles"):
        new_id = "gen_random_uuid()" if is_pg else _SQLITE_UUID
        now = "now()" if is_pg else "datetime('now')"
        op.execute(
            f"""
            INSERT INTO user_security_roles (id, user_id, role_id, granted_at)
            SELECT {new_id}, usr.user_id, '{MANAGE_TENANTS_ROLE_ID}'{cast}, {now}
            FROM user_security_roles usr
            WHERE usr.role_id = '{ADD_USER_ROLE_ID}'{cast}
              AND NOT EXISTS (
                SELECT 1 FROM user_security_roles ex
                WHERE ex.user_id = usr.user_id
                  AND ex.role_id = '{MANAGE_TENANTS_ROLE_ID}'{cast}
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
            f"WHERE role_id = '{MANAGE_TENANTS_ROLE_ID}'{cast};"
        )
    if _has_table(bind, "security_roles"):
        op.execute(
            f"DELETE FROM security_roles "
            f"WHERE id = '{MANAGE_TENANTS_ROLE_ID}'{cast};"
        )
