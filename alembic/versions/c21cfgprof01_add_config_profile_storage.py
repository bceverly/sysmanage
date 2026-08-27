# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add config profile storage, versions and assignments (Phase 20.1).

Expand-only. Three new tables plus ONE new foreign key on an existing column.

That foreign key deserves a note. ``config_profile_run.profile_id`` has existed
since c20cfgrun01 as an unconstrained nullable GUID, precisely so run history
could be recorded before a profile table existed. Every row written so far has
a NULL there -- nothing could have set it -- so adding the constraint cannot
fail on existing data.

It is ``ON DELETE SET NULL`` rather than CASCADE on purpose: deleting a profile
must not erase the record that it ran. History outliving its subject is the
whole point of an audit trail, and a CASCADE here would quietly delete the
evidence of every change that profile ever made.

Revision ID: c21cfgprof01
Revises: c20cfgrun01
Create Date: 2026-08-27
"""

import sqlalchemy as sa
from alembic import op

from backend.persistence.models.core import GUID

# revision identifiers, used by Alembic.
revision = "c21cfgprof01"
down_revision = "c20cfgrun01"
branch_labels = None
depends_on = None

_RUN_PROFILE_FK = "fk_config_profile_run_profile_id"


def upgrade() -> None:
    """Create profile storage and link existing run history to it."""
    op.create_table(
        "config_profile",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_config_profile_name", "config_profile", ["name"])

    op.create_table(
        "config_profile_version",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            GUID(),
            sa.ForeignKey("config_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_config_profile_version_profile_id", "config_profile_version", ["profile_id"]
    )
    # One row per (profile, version) -- a duplicate makes "restore version 3"
    # ambiguous.
    op.create_index(
        "ix_config_profile_version_unique",
        "config_profile_version",
        ["profile_id", "version"],
        unique=True,
    )

    op.create_table(
        "config_profile_assignment",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            GUID(),
            sa.ForeignKey("config_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "tag_id",
            GUID(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "site_id",
            GUID(),
            sa.ForeignKey("federation_sites.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schedule", sa.String(100), nullable=True),
        sa.Column(
            "check_mode", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_applied_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_config_profile_assignment_profile_id",
        "config_profile_assignment",
        ["profile_id"],
    )
    op.create_index(
        "ix_config_profile_assignment_enabled",
        "config_profile_assignment",
        ["enabled", "profile_id"],
    )

    # SET NULL, never CASCADE: deleting a profile must not erase the record
    # that it ran. See the module docstring.
    op.create_foreign_key(
        _RUN_PROFILE_FK,
        "config_profile_run",
        "config_profile",
        ["profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Drop profile storage, leaving run history intact."""
    op.drop_constraint(_RUN_PROFILE_FK, "config_profile_run", type_="foreignkey")
    op.drop_index("ix_config_profile_assignment_enabled", "config_profile_assignment")
    op.drop_index(
        "ix_config_profile_assignment_profile_id", "config_profile_assignment"
    )
    op.drop_table("config_profile_assignment")
    op.drop_index("ix_config_profile_version_unique", "config_profile_version")
    op.drop_index("ix_config_profile_version_profile_id", "config_profile_version")
    op.drop_table("config_profile_version")
    op.drop_index("ix_config_profile_name", "config_profile")
    op.drop_table("config_profile")
