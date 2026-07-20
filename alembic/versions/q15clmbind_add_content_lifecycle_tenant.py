# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create content-lifecycle promotion state (tenant partition) — Phase 16

Per-tenant promotion state: which content-view version is bound into which
environment, the audit trail, and per-site environment subscriptions.  All
references to the SHARED catalog IDs (environment / content view / version /
site) are SOFT — NO ForeignKey (cross-partition), matching
``host_applicable_advisory``.

Part of the TENANT chain (unprefixed tables), chained off the tenant head
``r2fipsmode`` — SEPARATE from the shared CLM migration (``s10clmviews``), which
lives in the shared chain.  The partition guard (test_alembic_prefix_guard)
enforces that the tenant chain never creates ``shared_``/``registry_`` tables.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q15clmbind
Revises: r2fipsmode
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "q15clmbind"
down_revision: Union[str, None] = "r2fipsmode"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_BINDING = "environment_content_binding"
_AUDIT = "content_promotion_audit"
_SUB = "environment_site_subscription"
_TABLES = (_AUDIT, _SUB, _BINDING)


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if not insp.has_table(_BINDING):
        op.create_table(
            _BINDING,
            sa.Column("id", GUID(), primary_key=True),
            # SOFT cross-partition refs to shared IDs — no FK.
            sa.Column("environment_id", GUID(), nullable=False),
            sa.Column("content_view_id", GUID(), nullable=False),
            sa.Column("content_view_version_id", GUID(), nullable=False),
            sa.Column("previous_version_id", GUID(), nullable=True),
            sa.Column("promoted_at", sa.DateTime(), nullable=False),
            sa.Column("promoted_by", GUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "environment_id", "content_view_id", name="uq_env_content_binding"
            ),
        )
        op.create_index(
            "ix_%s_environment_id" % _BINDING, _BINDING, ["environment_id"]
        )
        op.create_index(
            "ix_%s_content_view_id" % _BINDING, _BINDING, ["content_view_id"]
        )

    if not insp.has_table(_AUDIT):
        op.create_table(
            _AUDIT,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("content_view_id", GUID(), nullable=False),
            sa.Column("from_environment_id", GUID(), nullable=True),
            sa.Column("to_environment_id", GUID(), nullable=True),
            sa.Column("content_view_version_id", GUID(), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.Column("actor", GUID(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_%s_content_view_id" % _AUDIT, _AUDIT, ["content_view_id"]
        )
        op.create_index("ix_%s_action" % _AUDIT, _AUDIT, ["action"])
        op.create_index("ix_%s_at" % _AUDIT, _AUDIT, ["at"])

    if not insp.has_table(_SUB):
        op.create_table(
            _SUB,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("environment_id", GUID(), nullable=False),
            sa.Column("site_id", GUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "environment_id", "site_id", name="uq_env_site_subscription"
            ),
        )
        op.create_index(
            "ix_%s_environment_id" % _SUB, _SUB, ["environment_id"]
        )
        op.create_index("ix_%s_site_id" % _SUB, _SUB, ["site_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    for table in _TABLES:
        if insp.has_table(table):
            op.drop_table(table)
