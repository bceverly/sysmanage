# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""dedupe child_host_distribution + unique constraint + fix RHEL/RPM kvm install

Revision ID: v3uchildist0
Revises: u2lxd9latest
Create Date: 2026-05-05 11:55:00.000000

Three changes in one migration so a single ``alembic upgrade head`` fully
unblocks the KVM-on-RHEL-family child-host create flow:

1. Deduplicate ``child_host_distribution`` rows by
   ``(child_type, distribution_name, distribution_version)``.  Current
   data is already unique on that triple in production, so the dedupe
   step is a defensive no-op — but it's there so the migration is safe
   to re-run on a database that has drifted (e.g. a dev instance with
   re-applied seed data).
2. Add a unique constraint on
   ``(child_type, distribution_name, distribution_version)`` so future
   seeders / manual inserts cannot reintroduce duplicates.
3. Replace the KVM ``agent_install_commands`` for the RHEL / Rocky /
   Alma / Oracle family.  The previous payload ran
   ``pip3 install sysmanage-agent`` — but the agent isn't published on
   PyPI; cloud-init's runcmd block ran the dnf+pip steps without error,
   pip3 silently installed an unrelated (or no) package, and no agent
   ever registered.  Switch to the same GitHub-release-curl pattern
   Debian/Ubuntu use, with command substitution inside a single runcmd
   entry so no shell variables leak across entries (whether the runner
   is cloud-init's concatenated /bin/sh script or the LXD-style
   per-entry ``sh -c '<cmd>'``, both are correct under this form).

Idempotent + cross-database (SQLite + PostgreSQL):
* Dedupe runs in Python so no database-specific MIN(id) trickery is
  needed (UUID ordering differs between native PG ``uuid`` and SQLite
  CHAR(36) storage of the SysManage GUID type).
* Constraint creation is guarded by ``inspect().get_unique_constraints``
  so a second run skips it; the actual ADD goes through
  ``op.batch_alter_table`` so SQLite (which has no
  ``ALTER TABLE ADD CONSTRAINT``) gets the standard table-recreate
  dance.
* Install-commands UPDATE is gated on a marker string only the new
  payload contains, so a second run finds nothing to change.
"""

import json
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = "v3uchildist0"
down_revision: Union[str, None] = "u2lxd9latest"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "child_host_distribution"
_UQ_NAME = "uq_child_host_distribution_type_name_version"
_UQ_COLS = ["child_type", "distribution_name", "distribution_version"]

# Distributions whose KVM rows currently carry the broken pip3-based
# install.  The migration only rewrites rows that don't already carry
# the new payload, keyed off a marker string only the new commands
# contain.
_RHEL_FAMILY_NAMES = (
    "Oracle Linux",
    "Oracle",
    "Rocky Linux",
    "RockyLinux",
    "AlmaLinux",
    "RHEL",
)
_NEW_RPM_MARKER = "/tmp/sysmanage-agent.rpm"

# Mirror of the working Debian/Ubuntu pattern: pull the .rpm asset URL
# out of the GitHub release JSON via inline command substitution so all
# the work happens in a single sub-shell.
_NEW_RPM_KVM_COMMANDS = [
    "dnf install -y curl ca-certificates",
    "curl -fL -o /tmp/sysmanage-agent.rpm "
    "$(curl -sL https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest "
    "| grep -o '\"browser_download_url\": *\"[^\"]*\\.rpm\"' "
    "| grep -o 'https://[^\"]*\\.rpm' "
    "| head -1)",
    "dnf install -y /tmp/sysmanage-agent.rpm",
    "rm -f /tmp/sysmanage-agent.rpm",
]


def _dedupe_distribution_rows(bind) -> int:
    """Keep one row per (child_type, distribution_name, distribution_version);
    delete the rest.  Returns rows deleted.

    Done in Python rather than as a SQL subquery because UUID ordering
    differs between PostgreSQL (native ``uuid``) and SQLite (CHAR(36)
    storage of the GUID type), and we want the same deterministic result
    on both.  Tiebreaker per group: oldest ``created_at``, then lowest
    ``str(id)``."""
    rows = bind.execute(
        text(
            f"SELECT id, child_type, distribution_name, distribution_version, "
            f"created_at FROM {_TABLE}"
        )
    ).fetchall()
    survivors: dict = {}
    for row in rows:
        key = (row.child_type, row.distribution_name, row.distribution_version)
        sort_key = (row.created_at or datetime.min, str(row.id))
        if key not in survivors or sort_key < survivors[key][0]:
            survivors[key] = (sort_key, row.id)
    keep = {v[1] for v in survivors.values()}
    deleted = 0
    for row in rows:
        if row.id not in keep:
            bind.execute(
                text(f"DELETE FROM {_TABLE} WHERE id = :id"),
                {"id": row.id},
            )
            deleted += 1
    return deleted


def _ensure_unique_constraint(bind) -> bool:
    """Add the unique constraint if it isn't already present.  Returns
    True if this run created it, False if it already existed."""
    inspector = sa.inspect(bind)
    existing = {uq["name"] for uq in inspector.get_unique_constraints(_TABLE)}
    if _UQ_NAME in existing:
        return False
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.create_unique_constraint(_UQ_NAME, _UQ_COLS)
    return True


def _fix_rhel_kvm_install_commands(bind) -> int:
    """Rewrite the KVM ``agent_install_commands`` for RHEL-family distros
    to use the GitHub-release-curl pattern.  Idempotent: skips rows whose
    current commands already contain the new RPM marker."""
    new_payload = json.dumps(_NEW_RPM_KVM_COMMANDS)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    updated = 0
    for distro in _RHEL_FAMILY_NAMES:
        result = bind.execute(
            text(
                f"UPDATE {_TABLE} "
                "SET agent_install_commands = :payload, updated_at = :now "
                "WHERE child_type = 'kvm' "
                "  AND distribution_name = :distro "
                "  AND (agent_install_commands IS NULL "
                "       OR agent_install_commands NOT LIKE :marker)"
            ),
            {
                "payload": new_payload,
                "now": now,
                "distro": distro,
                "marker": f"%{_NEW_RPM_MARKER}%",
            },
        )
        updated += result.rowcount or 0
    return updated


def upgrade() -> None:
    bind = op.get_bind()
    _dedupe_distribution_rows(bind)
    _ensure_unique_constraint(bind)
    _fix_rhel_kvm_install_commands(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {uq["name"] for uq in inspector.get_unique_constraints(_TABLE)}
    if _UQ_NAME in existing:
        with op.batch_alter_table(_TABLE) as batch_op:
            batch_op.drop_constraint(_UQ_NAME, type_="unique")
    # We don't restore the broken ``pip3 install sysmanage-agent`` payload
    # on downgrade — that's a "feature" we never want back.  The dedupe
    # is also irreversible by design (deleted rows aren't kept around).
