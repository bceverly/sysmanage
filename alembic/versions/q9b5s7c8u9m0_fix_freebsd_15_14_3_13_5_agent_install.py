# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""fix_freebsd_15_14_3_13_5_agent_install

Revision ID: q9b5s7c8u9m0
Revises: p8a4r5b6t7l8
Create Date: 2026-05-01 16:55:00.000000

The earlier z5a6b7c8d9e0 migration switched FreeBSD KVM agent_install_commands
from ``pip install sysmanage-agent`` (which doesn't exist on PyPI and never
worked) to ``fetch + pkg add`` from the GitHub release.  But it only patched
the older versions (14.2/14.1/14.0/13.4/13.3) — the newer 15.0/14.3/13.5
distributions were seeded later by y4z5a6b7c8d9 with the same broken
commands and never got caught up.  Spawning a child host on any of those
versions silently failed: cloud-init "succeeded" because pip install no-ops,
but service sysmanage_agent start failed (no rc.d script) so the agent
never registered.

Idempotent: re-runs over the same rows simply re-set the same string.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "q9b5s7c8u9m0"
down_revision: Union[str, None] = "p8a4r5b6t7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FREEBSD_VERSIONS = ["15.0", "14.3", "13.5"]

NEW_INSTALL_COMMANDS = """[
    "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\"tag_name\\\": *\\\"[^\\\"]*\\\"' | grep -o 'v[0-9.]*')",
    "VERSION=${LATEST#v}",
    "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
    "pkg add /tmp/sysmanage-agent-${VERSION}.pkg",
    "rm /tmp/sysmanage-agent-${VERSION}.pkg",
    "sysrc sysmanage_agent_enable=YES",
    "service sysmanage_agent start"
]"""

OLD_INSTALL_COMMANDS = """[
    "pkg update",
    "pkg install -y python311 py311-pip",
    "pip install sysmanage-agent",
    "sysrc sysmanage_agent_enable=YES",
    "service sysmanage_agent start"
]"""


def _update_commands(bind, version: str, commands: str) -> None:
    is_sqlite = bind.dialect.name == "sqlite"
    timestamp_expr = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
    bind.execute(
        text(
            f"""
            UPDATE child_host_distribution SET
                agent_install_commands = :agent_install_commands,
                updated_at = {timestamp_expr}
            WHERE child_type = 'kvm'
              AND distribution_name = 'FreeBSD'
              AND distribution_version = :version
            """
        ),
        {"version": version, "agent_install_commands": commands},
    )


def upgrade() -> None:
    bind = op.get_bind()
    for version in FREEBSD_VERSIONS:
        _update_commands(bind, version, NEW_INSTALL_COMMANDS)


def downgrade() -> None:
    bind = op.get_bind()
    for version in FREEBSD_VERSIONS:
        _update_commands(bind, version, OLD_INSTALL_COMMANDS)
