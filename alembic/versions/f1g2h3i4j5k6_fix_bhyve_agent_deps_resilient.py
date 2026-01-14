"""fix_bhyve_agent_deps_resilient

Revision ID: f1g2h3i4j5k6
Revises: d9e0f1g2h3i4
Create Date: 2026-01-14 11:00:00.000000

This migration fixes the agent install commands to:
1. Pre-install all required dependencies (python3-pip, python3-venv)
2. Add --fix-missing flag for resilience against flaky mirrors
3. Add retry logic for apt-get update
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "f1g2h3i4j5k6"
down_revision: Union[str, None] = "e0f1g2h3i4j5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Ubuntu commands with all dependencies pre-installed and retry logic
UBUNTU_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "for i in 1 2 3; do apt-get update && break || sleep 5; done",
    "apt-get install -y --fix-missing python3 python3-pip python3-venv curl jq",
    "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -sSL --retry 3 -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "test $(stat -c%s /tmp/sysmanage-agent_${VERSION}_amd64.deb 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

# Debian commands with all dependencies pre-installed and retry logic
DEBIAN_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "for i in 1 2 3; do apt-get update && break || sleep 5; done",
    "apt-get install -y --fix-missing python3 python3-pip python3-venv curl jq",
    "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
    "VERSION=${LATEST#v}",
    "curl -sSL --retry 3 -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
    "test $(stat -c%s /tmp/sysmanage-agent_${VERSION}_amd64.deb 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""


def upgrade() -> None:
    """Add python3-venv to dependencies and improve resilience."""
    bind = op.get_bind()

    # Update Ubuntu distributions (idempotent - just overwrites)
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

    # Update Debian distributions (idempotent - just overwrites)
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
    """Revert to previous commands from e0f1g2h3i4j5."""
    bind = op.get_bind()

    # Previous Ubuntu commands (from e0f1g2h3i4j5 - has python3-venv but no retry)
    ubuntu_commands_old = """[
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

    # Previous Debian commands (from e0f1g2h3i4j5 - has python3-venv but no retry)
    debian_commands_old = """[
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
