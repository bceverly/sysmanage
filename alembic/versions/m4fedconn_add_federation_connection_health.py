# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add federation connection-health + site-metadata columns and sync-event series.

Phase 12.2 site-engine work:

* ``federation_coordinator`` gains site-side uplink health
  (``last_successful_sync_at``, ``consecutive_sync_failures``,
  ``connection_state``, ``next_reconnect_at``) so the site can classify
  its own connection, run in local autonomy mode when offline, and back
  off / auto-reconnect rather than hammer a hard-down coordinator.
* ``federation_sites`` gains the latest site-reported metadata
  (``sysmanage_version``, ``connection_state``, ``capabilities_json``,
  ``last_metadata_at``) the coordinator caches from each site's
  ``site_metadata`` sync payload.
* New ``federation_site_sync_event`` time-series feeds the per-site
  sync-status timeline (latency / queue-depth / host-count over time).

All operations are additive and guarded by inspector checks, so the
migration is idempotent and identical on SQLite and PostgreSQL — every
new column carries a ``server_default`` so the ADD COLUMN succeeds on a
populated table without a batch rebuild.

Revision ID: m4fedconn
Revises: m3fedalert
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m4fedconn"
down_revision: Union[str, None] = "m3fedalert"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EVENT_TABLE = "federation_site_sync_event"


def _guid_type():
    """UUID-typed column for the live dialect (Postgres UUID / String(36))."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


# (table, column, sqlalchemy type, server_default-or-None)
_COLUMNS = [
    ("federation_coordinator", "last_successful_sync_at", sa.DateTime(), None),
    (
        "federation_coordinator",
        "consecutive_sync_failures",
        sa.Integer(),
        sa.text("0"),
    ),
    (
        "federation_coordinator",
        "connection_state",
        sa.String(16),
        sa.text("'unknown'"),
    ),
    ("federation_coordinator", "next_reconnect_at", sa.DateTime(), None),
    ("federation_sites", "sysmanage_version", sa.String(32), None),
    ("federation_sites", "connection_state", sa.String(16), None),
    ("federation_sites", "capabilities_json", sa.Text(), None),
    ("federation_sites", "last_metadata_at", sa.DateTime(), None),
]


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    guid = _guid_type()

    for table, column, coltype, default in _COLUMNS:
        if _has_column(inspector, table, column):
            continue
        # NOT NULL columns supply a server_default so ADD COLUMN works on a
        # populated table; nullable columns add cleanly with no default.
        nullable = default is None
        op.add_column(
            table,
            sa.Column(
                column,
                coltype,
                nullable=nullable,
                server_default=default,
            ),
        )

    if _EVENT_TABLE not in set(inspector.get_table_names()):
        op.create_table(
            _EVENT_TABLE,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "site_id",
                guid,
                sa.ForeignKey("federation_sites.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("recorded_at", sa.DateTime(), nullable=False),
            sa.Column("sync_status", sa.String(32), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("queue_depth", sa.Integer(), nullable=True),
            sa.Column("host_count", sa.Integer(), nullable=True),
        )

    inspector = sa.inspect(bind)
    if _EVENT_TABLE in set(inspector.get_table_names()):
        existing = {idx["name"] for idx in inspector.get_indexes(_EVENT_TABLE)}
        if "ix_federation_site_sync_event_site_id" not in existing:
            op.create_index(
                "ix_federation_site_sync_event_site_id",
                _EVENT_TABLE,
                ["site_id"],
            )
        if "ix_federation_site_sync_event_site_recorded" not in existing:
            op.create_index(
                "ix_federation_site_sync_event_site_recorded",
                _EVENT_TABLE,
                ["site_id", "recorded_at"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _EVENT_TABLE in set(inspector.get_table_names()):
        existing = {idx["name"] for idx in inspector.get_indexes(_EVENT_TABLE)}
        for index_name in (
            "ix_federation_site_sync_event_site_recorded",
            "ix_federation_site_sync_event_site_id",
        ):
            if index_name in existing:
                op.drop_index(index_name, table_name=_EVENT_TABLE)
        op.drop_table(_EVENT_TABLE)

    for table, column, _coltype, _default in reversed(_COLUMNS):
        if _has_column(inspector, table, column):
            op.drop_column(table, column)
