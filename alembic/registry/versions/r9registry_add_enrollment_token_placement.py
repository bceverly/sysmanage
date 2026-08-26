# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add enrollment-token placement (site_id, access_group_id) — Phase 18.1 S4

SOFT-reference columns on ``registry_enrollment_token`` (no FK — the referenced
``federation_sites`` / ``access_groups`` rows live outside the registry
partition).  When set, a host enrolled with the token is also bound to the
access group and/or site.  Both NULL = tenant-scope only (pre-18.1 behavior).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r9registry
Revises: r8registry
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "r9registry"
down_revision: Union[str, None] = "r8registry"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "registry_enrollment_token"
_COLUMNS = ("site_id", "access_group_id")


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for col in _COLUMNS:
        if col not in existing:
            op.add_column(_TABLE, sa.Column(col, sa.String(length=36), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for col in reversed(_COLUMNS):
        if col in existing:
            op.drop_column(_TABLE, col)
