"""create gpg_key + gpg_key_assignment and seed 'Manage GPG Keys' role

GPG Key Management (Slice 1 — server-side foundation).

* ``gpg_key`` stores metadata for a named GPG key; the armored material lives
  in the OpenBAO vault, referenced by ``openbao_secret_id`` (NEVER in the DB).
* ``gpg_key_assignment`` assigns a key to a host (``target_username`` NULL) or
  to a specific user account on that host (``target_username`` set).
* Seeds the ``Manage GPG Keys`` security role in the Secrets group.

Tenant-partition tables: names are UNPREFIXED (no registry_/shared_ prefix).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: m1gpgkeys
Revises: l1logcfg
"""

import uuid
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "m1gpgkeys"
down_revision: Union[str, None] = "l1logcfg"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_GPG_KEY = "gpg_key"
_GPG_KEY_ASSIGNMENT = "gpg_key_assignment"

_ROLE_NAME = "Manage GPG Keys"
_SECRETS_GROUP_ID = "00000000-0000-0000-0000-000000000003"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table(_GPG_KEY):
        op.create_table(
            _GPG_KEY,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("fingerprint", sa.String(length=255), nullable=True),
            sa.Column("key_type", sa.String(length=20), nullable=False),
            sa.Column(
                "has_private",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("openbao_secret_id", sa.String(length=500), nullable=False),
            sa.Column("uploaded_by", GUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("name", name="uq_gpg_key_name"),
        )
        op.create_index("ix_gpg_key_name", _GPG_KEY, ["name"])
        op.create_index("ix_gpg_key_fingerprint", _GPG_KEY, ["fingerprint"])

    if not insp.has_table(_GPG_KEY_ASSIGNMENT):
        op.create_table(
            _GPG_KEY_ASSIGNMENT,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("gpg_key_id", GUID(), nullable=False),
            sa.Column("host_id", GUID(), nullable=False),
            sa.Column("target_username", sa.String(length=255), nullable=True),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("assigned_by", GUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["gpg_key_id"], ["gpg_key.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["host_id"], ["host.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_gpg_key_assignment_gpg_key_id",
            _GPG_KEY_ASSIGNMENT,
            ["gpg_key_id"],
        )
        op.create_index(
            "ix_gpg_key_assignment_host_id", _GPG_KEY_ASSIGNMENT, ["host_id"]
        )

    _seed_role(bind)


def _seed_role(bind) -> None:
    """Idempotently seed the 'Manage GPG Keys' role (Secrets group)."""
    insp = inspect(bind)
    if "security_roles" not in insp.get_table_names():
        return

    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM security_roles WHERE name = :name"),
        {"name": _ROLE_NAME},
    ).scalar()
    if existing:
        return

    # ``id``/``group_id`` are uuid columns on PostgreSQL, plain TEXT on SQLite.
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
            description="Manage GPG keys and their host/user assignments",
            group_id=_SECRETS_GROUP_ID,
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "security_roles" in insp.get_table_names():
        op.execute(
            sa.text("DELETE FROM security_roles WHERE name = :name").bindparams(
                name=_ROLE_NAME
            )
        )

    # Drop assignment first (it FKs the key table).
    if insp.has_table(_GPG_KEY_ASSIGNMENT):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_GPG_KEY_ASSIGNMENT)
    if insp.has_table(_GPG_KEY):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_GPG_KEY)
