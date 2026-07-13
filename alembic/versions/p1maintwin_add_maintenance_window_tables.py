"""create maintenance-window tables (Phase 14.2 — maintenance windows)

Operator-defined change windows: update installs / remote commands only reach
agents inside allowed windows, with blackout windows and time-boxed emergency
overrides (audited).  Per-tenant operational policy → **tenant** partition, so
the table names are UNPREFIXED (no registry_/shared_ prefix).  Scope + override
rows soft-reference ``host.id`` / ``tags.id`` (same partition) via plain indexed
GUID columns — no hard FK, keeping this migration order-independent + idempotent.

* ``maintenance_window`` — a window: name, kind (allow|blackout), recurrence
  (once|daily|weekly) + IANA timezone; recurring uses local start_time +
  duration_minutes (+ days_of_week for weekly); one-off uses starts_at/ends_at.
* ``maintenance_window_scope`` — what a window applies to (all|host|tag).
* ``maintenance_override`` — time-boxed emergency override for one host.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: p1maintwin
Revises: o1logremote
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "p1maintwin"
down_revision: Union[str, None] = "o1logremote"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_WINDOW = "maintenance_window"
_SCOPE = "maintenance_window_scope"
_OVERRIDE = "maintenance_override"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table(_WINDOW):
        op.create_table(
            _WINDOW,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "kind", sa.String(length=10), nullable=False, server_default="allow"
            ),
            sa.Column(
                "recurrence",
                sa.String(length=10),
                nullable=False,
                server_default="daily",
            ),
            sa.Column(
                "timezone",
                sa.String(length=64),
                nullable=False,
                server_default="UTC",
            ),
            sa.Column("start_time", sa.String(length=5), nullable=True),
            sa.Column("duration_minutes", sa.Integer(), nullable=True),
            sa.Column("days_of_week", sa.String(length=32), nullable=True),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", GUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if not insp.has_table(_SCOPE):
        op.create_table(
            _SCOPE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("window_id", GUID(), nullable=False),
            sa.Column("scope_type", sa.String(length=10), nullable=False),
            sa.Column("host_id", GUID(), nullable=True),
            sa.Column("tag_id", GUID(), nullable=True),
        )
        op.create_index("ix_mw_scope_window_id", _SCOPE, ["window_id"])
        op.create_index("ix_mw_scope_host_id", _SCOPE, ["host_id"])
        op.create_index("ix_mw_scope_tag_id", _SCOPE, ["tag_id"])

    if not insp.has_table(_OVERRIDE):
        op.create_table(
            _OVERRIDE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("host_id", GUID(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_by", GUID(), nullable=True),
            sa.Column("username", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mw_override_host_id", _OVERRIDE, ["host_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    # expand-contract-ok: reverse of this revision's create_table set.
    for table in (_OVERRIDE, _SCOPE, _WINDOW):
        if insp.has_table(table):
            op.drop_table(table)
