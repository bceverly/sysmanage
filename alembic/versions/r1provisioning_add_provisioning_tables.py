# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add provisioning tables (compute_resource, provisioning_template, provisioning_job) — Phase 18.1

Three tables backing the Pro+ ``provisioning_engine`` (net-new host
provisioning).  Per-tenant operational data, so they live in the TENANT
partition (the single shared DB when multi-tenancy is off), like the 8.7
report tables:

  compute_resource        a configured compute backend (provider endpoint)
  provisioning_template   operator-authored, versioned provisioning artifacts
  provisioning_job        a provision request + its lifecycle state

The OSS server owns the schema so non-Pro+ deployments don't crash on unknown
tables; the Enterprise-gated engine reads/writes them at request time.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r1provisioning
Revises: q20imagemode
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "r1provisioning"
down_revision: Union[str, None] = "q20imagemode"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if not insp.has_table("compute_resource"):
        op.create_table(
            "compute_resource",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column("kind", sa.String(length=50), nullable=False),
            sa.Column("connection_uri", sa.String(length=500), nullable=False),
            sa.Column("credential_ref", sa.String(length=500), nullable=True),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_compute_resource_kind", "compute_resource", ["kind"])

    if not insp.has_table("provisioning_template"):
        op.create_table(
            "provisioning_template",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column("kind", sa.String(length=50), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("params", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_provisioning_template_kind", "provisioning_template", ["kind"]
        )

    if not insp.has_table("provisioning_job"):
        op.create_table(
            "provisioning_job",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column(
                "compute_resource_id",
                sa.UUID(),
                sa.ForeignKey("compute_resource.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "template_id",
                sa.UUID(),
                sa.ForeignKey("provisioning_template.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("target_name", sa.String(length=255), nullable=False),
            sa.Column(
                "state",
                sa.String(length=30),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("provider_id", sa.String(length=255), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_provisioning_job_compute_resource_id",
            "provisioning_job",
            ["compute_resource_id"],
        )
        op.create_index("ix_provisioning_job_state", "provisioning_job", ["state"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table("provisioning_job"):
        op.drop_index("ix_provisioning_job_state", table_name="provisioning_job")
        op.drop_index(
            "ix_provisioning_job_compute_resource_id",
            table_name="provisioning_job",
        )
        op.drop_table("provisioning_job")
    if insp.has_table("provisioning_template"):
        op.drop_index(
            "ix_provisioning_template_kind", table_name="provisioning_template"
        )
        op.drop_table("provisioning_template")
    if insp.has_table("compute_resource"):
        op.drop_index("ix_compute_resource_kind", table_name="compute_resource")
        op.drop_table("compute_resource")
