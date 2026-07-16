# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""airgap_ingestion_run: worker_message_id + manifest_json (ingestion orchestrator).

Revision ID: z6ingest
Revises: y5srvcfg
Create Date: 2026-05-28 12:00:00.000000

The repository-side ingestion orchestrator (``airgap_ingest_tick``)
drives QUEUED ``AirgapIngestionRun`` rows through their lifecycle by
dispatching mount/copy plans to the repository host's agent.  Two new
columns:

  * ``worker_message_id`` — the same in-flight marker the collector
    orchestrator uses on ``airgap_collection_run``: stamped at dispatch,
    cleared on result, so a slow plan isn't double-dispatched next tick.
  * ``manifest_json`` — the verified inner manifest captured at the
    mount/verify step.  Persisted (rather than kept in memory) so the
    copy-complete step can register per-distro ``AirgapLocalRepository``
    rows from ``manifest['targets']`` even across a server restart, and
    so the ingest is auditable after the fact ("what did we accept?").

Idempotent: each column add is guarded by an ``inspect()`` check.
SQLite- and PostgreSQL-safe.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "z6ingest"
down_revision: Union[str, None] = "y5srvcfg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "airgap_ingestion_run"
_COLUMNS = {
    "worker_message_id": lambda: sa.Column(
        "worker_message_id", sa.String(length=80), nullable=True
    ),
    "manifest_json": lambda: sa.Column("manifest_json", sa.Text(), nullable=True),
}


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    to_add = [name for name in _COLUMNS if name not in existing]
    if not to_add:
        return
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        for name in to_add:
            batch.add_column(_COLUMNS[name]())


def downgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    to_drop = [name for name in _COLUMNS if name in existing]
    if not to_drop:
        return
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        for name in to_drop:
            batch.drop_column(name)
