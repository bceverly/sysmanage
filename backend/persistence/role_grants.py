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
one.  Plain SQL on the migration's connection, so it imports no application
code; idempotent (``NOT EXISTS``) and portable (SQLite + PostgreSQL).
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

# :role is the role granted; :new are the roles that do not count when deciding
# whether someone is a full holder (always at least :role itself).
_SELECT = """
    FROM "user" u
    JOIN security_roles target ON target.name = :role
    WHERE NOT EXISTS (
        SELECT 1 FROM user_security_roles ex
        WHERE ex.user_id = u.id AND ex.role_id = target.id
    )
    AND (
        u.is_admin = :yes
        OR (
            EXISTS (SELECT 1 FROM security_roles r0 WHERE r0.name NOT IN :new)
            AND NOT EXISTS (
                SELECT 1 FROM security_roles r
                WHERE r.name NOT IN :new AND NOT EXISTS (
                    SELECT 1 FROM user_security_roles held
                    WHERE held.user_id = u.id AND held.role_id = r.id
                )
            )
        )
    )
"""


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
    postgres = conn.dialect.name == "postgresql"
    columns = (
        "gen_random_uuid(), u.id, target.id, now()"
        if postgres
        else f"{_UUID_SQLITE}, u.id, target.id, datetime('now')"
    )
    statement = sa.text(
        "INSERT INTO user_security_roles (id, user_id, role_id, granted_at) "
        f"SELECT {columns}" + _SELECT
    ).bindparams(sa.bindparam("new", expanding=True))
    result = conn.execute(statement, {"role": role_name, "yes": True, "new": excluded})
    return result.rowcount or 0
