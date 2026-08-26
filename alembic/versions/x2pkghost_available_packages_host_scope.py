# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add available_packages.host_id — the catalog becomes per-host

``available_packages`` was keyed only by (os_name, os_version, package_manager,
package_name), i.e. ONE shared catalog per OS for the whole fleet.  Two
consequences, both real:

  * every host of the same OS transmitted an identical ~89k-row catalog, and
  * ``handle_packages_batch_start`` DELETEs the rows for an OS before
    re-inserting them, so two same-OS hosts reporting concurrently interleave
    delete/insert over each other's rows, and a host that dies mid-batch (or is
    rejected part-way) leaves the catalog truncated FOR EVERY HOST of that OS.

Host scoping removes both: a host only ever deletes and rewrites its own rows.

The column is NULLABLE and carries no FK constraint:
  * nullable, because pre-existing rows have no owning host and back-filling
    them would be a guess — they are left for the owning host to replace on its
    next report, and the readers treat NULL as "legacy, OS-scoped";
  * no FK, because SQLite cannot add one via ALTER and the codebase already
    uses soft references for host links elsewhere (see r3hostsite).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: x2pkghost
Revises: x1agentcap
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "x2pkghost"
down_revision: Union[str, None] = "x1agentcap"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "available_packages"
_COLUMN = "host_id"
_INDEX = "ix_available_packages_host_id"
# The lookup every ingest does: "delete/replace THIS host's rows for THIS
# manager".  Without it that becomes a scan of a table with ~89k rows per host.
_INDEX_HOST_MANAGER = "ix_available_packages_host_manager"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return

    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=36), nullable=True))

    idx_names = {i["name"] for i in insp.get_indexes(_TABLE)}
    if _INDEX not in idx_names:
        op.create_index(_INDEX, _TABLE, [_COLUMN])
    if _INDEX_HOST_MANAGER not in idx_names:
        op.create_index(_INDEX_HOST_MANAGER, _TABLE, [_COLUMN, "package_manager"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return

    idx_names = {i["name"] for i in insp.get_indexes(_TABLE)}
    if _INDEX_HOST_MANAGER in idx_names:
        op.drop_index(_INDEX_HOST_MANAGER, table_name=_TABLE)
    if _INDEX in idx_names:
        op.drop_index(_INDEX, table_name=_TABLE)

    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
