"""fix_bhyve_agent_install_escaping

Revision ID: b7c8d9e0f1g2
Revises: a6b7c8d9e0f1
Create Date: 2026-01-07 22:00:00.000000

This migration fixes the JSON escaping in bhyve distribution agent_install_commands.
The original migration had double-escaped quotes (\\") instead of properly escaped
quotes (\"), causing JSON parsing to fail.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1g2"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Corrected agent install commands - use jq to avoid quote escaping issues
UBUNTU_COMMANDS = """[
    "apt-get update",
    "apt-get install -y python3 python3-pip python3-venv curl jq",
    "LATEST=$(curl -s https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -L -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb || apt-get install -f -y",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

DEBIAN_COMMANDS = """[
    "apt-get update",
    "apt-get install -y python3 python3-pip python3-venv curl jq",
    "LATEST=$(curl -s https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -L -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb || apt-get install -f -y",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

FREEBSD_COMMANDS = """[
    "pkg install -y jq",
    "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
    "pkg install -y python311 py311-pip py311-aiosqlite py311-cryptography py311-pyyaml py311-aiohttp py311-sqlalchemy20 py311-alembic py311-websockets",
    "pkg add /tmp/sysmanage-agent-${VERSION}.pkg || true",
    "cd / && tar -xf /tmp/sysmanage-agent-${VERSION}.pkg --include='usr/*'",
    "sysrc sysmanage_agent_enable=YES",
    "sysrc sysmanage_agent_user=root",
    "service sysmanage_agent restart 2>/dev/null || service sysmanage_agent start"
]"""

FREEBSD_13_COMMANDS = """[
    "pkg install -y jq",
    "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
    "pkg install -y python39 py39-pip py39-aiosqlite py39-cryptography py39-pyyaml py39-aiohttp py39-sqlalchemy20 py39-alembic py39-websockets",
    "pkg add /tmp/sysmanage-agent-${VERSION}.pkg || true",
    "cd / && tar -xf /tmp/sysmanage-agent-${VERSION}.pkg --include='usr/*'",
    "sysrc sysmanage_agent_enable=YES",
    "sysrc sysmanage_agent_user=root",
    "service sysmanage_agent restart 2>/dev/null || service sysmanage_agent start"
]"""


def upgrade() -> None:
    """Fix the JSON escaping in bhyve agent_install_commands."""
    bind = op.get_bind()

    # Update Ubuntu distributions
    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'Ubuntu'
            """
        ),
        {"commands": UBUNTU_COMMANDS},
    )

    # Update Debian distributions
    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'Debian'
            """
        ),
        {"commands": DEBIAN_COMMANDS},
    )

    # Update FreeBSD 14.x distributions
    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'FreeBSD'
              AND distribution_version IN ('14.1', '14.2')
            """
        ),
        {"commands": FREEBSD_COMMANDS},
    )

    # Update FreeBSD 13.x distributions (uses python39)
    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'FreeBSD'
              AND distribution_version = '13.4'
            """
        ),
        {"commands": FREEBSD_13_COMMANDS},
    )


def downgrade() -> None:
    """No downgrade needed - the original data was broken anyway."""
    pass
