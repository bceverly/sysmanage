# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""child host provision progress — Phase 12.5

Revision ID: w2winprog
Revises: w1winchild
Create Date: 2026-08-05 00:00:00.000000

``host_child.installation_step`` already existed but nothing ever wrote it —
the agent's progress messages were logged and dropped server-side, so the
column was permanently NULL and the UI had nothing to show.

These three make a long provision legible.  A Windows Server install runs
25-45 minutes, during which "no news" means either working or wedged, and the
UI cannot tell those apart from a step string alone:

  installation_step_number / installation_total_steps
      the counter, so the UI can render real progress rather than a spinner
      that looks identical at minute 2 and minute 40.

  installation_step_at
      when that step was last reported.  This is the Phase 11.6 in-flight
      journal's heartbeat idea applied to the UI: a stalled provision is one
      whose heartbeat stopped, and without a timestamp it is indistinguishable
      from a slow one.

All nullable — every existing row predates progress reporting, and a child
created by an older agent will never populate them.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w2winprog"
down_revision: Union[str, None] = "w1winchild"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("installation_step_number", sa.Integer()),
    ("installation_total_steps", sa.Integer()),
    ("installation_step_at", sa.DateTime()),
)


def _has_column(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for name, coltype in _COLUMNS:
        if not _has_column(bind, "host_child", name):
            op.add_column("host_child", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for name, _coltype in reversed(_COLUMNS):
        if _has_column(bind, "host_child", name):
            op.drop_column("host_child", name)
