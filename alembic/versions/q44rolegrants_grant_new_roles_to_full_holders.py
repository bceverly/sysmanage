# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""grant the q38/q39/q42 roles to users who hold every other role

q38clockbound, q39clockresync and q42hwhealth each seeded a role and granted
it only to ``is_admin`` users.  An operator holding every other role but with
the admin flag off never got them: production on 2026-10-17 held 102 of 105
roles, missing exactly these three, so the clock resync button was greyed
out.  This grants them to every user who holds all roles apart from these
three, plus every admin (already granted, so a no-op for them).  Future role
migrations use ``backend.persistence.role_grants`` instead.

Grant-only and idempotent; a partial holder is left alone.  Downgrade does
nothing: these grants cannot be told apart from ones an operator made since.

Revision ID: q44rolegrants
Revises: q43hwtools
"""

from typing import Union

from sqlalchemy import inspect

from alembic import op
from backend.persistence.role_grants import grant_new_role_to_full_holders

revision: str = "q44rolegrants"
down_revision: Union[str, None] = "q43hwtools"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

# Every role a migration granted to is_admin users only.
_ADMIN_ONLY_ROLES = (
    "Manage Time Sync",  # q38clockbound
    "Resync Host Clock",  # q39clockresync
    "Manage Hardware Health",  # q42hwhealth
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if not {"security_roles", "user_security_roles", "user"} <= tables:
        return  # a tenant database: roles live with the registry
    for role in _ADMIN_ONLY_ROLES:
        grant_new_role_to_full_holders(bind, role, new_roles=_ADMIN_ONLY_ROLES)


def downgrade() -> None:
    """Nothing to undo safely (see the module docstring)."""
