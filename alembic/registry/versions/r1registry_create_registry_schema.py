"""create_registry_schema

Phase 13.1.A: multi-tenancy control-plane ("registry") schema.

Creates the four ``registry_*`` control-plane tables — the source of
truth for which tenants exist, who may reach them, and where each
tenant's database lives:

  * registry_tenant            — the tenant (account)
  * registry_user              — global identity keyed by email
  * registry_user_tenant_grant — the email→tenant mapping (least-privilege core)
  * registry_tenant_placement  — per-tenant DB coordinates (NEVER credentials)

This is the ROOT of the **registry** Alembic chain — a separate
environment with its own version table (``alembic_version_registry``),
NOT a second head in the tenant chain.  Foreign keys here are
intra-partition (all four tables always share one database) and so are
allowed; no FK crosses a partition boundary.

Idempotent (re-runnable on a database that already has any subset of the
tables / indexes), and identical on SQLite (test) and PostgreSQL (prod) —
no dialect-specific types or DDL.

Revision ID: r1registry
Revises:
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r1registry"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _guid_type():
    """UUID-typed column for the live dialect (UUID on PG, String(36) else).

    Mirrors ``backend.persistence.models.core.GUID`` without importing it,
    since Alembic may run against a bare engine without the app package.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def _tables():
    """Registry table definitions in FK-dependency order.

    ``registry_tenant`` and ``registry_user`` come first because the grant
    and placement tables reference them.
    """
    guid = _guid_type()
    return [
        {
            "name": "registry_tenant",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("name", sa.String(255), nullable=False),
                sa.Column("slug", sa.String(100), nullable=False),
                sa.Column("status", sa.String(32), nullable=False),
                sa.Column("settings", sa.JSON(), nullable=True),
                sa.Column("limits", sa.JSON(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
            ],
            "unique_constraints": [
                ("uq_registry_tenant_slug", ["slug"]),
            ],
            "indexes": [
                ("ix_registry_tenant_slug", ["slug"]),
            ],
        },
        {
            "name": "registry_user",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("email", sa.String(255), nullable=False),
                sa.Column("password_hash", sa.String(255), nullable=True),
                sa.Column("is_active", sa.Boolean(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
            ],
            "unique_constraints": [
                ("uq_registry_user_email", ["email"]),
            ],
            "indexes": [
                ("ix_registry_user_email", ["email"]),
            ],
        },
        {
            "name": "registry_user_tenant_grant",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column(
                    "user_id",
                    guid,
                    sa.ForeignKey("registry_user.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column(
                    "tenant_id",
                    guid,
                    sa.ForeignKey("registry_tenant.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("role", sa.String(64), nullable=False),
                sa.Column("is_default", sa.Boolean(), nullable=False),
                sa.Column("expires_at", sa.DateTime(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
            ],
            "unique_constraints": [
                ("uq_registry_grant_user_tenant", ["user_id", "tenant_id"]),
            ],
            "indexes": [
                ("ix_registry_grant_user", ["user_id"]),
                ("ix_registry_grant_tenant", ["tenant_id"]),
            ],
        },
        {
            "name": "registry_tenant_placement",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column(
                    "tenant_id",
                    guid,
                    sa.ForeignKey("registry_tenant.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("host", sa.String(255), nullable=True),
                sa.Column("port", sa.Integer(), nullable=True),
                sa.Column("dbname", sa.String(255), nullable=True),
                sa.Column("region", sa.String(64), nullable=True),
                sa.Column("tier", sa.String(16), nullable=False),
                sa.Column("openbao_role", sa.String(255), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
            ],
            "unique_constraints": [
                ("uq_registry_placement_tenant", ["tenant_id"]),
            ],
            "indexes": [
                ("ix_registry_placement_tenant", ["tenant_id"]),
            ],
        },
    ]


def upgrade() -> None:
    """Create the registry tables + their indexes (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table_def in _tables():
        table_name = table_def["name"]
        if table_name not in existing_tables:
            uniques = [
                sa.UniqueConstraint(*cols, name=name)
                for name, cols in table_def["unique_constraints"]
            ]
            op.create_table(table_name, *table_def["columns"], *uniques)
            existing_tables.add(table_name)

        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        for index_name, index_cols in table_def["indexes"]:
            if index_name not in existing_indexes:
                op.create_index(index_name, table_name, list(index_cols), unique=False)


def downgrade() -> None:
    """Drop the registry tables in reverse FK-dependency order (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table_def in reversed(_tables()):
        table_name = table_def["name"]
        if table_name not in existing_tables:
            continue
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        for index_name, _ in table_def["indexes"]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name)
        op.drop_table(table_name)
