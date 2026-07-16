# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_push_attempts

Phase 12.10 hardening: add retry-tracking columns to
``federation_dispatched_commands`` (sync queue + policy assignments
already have them).  These let the coordinator's push worker apply
exponential backoff + dead-letter dispatched commands the same way
it already does for policy pushes.

Adds three columns to ``federation_dispatched_commands``:

  ``push_attempts``         INTEGER NOT NULL DEFAULT 0
      Count of push attempts the coordinator has made for this
      command.  Bumped on every transport attempt regardless of
      outcome; reset to 0 only by explicit operator action.
  ``last_push_attempt_at``  DATETIME nullable
      Wall-clock timestamp of the most recent push attempt.  The
      backoff filter compares this against
      ``last_push_attempt_at + compute_backoff(push_attempts) <= now``.
  ``last_push_error``       TEXT nullable
      Most-recent failure detail (HTTP status, connection error
      message, etc.).  Captured for the diagnostics endpoint /
      operator UI.

Idempotent + cross-dialect: guards on the column-exists check
before adding.  ``push_attempts`` uses ``sa.true()``-style
literal default via ``server_default`` so existing rows get 0 on
upgrade (every other column is nullable so they survive an
unguarded INSERT).

Revision ID: r7hardening
Revises: q6coordbearer
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "r7hardening"
down_revision: Union[str, None] = "q6coordbearer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, type, nullable, server_default).
_NEW_COLUMNS = (
    (
        "federation_dispatched_commands",
        "push_attempts",
        sa.Integer(),
        False,
        sa.text("0"),
    ),
    (
        "federation_dispatched_commands",
        "last_push_attempt_at",
        sa.DateTime(),
        True,
        None,
    ),
    ("federation_dispatched_commands", "last_push_error", sa.Text(), True, None),
    (
        "federation_policy_assignments",
        "push_attempts",
        sa.Integer(),
        False,
        sa.text("0"),
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    for table, name, type_, nullable, server_default in _NEW_COLUMNS:
        if table not in table_names:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if name in existing:
            continue
        kwargs = {"nullable": nullable}
        if server_default is not None:
            kwargs["server_default"] = server_default
        op.add_column(table, sa.Column(name, type_, **kwargs))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    for table, name, _type, _nullable, _default in reversed(_NEW_COLUMNS):
        if table not in table_names:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if name in existing:
            op.drop_column(table, name)
