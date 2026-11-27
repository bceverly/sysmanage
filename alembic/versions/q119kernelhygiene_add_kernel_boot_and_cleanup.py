# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Package and kernel hygiene (ROADMAP 27.8).

``host_kernel_boot`` (each boot and the kernel it ran; a kernel is proven
by a boot that stayed up), ``package_cleanup_run`` (every cleanup plan and
apply) and ``auto_update_settings.cleanup_mode`` (what an automatic update
run does afterwards: ``apply`` by default, ``report`` or ``off``).
Additive; idempotent and identical on SQLite and PostgreSQL.

Revision ID: q119kernelhygiene
Revises: q118offsite
"""

from typing import Union

import sqlalchemy as sa

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q119kernelhygiene"
down_revision: Union[str, None] = "q118offsite"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _boot():
    return (
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("host_id", GUID(), nullable=False, index=True),
        sa.Column("boot_time", sa.DateTime(), nullable=False),
        sa.Column("kernel_release", sa.String(128), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("proven_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("host_id", "boot_time", name="uq_host_kernel_boot"),
    )


def _cleanup():
    return (
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("host_id", GUID(), nullable=False, index=True),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("trigger", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("protected", sa.JSON(), nullable=True),
        sa.Column("approved", sa.JSON(), nullable=True),
        sa.Column("packages", sa.JSON(), nullable=True),
        sa.Column("kept", sa.JSON(), nullable=True),
        sa.Column("running_kernel", sa.String(128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


_TABLES = (("host_kernel_boot", _boot), ("package_cleanup_run", _cleanup))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for name, columns in _TABLES:
        if name not in tables:
            op.create_table(name, *columns())
    if "auto_update_settings" in tables:
        present = {c["name"] for c in inspector.get_columns("auto_update_settings")}
        if "cleanup_mode" not in present:
            with op.batch_alter_table("auto_update_settings") as batch:
                batch.add_column(
                    sa.Column(
                        "cleanup_mode",
                        sa.String(8),
                        nullable=False,
                        server_default="apply",
                    )
                )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "auto_update_settings" in tables:
        present = {c["name"] for c in inspector.get_columns("auto_update_settings")}
        if "cleanup_mode" in present:
            with op.batch_alter_table("auto_update_settings") as batch:
                batch.drop_column("cleanup_mode")
    for name, _columns in reversed(_TABLES):
        if name in tables:
            op.drop_table(name)
