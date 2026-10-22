# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""VMM child hosts: OpenBSD 7.9 and 8.0; retire the unsupported releases (2026-10-22)

OpenBSD supports only its two newest releases, and since 8.0 shipped that is
7.9 and 8.0 -- the only releases sysmanage-agent publishes packages for (the
OpenBSD build matrix).  The catalog offered 7.4-7.7, whose agent packages are
no longer built, so a child host created from them could not get an agent.

This upserts OpenBSD 7.9 and 8.0 for the ``vmm`` child type (the release ISO
from ftp.openbsd.org, which keeps older releases after the CDN drops them,
and the per-release direct package download), and marks every other OpenBSD
``vmm`` row inactive -- not deleted: existing child hosts still name them.

Idempotent (upsert by child type, name and version; the deactivation is a
plain UPDATE); safe on SQLite + PostgreSQL.

Revision ID: q58vmmopenbsd80
Revises: q57backupnfspath
"""

import json
import uuid
from typing import Sequence, Union

from sqlalchemy import text

from alembic import op

revision: str = "q58vmmopenbsd80"
down_revision: Union[str, None] = "q57backupnfspath"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUPPORTED = ("7.9", "8.0")
_API_URL = "https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest"


def _commands(version: str) -> str:
    """The agent's own release package for this OpenBSD release (the same
    direct download the earlier OpenBSD rows use)."""
    package = (
        "https://github.com/bceverly/sysmanage-agent/releases/download/"
        "${LATEST}/sysmanage-agent-${VERSION}-openbsd"
        + version.replace(".", "")
        + ".tgz"
    )
    return json.dumps(
        [
            "LATEST=$(ftp -V -o - "
            + _API_URL
            + ' | grep -o \'"tag_name": *"[^"]*"\' | grep -o \'v[0-9.]*\')',
            "VERSION=${LATEST#v}",
            "ftp -V -o /tmp/sysmanage-agent.tgz " + package,
            "pkg_add -D unsigned /tmp/sysmanage-agent.tgz",
            "rm -f /tmp/sysmanage-agent.tgz",
            "rcctl enable sysmanage_agent",
            "rcctl start sysmanage_agent",
        ]
    )


def _row(version: str) -> dict:
    nodot = version.replace(".", "")
    newest = version == SUPPORTED[-1]
    return {
        "child_type": "vmm",
        "distribution_name": "OpenBSD",
        "distribution_version": version,
        "display_name": f"OpenBSD {version}",
        "install_identifier": (
            f"https://ftp.openbsd.org/pub/OpenBSD/{version}/amd64/install{nodot}.iso"
        ),
        "agent_install_method": "pkg_add",
        "agent_install_commands": _commands(version),
        "notes": (
            f"OpenBSD {version} - "
            + ("current release" if newest else "previous release, still supported")
            + " with VMM support"
        ),
    }


_KEY = (
    "child_type = :child_type AND distribution_name = :distribution_name "
    "AND distribution_version = :distribution_version"
)


def upgrade() -> None:
    bind = op.get_bind()
    now = "CURRENT_TIMESTAMP" if bind.dialect.name == "sqlite" else "NOW()"
    true = "1" if bind.dialect.name == "sqlite" else "true"
    false = "0" if bind.dialect.name == "sqlite" else "false"
    for version in SUPPORTED:
        row = _row(version)
        exists = bind.execute(
            text(f"SELECT COUNT(*) FROM child_host_distribution WHERE {_KEY}"), row
        ).scalar()
        if exists:
            bind.execute(
                text(
                    "UPDATE child_host_distribution SET display_name = :display_name, "
                    "install_identifier = :install_identifier, "
                    "agent_install_method = :agent_install_method, "
                    "agent_install_commands = :agent_install_commands, notes = :notes, "
                    f"is_active = {true}, updated_at = {now} WHERE {_KEY}"
                ),
                row,
            )
        else:
            bind.execute(
                text(
                    "INSERT INTO child_host_distribution (id, child_type, "
                    "distribution_name, distribution_version, display_name, "
                    "install_identifier, executable_name, agent_install_method, "
                    "agent_install_commands, notes, is_active, created_at, updated_at) "
                    "VALUES (:id, :child_type, :distribution_name, "
                    ":distribution_version, :display_name, :install_identifier, NULL, "
                    ":agent_install_method, :agent_install_commands, :notes, "
                    f"{true}, {now}, {now})"
                ),
                dict(row, id=str(uuid.uuid4())),
            )
    bind.execute(
        text(
            f"UPDATE child_host_distribution SET is_active = {false}, "
            f"updated_at = {now} WHERE child_type = 'vmm' "
            "AND distribution_name = 'OpenBSD' "
            "AND distribution_version NOT IN ('7.9', '8.0')"
        )
    )


def downgrade() -> None:
    # Back to the earlier catalog: the older rows offered again, 7.9 and 8.0
    # withdrawn -- deactivated, not deleted, since child hosts may name them.
    bind = op.get_bind()
    now = "CURRENT_TIMESTAMP" if bind.dialect.name == "sqlite" else "NOW()"
    true = "1" if bind.dialect.name == "sqlite" else "true"
    false = "0" if bind.dialect.name == "sqlite" else "false"
    bind.execute(
        text(
            f"UPDATE child_host_distribution SET is_active = {true}, "
            f"updated_at = {now} WHERE child_type = 'vmm' "
            "AND distribution_name = 'OpenBSD' "
            "AND distribution_version NOT IN ('7.9', '8.0')"
        )
    )
    bind.execute(
        text(
            f"UPDATE child_host_distribution SET is_active = {false}, "
            f"updated_at = {now} WHERE child_type = 'vmm' "
            "AND distribution_name = 'OpenBSD' "
            "AND distribution_version IN ('7.9', '8.0')"
        )
    )
