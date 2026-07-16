# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add mirror_setup_status table (Phase 10.4.1)

Revision ID: z7mirror20setup
Revises: y6idp10extauth
Create Date: 2026-05-07 21:00:00.000000

One-row-per-host cache for the Repository Mirroring setup card.
Backs the GET /api/mirror-repositories/setup-status/{host_id}
endpoint without forcing a synchronous round-trip through the agent
on every page render — the agent posts updates asynchronously via
the existing ``apply_deployment_plan`` + ``command_result`` path.

Columns:

  host_id                  PK + FK → host.id (cascade on host delete)
  tools                    JSON map: ``{"apt-mirror": "present", …}``
  platform                 e.g. "Linux", "FreeBSD" (uname -s)
  distro                   e.g. "ubuntu", "ol", "freebsd" (/etc/os-release ID)
  last_check_at            timestamp of the last probe-result that
                           landed (NULL if never probed)
  last_check_message_id    in-flight probe message_id (NULL when idle)
  last_check_error         agent stderr from the last failed probe
  install_status           "idle" | "dispatched" | "succeeded" | "failed"
  last_install_at          timestamp of the last install attempt
  last_install_message_id  in-flight install message_id (NULL when idle)
  last_install_error       agent stderr from the last failed install

Idempotent — re-running ``alembic upgrade head`` is a no-op via
``inspect().has_table()``.  SQLite + PostgreSQL safe; uses ``sa.JSON``
which lands as TEXT on SQLite and as JSON on PostgreSQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "z7mirror20setup"
down_revision: Union[str, None] = "y6idp10extauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("mirror_setup_status"):
        op.create_table(
            "mirror_setup_status",
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("tools", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("platform", sa.String(length=40), nullable=True),
            sa.Column("distro", sa.String(length=40), nullable=True),
            sa.Column("last_check_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("last_check_message_id", sa.String(length=36), nullable=True),
            sa.Column("last_check_error", sa.Text(), nullable=True),
            sa.Column(
                "install_status",
                sa.String(length=20),
                nullable=False,
                server_default="idle",
            ),
            sa.Column("last_install_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column(
                "last_install_message_id", sa.String(length=36), nullable=True
            ),
            sa.Column("last_install_error", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("mirror_setup_status"):
        op.drop_table("mirror_setup_status")
