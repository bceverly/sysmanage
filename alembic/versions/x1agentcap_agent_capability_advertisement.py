# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""agent capability advertisement — Phase 19

Revision ID: x1agentcap
Revises: w2winprog
Create Date: 2026-08-07 00:00:00.000000

Not every platform runs the FULL agent — alpine/freebsd/openbsd/netbsd already
run reduced-capability builds — and until now the server had no idea, so it
dispatched commands the agent could not route and the operator found out as a
runtime failure.

  agent_capabilities
      The report the agent sent, stored verbatim as JSON with sorted keys:
      schema_version, the capability GROUPS the UI shows, the exact command
      types the dispatch gate reads, and unavailable/partial groups with a
      machine-readable reason code.  Kept whole rather than shredded into
      columns precisely so a NEWER agent can advertise capabilities this
      server has never heard of without needing a migration — the server
      ignores what it does not recognise.  Same treatment as a federated
      site's ``capabilities_json``.

      NULL means "never told us" (an older agent, or one whose report could
      not be built).  That is deliberately distinct from "limited": a host we
      know nothing about must not be flagged reduced, and must not have its
      commands gated.

  agent_capabilities_limited
      Denormalised "advertised set is a strict subset of the baseline" so the
      hosts list can filter and sort without parsing JSON on every row.
      NOT NULL DEFAULT false: existing rows are unknown-capability, which is
      not limited, and a nullable tri-state here would put "unknown" and
      "not limited" in the same column with no way to tell them apart —
      ``agent_capabilities IS NULL`` is the unknown test.

  agent_capabilities_updated_at
      When the report last landed, so a stale advertisement is visible rather
      than silently trusted forever.

Idempotent and SQLite/PostgreSQL-safe: every step checks the inspector first,
so re-running against a database that already has these is a no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "x1agentcap"
down_revision: Union[str, None] = "w2winprog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "host"

_COLUMNS = (
    ("agent_capabilities", sa.Text(), True, None),
    ("agent_capabilities_limited", sa.Boolean(), False, sa.false()),
    ("agent_capabilities_updated_at", sa.DateTime(), True, None),
)


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for name, coltype, nullable, default in _COLUMNS:
        if _has_column(bind, _TABLE, name):
            continue
        # server_default on the NOT NULL column: SQLite cannot add a NOT NULL
        # column to a populated table without one, and existing hosts must
        # come out "not limited" rather than NULL.
        op.add_column(
            _TABLE,
            sa.Column(name, coltype, nullable=nullable, server_default=default),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for name, _coltype, _nullable, _default in reversed(_COLUMNS):
        if _has_column(bind, _TABLE, name):
            op.drop_column(_TABLE, name)
