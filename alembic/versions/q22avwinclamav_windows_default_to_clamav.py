# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Windows antivirus default: clamwin -> clamav (Phase 21.3)

The seeded Windows default was ClamWin, whose newest release is ClamAV 0.103
(end of life).  The agent detects, and the malware scanner runs, the official
ClamAV build in C:\\Program Files\\ClamAV, so a ClamWin install was never seen.
The deploy planner now installs official ClamAV; this makes the default the
operator sees say so.  Only the untouched seeded value is changed.

Data-only. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q22avwinclamav
Revises: q21avauto
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q22avwinclamav"
down_revision: Union[str, None] = "q21avauto"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _set(old: str, new: str) -> None:
    if "antivirus_default" not in inspect(op.get_bind()).get_table_names():
        return
    op.execute(
        sa.text(
            "UPDATE antivirus_default SET antivirus_package = :new "
            "WHERE os_name = 'Windows' AND antivirus_package = :old"
        ).bindparams(old=old, new=new)
    )


def upgrade() -> None:
    _set("clamwin", "clamav")


def downgrade() -> None:
    _set("clamav", "clamwin")
