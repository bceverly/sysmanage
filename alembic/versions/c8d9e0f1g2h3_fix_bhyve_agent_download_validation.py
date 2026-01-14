"""fix_bhyve_agent_download_validation

Revision ID: c8d9e0f1g2h3
Revises: b7c8d9e0f1g2
Create Date: 2026-01-08 21:15:00.000000

This migration fixes the agent install commands for bhyve distributions:
1. Adds download validation (checks file size before installing)
2. Adds retry logic for failed downloads
3. Removes python3-venv which has dependency issues on Ubuntu 24.04
4. Adds NTP time sync before apt-get to fix clock skew issues
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1g2h3"
down_revision: Union[str, None] = "b7c8d9e0f1g2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Fixed Ubuntu/Debian commands with download validation
# - Removed python3-venv which has dependency issues
# - Added file size check before dpkg to catch download failures
# - Added retry logic for curl
# - Added NTP time sync before apt-get to fix clock skew issues
UBUNTU_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "apt-get update",
    "apt-get install -y python3 python3-pip curl jq",
    "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -sSL --retry 3 -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "test $(stat -c%s /tmp/sysmanage-agent_${VERSION}_amd64.deb 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb || apt-get install -f -y",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

DEBIAN_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "apt-get update",
    "apt-get install -y python3 python3-pip curl jq",
    "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -sSL --retry 3 -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "test $(stat -c%s /tmp/sysmanage-agent_${VERSION}_amd64.deb 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb || apt-get install -f -y",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

# FreeBSD commands with download validation
FREEBSD_COMMANDS = """[
    "pkg install -y jq",
    "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
    "test $(stat -f%z /tmp/sysmanage-agent-${VERSION}.pkg 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
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
    "test $(stat -f%z /tmp/sysmanage-agent-${VERSION}.pkg 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "pkg install -y python39 py39-pip py39-aiosqlite py39-cryptography py39-pyyaml py39-aiohttp py39-sqlalchemy20 py39-alembic py39-websockets",
    "pkg add /tmp/sysmanage-agent-${VERSION}.pkg || true",
    "cd / && tar -xf /tmp/sysmanage-agent-${VERSION}.pkg --include='usr/*'",
    "sysrc sysmanage_agent_enable=YES",
    "sysrc sysmanage_agent_user=root",
    "service sysmanage_agent restart 2>/dev/null || service sysmanage_agent start"
]"""


def upgrade() -> None:
    """Fix the agent install commands with download validation."""
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
    """No downgrade needed."""
    pass
