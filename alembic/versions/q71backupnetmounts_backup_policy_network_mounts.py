# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup: the network shares a host's backup leaves out (2026-11-01)

Tenant data.  network_mounts: what the host's agent reported at its last
configure, JSON {"excluded": [paths], "kept": [paths], "native": bool} --
the host's network and automount points left out of its backup (another
server's data), those an operator opted back in, and whether restate itself
leaves them out.  NULL: not reported (an older agent).  Additive,
idempotent; safe on SQLite + PostgreSQL.

Revision ID: q71backupnetmounts
Revises: q70backupreach
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q71backupnetmounts"
down_revision: Union[str, None] = "q70backupreach"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_POLICY = (("network_mounts", sa.Text()),)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_policy" not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns("backup_policy")}
    for name, kind in _POLICY:
        if name not in present:
            op.add_column("backup_policy", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_policy" not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns("backup_policy")}
    drop = [name for name, _kind in _POLICY if name in present]
    if drop:
        with op.batch_alter_table("backup_policy") as batch:
            for name in drop:
                batch.drop_column(name)
