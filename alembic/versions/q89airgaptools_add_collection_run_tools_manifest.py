# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SysManage tools on an air-gap collection run's media (ROADMAP 25.9).

``airgap_collection_run.tools_manifest``: JSON ``[{distro, version, files:
[{name, sha256}]}]`` -- the agent, restate and restate-proxy packages the
mirror host fetched beside the mirrors, kept between the staging and the
ISO step, where it is signed into the media's manifest.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q89airgaptools
Revises: q88pmrepair
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q89airgaptools"
down_revision: Union[str, None] = "q88pmrepair"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_RUN = "airgap_collection_run"
_COLUMN = "tools_manifest"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_RUN)}:
        op.add_column(_RUN, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_RUN)}:
        with op.batch_alter_table(_RUN) as batch:
            batch.drop_column(_COLUMN)
