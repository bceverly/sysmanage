# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create mirror_image_content (tenant partition) — Phase 17.2 (S3)

One row per (mirror, container-image ref): the registry / repository / tag
tracked for capture into a mirror, plus the pinned ``digest`` (once captured)
and capture bookkeeping.  The captured OCI layouts live on disk under the
mirror's ``images`` dir; these rows drive the ``oci_proxy_engine`` capture plan
and let a later content-view publish materialize the images into the version
store.

Part of the TENANT chain (``mirror_repository`` is an unprefixed tenant table),
chained off ``q18snapcontent``.  Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q19imagecontent
Revises: q18snapcontent
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q19imagecontent"
down_revision: Union[str, None] = "q18snapcontent"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "mirror_image_content"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("repository_id", GUID(), nullable=False),
            sa.Column("registry", sa.String(length=255), nullable=False),
            sa.Column("repository", sa.String(length=255), nullable=False),
            sa.Column("tag", sa.String(length=128), nullable=False),
            sa.Column("digest", sa.String(length=255), nullable=True),
            sa.Column("capture_status", sa.String(length=20), nullable=False),
            sa.Column("last_capture_message_id", sa.String(length=80), nullable=True),
            sa.Column("last_capture_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["repository_id"], ["mirror_repository.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "repository_id",
                "registry",
                "repository",
                "tag",
                name="uq_mirror_image_content",
            ),
        )
        op.create_index("ix_%s_repository_id" % _TABLE, _TABLE, ["repository_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        op.drop_index("ix_%s_repository_id" % _TABLE, table_name=_TABLE)
        op.drop_table(_TABLE)
