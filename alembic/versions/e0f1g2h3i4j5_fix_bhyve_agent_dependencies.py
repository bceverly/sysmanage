"""fix_bhyve_agent_dependencies

Revision ID: e0f1g2h3i4j5
Revises: d9e0f1g2h3i4
Create Date: 2026-01-14 10:00:00.000000

This migration fixes the agent install commands to pre-install all required
dependencies (python3-pip, python3-venv) before dpkg to avoid apt-get install -f
removing the package when dependencies can't be resolved.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "e0f1g2h3i4j5"
down_revision: Union[str, None] = "d9e0f1g2h3i4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Ubuntu commands with all dependencies pre-installed
UBUNTU_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "apt-get update",
    "apt-get install -y python3 python3-pip python3-venv curl jq",
    "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -sSL --retry 3 -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "test $(stat -c%s /tmp/sysmanage-agent_${VERSION}_amd64.deb 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

# Debian commands with all dependencies pre-installed
DEBIAN_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "apt-get update",
    "apt-get install -y python3 python3-pip python3-venv curl jq",
    "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -sSL --retry 3 -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "test $(stat -c%s /tmp/sysmanage-agent_${VERSION}_amd64.deb 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""


def upgrade() -> None:
    """Add python3-venv to dependencies pre-install."""
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
    """Revert to previous commands without python3-venv pre-install."""
    bind = op.get_bind()

    # Previous Ubuntu commands
    ubuntu_commands_old = """[
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

    # Previous Debian commands
    debian_commands_old = """[
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

    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'Ubuntu'
            """
        ),
        {"commands": ubuntu_commands_old},
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
        {"commands": debian_commands_old},
    )
