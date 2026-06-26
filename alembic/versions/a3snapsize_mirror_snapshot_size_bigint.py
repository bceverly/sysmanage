"""Widen mirror_snapshot.size_bytes to BigInteger.

Revision ID: a3snapsize
Revises: z7mirrorfail
Create Date: 2026-06-02 12:00:00.000000

A repository mirror snapshot's byte total routinely exceeds the
signed-32-bit INTEGER ceiling (~2.15 GB) — e.g. a 9.7 GB Ubuntu mirror.
The agent's snapshot-result handler does
``UPDATE mirror_snapshot SET size_bytes=..., file_count=...`` which then
raised ``psycopg2.errors.NumericValueOutOfRange`` ("integer out of
range"), rolled back the whole result-apply transaction, and left the
snapshot stuck in ``DISPATCHED`` with ``last_snapshot_message_id`` never
cleared.  That in turn blocked every air-gap collection run sourcing
from the mirror (the run-tick waits at QUEUED for a snapshot that had
actually completed).  Widen to BigInteger (INT8).

Reversible — downgrade narrows back to Integer and will fail loudly if
any row's size_bytes exceeds INT4_MAX at that time.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a3snapsize"
down_revision: Union[str, None] = "z7mirrorfail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite's INTEGER is a dynamic up-to-8-byte type that already stores
    # values > INT4_MAX fine, and it has no ``ALTER COLUMN ... TYPE`` —
    # so this is a no-op there.  Only emit the real DDL on backends that
    # need (and support) it; without this guard alembic would emit
    # ``ALTER TABLE ... ALTER COLUMN ... TYPE BIGINT`` which SQLite
    # rejects with "near 'ALTER': syntax error".
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "mirror_snapshot",
        "size_bytes",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "mirror_snapshot",
        "size_bytes",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
