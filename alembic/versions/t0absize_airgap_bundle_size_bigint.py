# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Widen airgap_bundle.size_bytes to BigInteger.

Revision ID: t0absize
Revises: s9abver
Create Date: 2026-05-25 16:10:00.000000

Multi-OS server bundles routinely exceed 2 GB (Postgres INT4_MAX is
~2.15 GB), which caused commit failures and left bundle rows stuck in
the "building" state.  Widen to BigInteger (INT8).

Reversible — downgrade narrows back to Integer.  Doesn't lose data
because actual stored sizes will fit in Integer if-and-only-if the
narrowing target is reached after they're cleared.  Downgrade will
fail loudly if any row has size > INT4_MAX at the time.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t0absize"
down_revision: Union[str, None] = "s9abver"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite has no ``ALTER COLUMN ... TYPE`` and its ``INTEGER`` is
    # already a dynamic, up-to-8-byte type that stores >INT4_MAX values
    # fine — so widening to BigInteger is a no-op there.  Only emit the
    # real DDL on backends that need (and support) it.  Without this
    # guard alembic emits ``ALTER TABLE ... ALTER COLUMN ... TYPE BIGINT``
    # which SQLite rejects with "near 'ALTER': syntax error".
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "airgap_bundle",
        "size_bytes",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "airgap_bundle",
        "size_bytes",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
