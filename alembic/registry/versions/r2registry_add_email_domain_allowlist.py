# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_email_domain_allowlist

Phase 13.1.B: per-tenant email-domain allowlist.

Adds ``registry_tenant_email_domain`` — the per-tenant allowlist of email
domains permitted to join the tenant (enforced at grant/provisioning
time, design §10).  An empty allowlist for a tenant means "no domain
restriction".

Second migration in the **registry** chain (chains off ``r1registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod); no
cross-partition FK (the one FK targets ``registry_tenant``, same
partition).

Revision ID: r2registry
Revises: r1registry
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r2registry"
down_revision: Union[str, None] = "r1registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_tenant_email_domain"


def _guid_type():
    """UUID-typed column for the live dialect (UUID on PG, String(36) else)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    """Create the email-domain allowlist table + indexes (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    guid = _guid_type()

    if _TABLE not in existing_tables:
        op.create_table(
            _TABLE,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "tenant_id",
                guid,
                sa.ForeignKey("registry_tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("domain", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "tenant_id", "domain", name="uq_registry_email_domain_tenant_domain"
            ),
        )

    # Re-inspect so the index check sees a table that was just created.
    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if "ix_registry_email_domain_tenant" not in existing_indexes:
        op.create_index(
            "ix_registry_email_domain_tenant", _TABLE, ["tenant_id"], unique=False
        )


def downgrade() -> None:
    """Drop the email-domain allowlist table (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if "ix_registry_email_domain_tenant" in existing_indexes:
        op.drop_index("ix_registry_email_domain_tenant", table_name=_TABLE)
    op.drop_table(_TABLE)
