# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add install_source + host_install_assignment — Phase 18.2 S3

The OS install-source catalog (os_family/version/arch -> kernel/initrd/install
tree/answer-file dialect) and the per-MAC assignment the per-MAC iPXE endpoint
resolves at boot.  Together these are what make per-machine OS choice a
first-class thing rather than an emergent side effect.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r6installsrc
Revises: r5provreadiness
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "r6installsrc"
down_revision: Union[str, None] = "r5provreadiness"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_SOURCE = "install_source"
_ASSIGNMENT = "host_install_assignment"


def _create_install_source(insp) -> None:
    if insp.has_table(_SOURCE):
        return
    op.create_table(
        _SOURCE,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("os_family", sa.String(length=40), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("arch", sa.String(length=20), nullable=False),
        # Nullable: FreeBSD netboots pxeboot + mfsroot, not kernel+initrd.
        sa.Column("kernel_path", sa.String(length=500), nullable=False),
        sa.Column("initrd_path", sa.String(length=500), nullable=True),
        sa.Column("install_tree_url", sa.String(length=1000), nullable=False),
        sa.Column("template_type", sa.String(length=30), nullable=False),
        sa.Column("boot_args", sa.Text(), nullable=True),
        # Soft reference to the originating mirror — provenance, not a FK.
        sa.Column("mirror_repository_id", GUID(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_install_source_os_family", _SOURCE, ["os_family"])
    op.create_index("ix_install_source_arch", _SOURCE, ["arch"])


def _create_assignment(insp) -> None:
    if insp.has_table(_ASSIGNMENT):
        return
    template_fk = (
        [
            sa.ForeignKeyConstraint(
                ["partition_template_id"],
                ["provisioning_template.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["finish_template_id"],
                ["provisioning_template.id"],
                ondelete="SET NULL",
            ),
        ]
        if insp.has_table("provisioning_template")
        else []
    )
    op.create_table(
        _ASSIGNMENT,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("mac_address", sa.String(length=17), nullable=False),
        sa.Column("install_source_id", GUID(), nullable=False),
        sa.Column("partition_template_id", GUID(), nullable=True),
        sa.Column("finish_template_id", GUID(), nullable=True),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("site_id", GUID(), nullable=True),
        sa.Column("access_group_id", GUID(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("boot_token", sa.String(length=64), nullable=True),
        sa.Column("boot_token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_boot_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mac_address"),
        sa.ForeignKeyConstraint(
            ["install_source_id"], ["install_source.id"], ondelete="CASCADE"
        ),
        *template_fk,
    )
    op.create_index("ix_host_install_assignment_mac", _ASSIGNMENT, ["mac_address"])
    op.create_index("ix_host_install_assignment_state", _ASSIGNMENT, ["state"])
    op.create_index("ix_host_install_assignment_token", _ASSIGNMENT, ["boot_token"])


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _create_install_source(insp)
    # Re-inspect: the assignment's FK targets the table just created.
    _create_assignment(inspect(op.get_bind()))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_ASSIGNMENT):
        op.drop_table(_ASSIGNMENT)
    if insp.has_table(_SOURCE):
        op.drop_table(_SOURCE)
