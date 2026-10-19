# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Grant a newly added security role to the people who already hold them all.

ROLE MIGRATIONS -- the rule for every migration that adds a role.
------------------------------------------------------------------
Granting a new role only to ``is_admin`` users silently locks it away from a
fully privileged operator whose admin flag happens to be off: on 2026-10-17
the production operator held 102 of 105 roles -- every role except the three
added by q38clockbound, q39clockresync and q42hwhealth, each granted with
``WHERE u.is_admin`` -- so the clock resync button was greyed out for the one
person meant to use it.  A migration that seeds a role calls
:func:`grant_new_role_to_full_holders` instead, which grants it to

* every ``is_admin`` user, and
* every user who already holds EVERY other role (the "full holders").

A partial holder is left alone: holding some roles says nothing about this
one.  SQLAlchemy Core on the migration's connection, so it imports no
application code; idempotent (``NOT EXISTS``) and portable (SQLite +
PostgreSQL).
``tests/test_role_migrations_grant_full_holders.py`` fails a new migration
that inserts into ``user_security_roles`` without it.
"""

from typing import Iterable, Optional

import sqlalchemy as sa

_UUID_SQLITE = (
    "lower(substr(hex(randomblob(4)),1,8)||'-'||substr(hex(randomblob(2)),1,4)"
    "||'-'||substr(hex(randomblob(2)),1,4)||'-'||substr(hex(randomblob(2)),1,4)"
    "||'-'||substr(hex(randomblob(6)),1,12))"
)

# Bare table shapes -- not the ORM models -- so a migration imports no
# application code and sees the schema as it is at that revision.
_USER = sa.table("user", sa.column("id"), sa.column("is_admin"))
_ROLES = sa.table("security_roles", sa.column("id"), sa.column("name"))
_GRANTS = sa.table(
    "user_security_roles",
    sa.column("id"),
    sa.column("user_id"),
    sa.column("role_id"),
    sa.column("granted_at"),
)


def _holds(user_id, role_id):
    # correlate_except: auto-correlation reaches only the enclosing query, and
    # this sits two levels below the outer user row in the full-holder test.
    grant = _GRANTS.alias()
    return (
        sa.exists()
        .where(grant.c.user_id == user_id, grant.c.role_id == role_id)
        .correlate_except(grant)
    )


def _grant_select(role_name: str, excluded, postgres: bool):
    """Admins and full holders of every role but ``excluded``, not yet
    holding ``role_name``: (new id, user id, role id, granted at)."""
    target, other, any_other = _ROLES.alias(), _ROLES.alias(), _ROLES.alias()
    if postgres:
        new_id, granted_at = sa.func.gen_random_uuid(), sa.func.now()
    else:
        # A constant expression (no input reaches it): SQLite has no uuid().
        new_id = sa.literal_column(_UUID_SQLITE)
        granted_at = sa.func.datetime("now")
    full_holder = sa.and_(
        # with no other roles yet, "holds every other role" is vacuous
        sa.exists().where(any_other.c.name.notin_(excluded)),
        ~sa.exists().where(
            other.c.name.notin_(excluded), ~_holds(_USER.c.id, other.c.id)
        ),
    )
    return (
        sa.select(new_id, _USER.c.id, target.c.id, granted_at)
        .select_from(_USER.join(target, target.c.name == role_name))
        .where(
            ~_holds(_USER.c.id, target.c.id),
            sa.or_(_USER.c.is_admin == sa.true(), full_holder),
        )
    )


def grant_new_role_to_full_holders(
    conn, role_name: str, new_roles: Optional[Iterable[str]] = None
) -> int:
    """Grant ``role_name`` to admins and full holders; returns rows added.

    ``new_roles`` names every role being introduced together (default: just
    ``role_name``) -- none of them is required to count as a full holder.  The
    "must hold every other role" test only applies when other roles exist, so
    a database with no roles yet grants to admins only.
    """
    excluded = sorted(set(new_roles or ()) | {role_name})
    select = _grant_select(role_name, excluded, conn.dialect.name == "postgresql")
    statement = _GRANTS.insert().from_select(
        ["id", "user_id", "role_id", "granted_at"], select
    )
    result = conn.execute(statement)
    return result.rowcount or 0
