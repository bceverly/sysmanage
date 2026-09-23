# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add host.updates_updated_at -- WHEN update detection last reported

A host's pending updates are replaced wholesale on every report, so "checked
and nothing is pending" and "never checked" were the same state: zero rows.
Every other inventory source already stamps its own time (software, hardware,
OS version, reboot state); update detection did not.

It matters most for the one assessment built directly on that list: an
OpenBSD vulnerability verdict is "every security erratum is absent from
``syspatch -c``", and without a timestamp a host whose check never ran read
as fully patched.  The stand-in used until now,
``available_packages_fingerprint_at``, belongs to the available-packages
CATALOG, which is a different report (found 2026-09-23).

NULL means "no update report received since this column existed" -- the
honest answer for every host until its next update cycle.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q5updatesat
Revises: q4filewatch
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q5updatesat"
down_revision: Union[str, None] = "q4filewatch"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"
_COLUMN = "updates_updated_at"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    if _COLUMN not in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    if _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
