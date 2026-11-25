# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The off-site cloud copy: S3 Glacier Deep Archive (ROADMAP 27.3).

``backup_offsite_copy`` (one per target: bucket, settings, the OpenBAO path
of its credentials), ``backup_offsite_key`` (its AES-256 keys, by OpenBAO
path), ``backup_offsite_run`` (check / upload / restore jobs) and
``backup_offsite_stream`` (what is in the bucket).  Pure additive (new
tables); idempotent and identical on SQLite and PostgreSQL.

Revision ID: q118offsite
Revises: q117malwarepolicy
"""

from typing import Union

import sqlalchemy as sa

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q118offsite"
down_revision: Union[str, None] = "q117malwarepolicy"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _copy():
    return (
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("target_id", GUID(), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bucket", sa.String(63), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=True),
        sa.Column("prefix", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "storage_class",
            sa.String(16),
            nullable=False,
            server_default="DEEP_ARCHIVE",
        ),
        sa.Column(
            "object_lock", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("credentials_ref", sa.String(512), nullable=True),
        sa.Column("access_key_hint", sa.String(32), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("last_run_id", GUID(), nullable=True),
        sa.Column("last_ok_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lock_verified", sa.Boolean(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("alerted_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def _key():
    return (
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("copy_id", GUID(), nullable=False, index=True),
        sa.Column("key_id", sa.String(16), nullable=False, index=True),
        sa.Column("key_ref", sa.String(512), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
    )


def _run():
    return (
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("copy_id", GUID(), nullable=False, index=True),
        sa.Column("host_id", GUID(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="queued", index=True
        ),
        sa.Column("command_id", sa.String(64), nullable=True, index=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("key_id", sa.String(16), nullable=True),
        sa.Column("snapshot", sa.String(64), nullable=True),
        sa.Column("progress", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("bytes_moved", sa.BigInteger(), nullable=True),
        sa.Column("secrets_released_at", sa.DateTime(), nullable=True),
        sa.Column("target_dataset", sa.String(255), nullable=True),
        sa.Column("streams", sa.Text(), nullable=True),
    )


def _stream():
    return (
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("copy_id", GUID(), nullable=False, index=True),
        sa.Column("run_id", GUID(), nullable=True),
        sa.Column("dataset", sa.String(255), nullable=False, index=True),
        sa.Column("snapshot", sa.String(64), nullable=False),
        sa.Column("base_snapshot", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("key_id", sa.String(16), nullable=False),
        sa.Column("storage_class", sa.String(16), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("parts", sa.Text(), nullable=False),
        sa.Column("part_count", sa.Integer(), nullable=False),
        sa.Column("bytes_stored", sa.BigInteger(), nullable=False),
        sa.Column("stream_bytes", sa.BigInteger(), nullable=True),
        sa.Column("manifest_key", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False, index=True),
    )


_TABLES = (
    ("backup_offsite_copy", _copy),
    ("backup_offsite_key", _key),
    ("backup_offsite_run", _run),
    ("backup_offsite_stream", _stream),
)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for name, columns in _TABLES:
        if name not in tables:
            op.create_table(name, *columns())


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for name, _columns in reversed(_TABLES):
        if name in tables:
            op.drop_table(name)
