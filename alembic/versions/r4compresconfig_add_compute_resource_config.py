# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add compute_resource.config (non-secret provider settings) — Phase 18.1

A nullable JSON bag on ``compute_resource`` for NON-secret provider config that
doesn't warrant a column each — e.g. the Proxmox node SSH login
(``node_ssh_user``), snippet-storage name, or node SSH host for cluster
targeting.  Secrets still live only in OpenBAO (referenced by
``credential_ref``); this column never holds credentials.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r4compresconfig
Revises: r3hostsite
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "r4compresconfig"
down_revision: Union[str, None] = "r3hostsite"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table("compute_resource"):
        return
    cols = {c["name"] for c in insp.get_columns("compute_resource")}
    if "config" not in cols:
        op.add_column("compute_resource", sa.Column("config", sa.JSON(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table("compute_resource"):
        return
    cols = {c["name"] for c in insp.get_columns("compute_resource")}
    if "config" in cols:
        # batch mode so the drop also works on older SQLite (rebuild-table path)
        with op.batch_alter_table("compute_resource") as batch:
            batch.drop_column("config")
