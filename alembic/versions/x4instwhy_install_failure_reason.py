# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add host_install_assignment install_detail / install_log_tail — say WHY

A machine installed, silently did not enroll, and the reason (a broken apt
repo) was three layers away and only findable by inference -- it existed solely
in bootstrap output on a console nobody was watching.  The install callback
carried a state and nothing else, so the assignment row could say "installed"
about a machine with no agent on it.

These columns hold what the MACHINE reports: a one-line reason and the tail of
its bootstrap log, so the row reads
``agent install failed: Unable to locate package sysmanage-agent``.

Paired with the new ``agent_missing`` state, which distinguishes "the bootstrap
script ran" from "the agent is up".  Both still DISARM netboot: the script
deliberately continues past failure so a late error still reports back, and a
state that left the machine armed would reinstall it on every reboot, wiping
the OS it just installed.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: x4instwhy
Revises: x3pkgfp
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "x4instwhy"
down_revision: Union[str, None] = "x3pkgfp"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host_install_assignment"
_COLUMNS = {
    "install_detail": sa.String(length=500),
    "install_log_tail": sa.Text(),
    "install_reported_at": sa.DateTime(),
}


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, coltype in _COLUMNS.items():
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
