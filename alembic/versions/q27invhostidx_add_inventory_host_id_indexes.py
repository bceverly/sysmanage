# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""index host_id on the per-report inventory tables (Phase 22.2)

PostgreSQL does not index a foreign key's column.  These tables are read,
replaced or diffed per host on every inventory report, and had no index on
host_id: every such statement scanned the whole fleet's rows.  At 10,000
agents (2026-10-02, pg_stat_statements) reading one host's software inventory
took 61 ms -- 31% of the database's time -- and deleting one host's users and
groups 6-7 ms each.  It also made deleting a host (ON DELETE CASCADE) scan
each table.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q27invhostidx
Revises: q26mqhostidx
"""

from typing import Union

from sqlalchemy import inspect

from alembic import op

revision: str = "q27invhostidx"
down_revision: Union[str, None] = "q26mqhostidx"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

TABLES = (
    "software_package",
    "user_accounts",
    "user_groups",
    "user_group_memberships",
    "host_certificates",
    "host_roles",
    "network_interface",
    "storage_device",
)


def _index(table: str) -> str:
    return f"ix_{table}_host_id"


def _present(inspector, table: str) -> bool:
    return any(i["name"] == _index(table) for i in inspector.get_indexes(table))


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in TABLES:
        if table in tables and not _present(inspector, table):
            op.create_index(_index(table), table, ["host_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in TABLES:
        if table in tables and _present(inspector, table):
            op.drop_index(_index(table), table_name=table)
