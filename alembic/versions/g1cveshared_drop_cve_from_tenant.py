# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Drop the CVE reference/config tables from the tenant partition (option B).

The CVE reference + config tables moved to the shared partition (renamed to
``shared_*`` by the shared chain, revision ``s2sharedcve``).  This tenant-chain
revision removes their old tenant-side footprint:

* The cross-partition FK ``host_vulnerability_finding.vulnerability_id`` →
  ``(shared_)vulnerability`` is dropped — it is a soft reference now (the target
  lives in the shared partition; callers resolve it via the shared session).
* The old unprefixed CVE tables are dropped.  In the bootstrap/collapsed
  database the shared chain already renamed them away, so these are no-ops; in
  each per-tenant database they are empty leftovers from when CVE data was
  (incorrectly) tenant-partitioned.

The shared chain runs before this one, so on the bootstrap database the rename
has already happened — this never drops populated CVE data.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: g1cveshared
Revises: f1apikey01
"""

from typing import Union

from alembic import op
from sqlalchemy import inspect

revision: str = "g1cveshared"
down_revision: Union[str, None] = "f1apikey01"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_FINDING = "host_vulnerability_finding"
_CVE_TARGETS = ("vulnerability", "shared_vulnerability")
# Child (package_vulnerability) before parent (vulnerability) for FK safety on PG.
_DROP_TABLES = (
    "package_vulnerability",
    "vulnerability",
    "vulnerability_ingestion_log",
    "cve_refresh_settings",
)


# Deterministic name for the (often unnamed) FK so SQLite batch can address it.
_FK_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _drop_cve_fk(bind, insp) -> None:
    """Drop the cross-partition FK host_vulnerability_finding -> CVE table.

    PostgreSQL carries a real constraint name we can drop directly; SQLite cannot
    ALTER-DROP a constraint, so recreate the table without it via batch (using a
    naming convention so the reflected FK is addressable).
    """
    if not insp.has_table(_FINDING):
        return
    cve_fks = [
        fk
        for fk in insp.get_foreign_keys(_FINDING)
        if fk.get("referred_table") in _CVE_TARGETS
    ]
    if not cve_fks:
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_FINDING, naming_convention=_FK_NAMING) as batch:
            for fk in cve_fks:
                col = fk["constrained_columns"][0]
                name = f"fk_{_FINDING}_{col}_{fk['referred_table']}"
                # expand-contract-ok: cross-partition FK becomes a soft reference.
                batch.drop_constraint(name, type_="foreignkey")
    else:
        for fk in cve_fks:
            if fk.get("name"):
                # expand-contract-ok: cross-partition FK becomes a soft reference.
                op.drop_constraint(fk["name"], _FINDING, type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Drop the now cross-partition FK on host_vulnerability_finding.
    _drop_cve_fk(bind, inspect(bind))

    # 2. Drop the old tenant-side CVE tables (relocated to the shared partition).
    existing = set(inspect(bind).get_table_names())
    for tbl in _DROP_TABLES:
        if tbl in existing:
            # expand-contract-ok: CVE data relocated to the shared partition (shared_* tables)
            op.drop_table(tbl)


def downgrade() -> None:
    # Forward-only: the CVE tables now live in the shared partition; recreating
    # empty tenant copies would diverge from the shared-partition model.  The
    # shared chain's downgrade restores the unprefixed tables in the bootstrap
    # database.
    pass
