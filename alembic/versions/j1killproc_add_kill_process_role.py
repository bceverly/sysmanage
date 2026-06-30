"""add 'Kill Host Process' security role (Phase 13.3 — Process Management)

Seeds the new Host-group security role used to gate terminating a process on a
managed host.  Idempotent: only inserts when a role with that name is absent.
The primary key is a freshly generated UUID (not a hardcoded sequential id) so
it can never collide with a role added by another migration.
Safe on SQLite + PostgreSQL.

Revision ID: j1killproc
Revises: i1hostproc
"""

import uuid
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "j1killproc"
down_revision: Union[str, None] = "i1hostproc"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_ROLE_NAME = "Kill Host Process"
_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Nothing to do if the roles table hasn't been created yet.
    if "security_roles" not in inspector.get_table_names():
        return

    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM security_roles WHERE name = :name"),
        {"name": _ROLE_NAME},
    ).scalar()
    if existing:
        return

    # ``id``/``group_id`` are uuid columns on PostgreSQL, plain TEXT on SQLite.
    # Use ``CAST(:p AS uuid)`` on PG (a bare ``:p::uuid`` would break text()'s
    # bind-param parser — ``:id`` immediately followed by ``:`` isn't matched).
    is_sqlite = bind.dialect.name == "sqlite"
    id_ph = ":id" if is_sqlite else "CAST(:id AS uuid)"
    gid_ph = ":group_id" if is_sqlite else "CAST(:group_id AS uuid)"
    op.execute(
        sa.text(
            "INSERT INTO security_roles (id, name, description, group_id) "
            f"VALUES ({id_ph}, :name, :description, {gid_ph})"
        ).bindparams(
            id=str(uuid.uuid4()),
            name=_ROLE_NAME,
            description="Terminate processes on hosts",
            group_id=_HOST_GROUP_ID,
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "security_roles" not in inspector.get_table_names():
        return
    op.execute(
        sa.text("DELETE FROM security_roles WHERE name = :name").bindparams(
            name=_ROLE_NAME
        )
    )
