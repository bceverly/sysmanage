# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add threat_model, posture_item, posture_item_event, posture_waiver (Phase 21.4 S2)

Tenant data: the derived threat model (versioned), the posture punch list,
its change history and the audited waivers. The questionnaire and the rules
are soft references into the shared catalog (no cross-partition FK).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q11posture
Revises: q10advisorpack
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q11posture"
down_revision: Union[str, None] = "q10advisorpack"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _scope():
    return [
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_ref", sa.String(length=64), nullable=False),
    ]


def _threat_model():
    op.create_table(
        "threat_model",
        sa.Column("id", GUID(), primary_key=True),
        *_scope(),
        sa.Column("model_version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("questionnaire_slug", sa.String(length=128), nullable=False),
        sa.Column("questionnaire_version", sa.Integer(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=True),
        sa.Column("ignored", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "scope_kind", "scope_ref", "model_version", name="uq_threat_model_version"
        ),
    )
    op.create_index(
        "ix_threat_model_current",
        "threat_model",
        ["scope_kind", "scope_ref", "is_current"],
    )


def _posture_item():
    op.create_table(
        "posture_item",
        sa.Column("id", GUID(), primary_key=True),
        *_scope(),
        sa.Column("rule_source", sa.String(length=16), nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=True),
        sa.Column("threat_model_id", GUID(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("managed_by", sa.String(length=16), nullable=False),
        sa.Column("impact", sa.Integer(), nullable=True),
        sa.Column("likelihood", sa.Integer(), nullable=True),
        sa.Column("risk", sa.Integer(), nullable=True),
        sa.Column("gaps", sa.JSON(), nullable=True),
        sa.Column("coverage", sa.JSON(), nullable=True),
        sa.Column("matches", sa.JSON(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("state_changed_at", sa.DateTime(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "scope_kind", "scope_ref", "rule_key", name="uq_posture_item_rule"
        ),
    )
    op.create_index(
        "ix_posture_item_state", "posture_item", ["scope_kind", "scope_ref", "state"]
    )
    op.create_index(
        "ix_posture_item_threat_model_id", "posture_item", ["threat_model_id"]
    )


def _posture_item_event():
    op.create_table(
        "posture_item_event",
        sa.Column("id", GUID(), primary_key=True),
        *_scope(),
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        sa.Column("from_state", sa.String(length=16), nullable=True),
        sa.Column("to_state", sa.String(length=16), nullable=True),
        sa.Column("cause", sa.String(length=32), nullable=False),
        sa.Column("threat_model_version", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_posture_item_event_rule",
        "posture_item_event",
        ["scope_kind", "scope_ref", "rule_key", "at"],
    )
    op.create_index("ix_posture_item_event_at", "posture_item_event", ["at"])


def _posture_waiver():
    op.create_table(
        "posture_waiver",
        sa.Column("id", GUID(), primary_key=True),
        *_scope(),
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=True),
        sa.Column("risk", sa.Integer(), nullable=True),
        sa.Column("basis_attributes", sa.JSON(), nullable=True),
        sa.Column("threat_model_version", sa.Integer(), nullable=True),
        sa.Column("granted_by", sa.String(length=255), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("reaffirmed_by", sa.String(length=255), nullable=True),
        sa.Column("reaffirmed_at", sa.DateTime(), nullable=True),
        sa.Column("stale_reason", sa.String(length=64), nullable=True),
        sa.Column("stale_since", sa.DateTime(), nullable=True),
        sa.Column("revoked_by", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_posture_waiver_active",
        "posture_waiver",
        ["scope_kind", "scope_ref", "rule_key", "revoked_at"],
    )


_TABLES = {
    "threat_model": _threat_model,
    "posture_item": _posture_item,
    "posture_item_event": _posture_item_event,
    "posture_waiver": _posture_waiver,
}


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    for table, create in _TABLES.items():
        if table not in existing:
            create()


def downgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    for table in reversed(list(_TABLES)):
        if table in existing:
            op.drop_table(table)
