# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""enable the per-OS CVE feeds on existing installs (Phase 21.2)

A settings row records the sources that were enabled when it was CREATED, so
a feed added later never runs on an existing install -- and a host whose feed
never runs stays "not assessable". None of these four has had a real operator
choice to respect: FreeBSD VuXML was a stub (off by default, ingesting
nothing), Microsoft was "on by default" yet never in the default list (and its
fetcher ingested nothing), and NetBSD and macOS did not exist. So each is
appended where missing. Nothing else in the list is touched, and an operator
can switch any of them off afterwards.

Data-only (no schema change). Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s16osfeeds
Revises: s15advisordefault
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "s16osfeeds"
down_revision: Union[str, None] = "s15advisordefault"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "shared_cve_refresh_settings"
_NEW_SOURCES = ("microsoft", "freebsd", "netbsd", "macos")

_settings = sa.table(
    _TABLE,
    sa.column("id"),  # untyped: bind back exactly what the driver returned
    sa.column("enabled_sources", sa.JSON()),
)


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in inspect(bind).get_table_names():
        return
    for row in bind.execute(sa.select(_settings.c.id, _settings.c.enabled_sources)):
        sources = list(row.enabled_sources or [])
        missing = [s for s in _NEW_SOURCES if s not in sources]
        if missing:
            bind.execute(
                _settings.update()
                .where(_settings.c.id == row.id)
                .values(enabled_sources=sources + missing)
            )


def downgrade() -> None:
    # Not reversed: after the upgrade an operator may have chosen these feeds
    # deliberately, and the migration cannot tell that apart from its own work.
    pass
