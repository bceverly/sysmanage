# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Which disc of a set an air-gap ingest copied (ROADMAP 25.9).

``airgap_ingestion_run.disc_index`` / ``disc_count``: read from the media's
manifest envelope at the verify step.  A disc of a set of two or more is
merged into the repository instead of replacing it, so ingesting disc 2
no longer deletes what disc 1 brought.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q91ingestdisc
Revises: q90proautoattach
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q91ingestdisc"
down_revision: Union[str, None] = "q90proautoattach"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_RUN = "airgap_ingestion_run"
_COLUMNS = ("disc_index", "disc_count")


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_RUN)}
    for name in _COLUMNS:
        if name not in have:
            op.add_column(_RUN, sa.Column(name, sa.Integer(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_RUN)}
    with op.batch_alter_table(_RUN) as batch:
        for name in _COLUMNS:
            if name in have:
                batch.drop_column(name)
