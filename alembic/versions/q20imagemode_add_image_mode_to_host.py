# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add image-mode (bootc / rpm-ostree) host state to host (tenant partition) — Phase 17.3

Per-host image-mode state is operational state, so it lives on the ``host``
table in the TENANT partition (like the 14.3 release-upgrade job and the 14.4
FIPS columns).  Detection ("is this an image-mode host + which deployment is
booted/staged/rollback?") is reported by every agent (OSS, rides
``os_version_update``); the stage/apply/rollback action is Enterprise-gated
(``image_mode_manage`` / ``image_mode_engine``).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q20imagemode
Revises: q19imagecontent
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q20imagemode"
down_revision: Union[str, None] = "q19imagecontent"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"

# (name, type, extra kwargs) for each added column.  ``is_image_mode`` is a
# NOT-NULL boolean with a server default so it backfills False on existing rows.
_COLUMNS = (
    ("is_image_mode", sa.Boolean(), {"nullable": False, "server_default": "0"}),
    ("image_backend", sa.String(length=20), {"nullable": True}),
    ("booted_image_ref", sa.String(length=255), {"nullable": True}),
    ("booted_image_digest", sa.String(length=80), {"nullable": True}),
    ("staged_image_ref", sa.String(length=255), {"nullable": True}),
    ("staged_image_digest", sa.String(length=80), {"nullable": True}),
    ("rollback_available", sa.Boolean(), {"nullable": True}),
    ("image_mode_updated_at", sa.DateTime(), {"nullable": True}),
)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, coltype, kwargs in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, coltype, **kwargs))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, _coltype, _kwargs in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
