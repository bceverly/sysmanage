"""add_ntp_sync_to_bhyve_commands

Revision ID: d9e0f1g2h3i4
Revises: c8d9e0f1g2h3
Create Date: 2026-01-08 21:50:00.000000

This migration adds NTP time sync commands before apt-get to fix clock skew
issues that cause apt to fail with "Release file is not valid yet" errors.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "d9e0f1g2h3i4"
down_revision: Union[str, None] = "c8d9e0f1g2h3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Ubuntu commands with NTP sync before apt-get
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

# Debian commands with NTP sync before apt-get
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


def upgrade() -> None:
    """Add NTP time sync commands before apt-get."""
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


def downgrade() -> None:
    """Remove NTP sync commands (revert to previous version)."""
    bind = op.get_bind()

    # Revert to commands without NTP sync
    ubuntu_commands_no_ntp = """[
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

    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'Ubuntu'
            """
        ),
        {"commands": ubuntu_commands_no_ntp},
    )

    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'Debian'
            """
        ),
        {"commands": ubuntu_commands_no_ntp},
    )
