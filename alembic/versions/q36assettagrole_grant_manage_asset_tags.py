# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""grant 'Manage Asset Tags' to existing tag editors (Phase 23.2)

q34assettag created the role but granted it to nobody.  A NEW install's
first admin receives every role, but on a server that was already running,
no one held it -- so the naming scheme, tag assignment and CSV import were
read-only for every user until someone granted the role by hand.  Same
backfill shape as o12mgttenant: every user who can already edit host tags
gets it.

Idempotent (never grants twice); safe on SQLite + PostgreSQL.  The role id was
generated when q34 ran, so it is looked up by name.

Revision ID: q36assettagrole
Revises: q35heldtag
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q36assettagrole"
down_revision: Union[str, None] = "q35heldtag"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_ROLE = "Manage Asset Tags"
_FROM_ROLE = "Edit Tags"
_SELECT = """
    FROM user_security_roles usr
    JOIN security_roles src ON src.id = usr.role_id AND src.name = :from_role
    JOIN security_roles target ON target.name = :role
    WHERE NOT EXISTS (
        SELECT 1 FROM user_security_roles ex
        WHERE ex.user_id = usr.user_id AND ex.role_id = target.id
    )
"""
_INSERT_PG = (
    "INSERT INTO user_security_roles (id, user_id, role_id, granted_at) "
    "SELECT gen_random_uuid(), usr.user_id, target.id, now()" + _SELECT
)
_INSERT_SQLITE = (
    "INSERT INTO user_security_roles (id, user_id, role_id, granted_at) "
    "SELECT lower("
    "substr(hex(randomblob(4)),1,8)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(6)),1,12)), usr.user_id, target.id, datetime('now')"
    + _SELECT
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if not {"security_roles", "user_security_roles"} <= tables:
        return  # a tenant database: roles live with the registry
    sql = _INSERT_PG if bind.dialect.name == "postgresql" else _INSERT_SQLITE
    op.execute(sa.text(sql).bindparams(role=_ROLE, from_role=_FROM_ROLE))


def downgrade() -> None:
    """Leave grants in place: q34's downgrade deletes the role (and these
    grants with it), and a grant an admin made by hand is indistinguishable
    from one made here."""
