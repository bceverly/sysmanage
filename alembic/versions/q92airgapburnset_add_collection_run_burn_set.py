# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Burning an air-gap disc set one disc at a time.

``airgap_collection_run.disc_count``: how many discs the run's plan made (1
for a single ISO).  ``airgap_collection_run.burned_disc_count``: how many of
them the burn device has written so far.  Between two discs the run waits at
AWAITING_MEDIA until the operator confirms a blank disc is loaded.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q92airgapburnset
Revises: q91ingestdisc
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q92airgapburnset"
down_revision: Union[str, None] = "q91ingestdisc"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_RUN = "airgap_collection_run"
_COLUMNS = (
    ("disc_count", None),
    # Existing rows have burned nothing of a set yet; a finished
    # single-disc burn reads the same as before (COMPLETE).
    ("burned_disc_count", "0"),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_RUN)}
    for name, default in _COLUMNS:
        if name not in have:
            op.add_column(
                _RUN,
                sa.Column(
                    name,
                    sa.Integer(),
                    nullable=True,
                    server_default=sa.text(default) if default else None,
                ),
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_RUN)}
    with op.batch_alter_table(_RUN) as batch:
        for name, _default in _COLUMNS:
            if name in have:
                batch.drop_column(name)
