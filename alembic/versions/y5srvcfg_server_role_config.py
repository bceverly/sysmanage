"""server_configuration singleton (air-gap server_role moved out of YAML).

Revision ID: y5srvcfg
Revises: x4airgap80optB
Create Date: 2026-05-28 09:00:00.000000

Phase 12: the air-gap topology role (standard | collector | repository)
used to live in ``sysmanage.yaml`` under the top-level ``role:`` key.
That meant operators hand-edited a config file and restarted to pick a
role.  This migration moves it into the database so it can be set from
Settings → Server Role in the web UI.

Creates a single-row ``server_configuration`` table (sentinel-UUID
singleton, same pattern as ``mirror_settings``) and seeds the one row
with ``server_role = 'standard'`` — i.e. "no air gap", the safe default
that matches the pre-existing behaviour when ``role:`` was omitted from
the YAML.  Operators with an existing ``role: collector`` /
``role: repository`` in their YAML re-pick it once via the new UI; the
now-unused YAML key is harmlessly ignored.

Idempotent: guarded by ``inspect().has_table()`` and a SELECT before
the seed INSERT, so re-running on a partially-migrated DB is a no-op.
SQLite- and PostgreSQL-safe (plain CREATE TABLE + parameterised
INSERT; no dialect-specific DDL).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

from backend.persistence.models.core import GUID


revision: str = "y5srvcfg"
down_revision: Union[str, None] = "x4airgap80optB"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "server_configuration"
_SINGLETON_ID = "00000000-0000-0000-0000-000000000004"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True, nullable=False),
            sa.Column(
                "server_role",
                sa.String(length=40),
                nullable=False,
                server_default="standard",
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    # Seed the singleton row if absent.  Matched on the sentinel id so
    # re-running never duplicates it.
    existing = bind.execute(
        text(f"SELECT 1 FROM {_TABLE} WHERE id = :id"),
        {"id": _SINGLETON_ID},
    ).fetchone()
    if not existing:
        bind.execute(
            text(
                f"INSERT INTO {_TABLE} (id, server_role) "
                "VALUES (:id, :role)"
            ),
            {"id": _SINGLETON_ID, "role": "standard"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
