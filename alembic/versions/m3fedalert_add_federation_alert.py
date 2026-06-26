"""Add federation_alert table (Phase 12.1 — rollup alerting).

Records enterprise-wide alerts fired on cross-site rollup conditions
(a site going offline, a site's compliance score dropping below a
threshold, a site's critical-CVE count crossing a threshold).  These
are SITE-scoped, so they can't live in the host-scoped ``alert`` table
(``alert.host_id`` is NOT NULL); a dedicated additive table keeps the
migration a pure ``CREATE TABLE`` — idempotent and identical on SQLite
and PostgreSQL, with no fragile ``ALTER COLUMN`` / batch rebuild.

Revision ID: m3fedalert
Revises: b1airgapdev
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m3fedalert"
down_revision: Union[str, None] = "b1airgapdev"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "federation_alert"


def _guid_type():
    """UUID-typed column for the live dialect (Postgres UUID / String(36)).

    Mirrors ``backend.persistence.models.core.GUID`` without importing the
    app package (Alembic runs against a bare engine).
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def _indexes():
    return [
        ("ix_federation_alert_site_id", ["site_id"]),
        ("ix_federation_alert_resolved", ["resolved"]),
    ]


def upgrade() -> None:
    """Create ``federation_alert`` + its indexes.  Idempotent: skips the
    table / each index if it already exists from a prior partial run."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    guid = _guid_type()

    if _TABLE not in set(inspector.get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "site_id",
                guid,
                sa.ForeignKey("federation_sites.id", ondelete="CASCADE"),
                nullable=False,
            ),
            # site_offline | compliance_below | vulnerabilities_high
            sa.Column("condition", sa.String(64), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=True),
            sa.Column("triggered_at", sa.DateTime(), nullable=False),
            sa.Column(
                "resolved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column(
                "acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for index_name, index_cols in _indexes():
        if index_name not in existing_indexes:
            op.create_index(index_name, _TABLE, list(index_cols))


def downgrade() -> None:
    """Drop ``federation_alert`` (+ indexes) if present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for index_name, _cols in _indexes():
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=_TABLE)
    op.drop_table(_TABLE)
