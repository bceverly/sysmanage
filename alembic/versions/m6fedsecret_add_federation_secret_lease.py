# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add federation secret-lease tables (Phase 12.5 — federation-aware leases).

Coordinator-side ``federation_secret_lease`` tracks dynamic-secret leases
the coordinator issues from its master Vault on behalf of hosts at
subordinate sites; site-side ``federation_received_secret_lease`` is the
inbox for the result echo.  Pure additive ``CREATE TABLE`` — idempotent and
identical on SQLite and PostgreSQL.

Revision ID: m6fedsecret
Revises: m5fedalertcfg
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m6fedsecret"
down_revision: Union[str, None] = "m5fedalertcfg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEASE = "federation_secret_lease"
_RECEIVED = "federation_received_secret_lease"


def _guid_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def _create_index_if_absent(inspector, table, name, cols):
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, cols)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    guid = _guid_type()
    tables = set(inspector.get_table_names())

    if _LEASE not in tables:
        op.create_table(
            _LEASE,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "site_id",
                guid,
                sa.ForeignKey("federation_sites.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("host_id", sa.String(255), nullable=False),
            sa.Column("secret_name", sa.String(255), nullable=False),
            sa.Column("backend_role", sa.String(255), nullable=False),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("vault_lease_id", sa.String(500), nullable=True),
            sa.Column("ttl_seconds", sa.Integer(), nullable=True),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("issued_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("last_renewed_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("correlation_key", sa.String(64), nullable=True),
            sa.Column("secret_metadata_json", sa.Text(), nullable=True),
        )

    if _RECEIVED not in tables:
        op.create_table(
            _RECEIVED,
            sa.Column("id", guid, primary_key=True),
            sa.Column("correlation_key", sa.String(64), nullable=False),
            sa.Column("host_id", sa.String(255), nullable=False),
            sa.Column("secret_name", sa.String(255), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("secret_metadata_json", sa.Text(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("delivered_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
        )

    inspector = sa.inspect(bind)
    if _LEASE in set(inspector.get_table_names()):
        _create_index_if_absent(
            inspector, _LEASE, "ix_federation_secret_lease_site_id", ["site_id"]
        )
        _create_index_if_absent(
            inspector,
            _LEASE,
            "ix_federation_secret_lease_vault_lease_id",
            ["vault_lease_id"],
        )
        _create_index_if_absent(
            inspector,
            _LEASE,
            "ix_federation_secret_lease_expires_at",
            ["expires_at"],
        )
        _create_index_if_absent(
            inspector,
            _LEASE,
            "ix_federation_secret_lease_correlation_key",
            ["correlation_key"],
        )
        _create_index_if_absent(
            inspector,
            _LEASE,
            "ix_federation_secret_lease_site_status",
            ["site_id", "status"],
        )
    if _RECEIVED in set(inspector.get_table_names()):
        _create_index_if_absent(
            inspector,
            _RECEIVED,
            "ix_federation_received_secret_lease_correlation_key",
            ["correlation_key"],
        )
        _create_index_if_absent(
            inspector,
            _RECEIVED,
            "ix_federation_received_secret_lease_delivered",
            ["delivered_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if _RECEIVED in tables:
        op.drop_table(_RECEIVED)
    if _LEASE in tables:
        op.drop_table(_LEASE)
