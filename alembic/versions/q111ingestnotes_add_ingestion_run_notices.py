# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What an air-gap ingest found after it completed (2026-11-24).

``airgap_ingestion_run.notices``: a JSON list of ``{code, params}`` -- a
SysManage tools repository that could not be built (apt-ftparchive or
createrepo_c missing), the security catalog loaded, refused (not the file
the signed manifest names) or failed.  Before this they were in the log
only, so the operator saw "Complete" and nothing else.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q111ingestnotes
Revises: q110srcpkg
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q111ingestnotes"
down_revision: Union[str, None] = "q110srcpkg"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_RUN = "airgap_ingestion_run"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    if "notices" not in {c["name"] for c in inspector.get_columns(_RUN)}:
        op.add_column(_RUN, sa.Column("notices", sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _RUN not in inspector.get_table_names():
        return
    if "notices" in {c["name"] for c in inspector.get_columns(_RUN)}:
        with op.batch_alter_table(_RUN) as batch:
            batch.drop_column("notices")
