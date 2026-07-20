# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create content-lifecycle shared catalog (shared partition) — Phase 16

Lifecycle environments + content views + versions are platform truth, identical
across tenants, so they live in the SHARED partition (``shared_*`` prefix).
Intra-shared FKs (a version/filter/repo -> its content view) are real; the only
cross-partition reference (``shared_content_view_repo.mirror_id`` ->
``mirror_repository``) is SOFT (no ForeignKey), matching the advisory precedent.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s10clmviews
Revises: s4oslifecycle
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "s10clmviews"
down_revision: Union[str, None] = "s4oslifecycle"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_ENV = "shared_lifecycle_environment"
_CV = "shared_content_view"
_REPO = "shared_content_view_repo"
_FILTER = "shared_content_view_filter"
_VERSION = "shared_content_view_version"
_TABLES = (_VERSION, _FILTER, _REPO, _CV, _ENV)  # drop order (children first)


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if not insp.has_table(_ENV):
        op.create_table(
            _ENV,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "is_library", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("name", name="uq_shared_lifecycle_env_name"),
            sa.UniqueConstraint("position", name="uq_shared_lifecycle_env_position"),
        )
        op.create_index("ix_%s_name" % _ENV, _ENV, ["name"])

    if not insp.has_table(_CV):
        op.create_table(
            _CV,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "composite", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "keep_versions", sa.Integer(), nullable=False, server_default="5"
            ),
            sa.Column("created_by", GUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("name", name="uq_shared_content_view_name"),
        )
        op.create_index("ix_%s_name" % _CV, _CV, ["name"])

    if not insp.has_table(_REPO):
        op.create_table(
            _REPO,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("content_view_id", GUID(), nullable=False),
            # SOFT ref to mirror_repository.id (tenant partition) — no FK.
            sa.Column("mirror_id", GUID(), nullable=True),
            sa.Column("component_content_view_id", GUID(), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["content_view_id"], ["%s.id" % _CV], ondelete="CASCADE"
            ),
        )
        op.create_index("ix_%s_content_view_id" % _REPO, _REPO, ["content_view_id"])
        op.create_index("ix_%s_mirror_id" % _REPO, _REPO, ["mirror_id"])

    if not insp.has_table(_FILTER):
        op.create_table(
            _FILTER,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("content_view_id", GUID(), nullable=False),
            sa.Column("filter_type", sa.String(length=30), nullable=False),
            sa.Column("rule_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["content_view_id"], ["%s.id" % _CV], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_%s_content_view_id" % _FILTER, _FILTER, ["content_view_id"]
        )
        op.create_index("ix_%s_filter_type" % _FILTER, _FILTER, ["filter_type"])

    if not insp.has_table(_VERSION):
        op.create_table(
            _VERSION,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("content_view_id", GUID(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="draft"
            ),
            sa.Column("store_path", sa.String(length=500), nullable=True),
            sa.Column("manifest", sa.JSON(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("published_by", GUID(), nullable=True),
            sa.Column("publish_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["content_view_id"], ["%s.id" % _CV], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "content_view_id", "version", name="uq_shared_cvv_cv_version"
            ),
        )
        op.create_index(
            "ix_%s_content_view_id" % _VERSION, _VERSION, ["content_view_id"]
        )
        op.create_index("ix_%s_status" % _VERSION, _VERSION, ["status"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    for table in _TABLES:
        if insp.has_table(table):
            op.drop_table(table)
