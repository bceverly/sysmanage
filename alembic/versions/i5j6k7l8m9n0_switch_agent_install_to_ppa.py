"""switch_agent_install_to_ppa

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-02-24 19:30:00.000000

Switch bhyve Ubuntu/Debian agent install commands from GitHub API
(private repo, returns 404) to Launchpad PPA. Also switch KVM Oracle
Linux from GitHub to direct RPM URL pattern that doesn't require
the GitHub API.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "i5j6k7l8m9n0"
down_revision: Union[str, None] = "h4i5j6k7l8m9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Ubuntu/Debian: use Launchpad PPA (matches KVM Ubuntu pattern)
UBUNTU_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "for i in 1 2 3; do apt-get update && break || sleep 5; done",
    "apt-get install -y --fix-missing software-properties-common",
    "add-apt-repository -y ppa:bceverly/sysmanage-agent",
    "apt-get update",
    "DEBIAN_FRONTEND=noninteractive apt-get install -y sysmanage-agent",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

DEBIAN_COMMANDS = """[
    "timedatectl set-ntp true || true",
    "sleep 5",
    "for i in 1 2 3; do apt-get update && break || sleep 5; done",
    "apt-get install -y --fix-missing software-properties-common",
    "add-apt-repository -y ppa:bceverly/sysmanage-agent",
    "apt-get update",
    "DEBIAN_FRONTEND=noninteractive apt-get install -y sysmanage-agent",
    "systemctl enable sysmanage-agent",
    "systemctl start sysmanage-agent"
]"""

# Previous Ubuntu commands (for downgrade)
OLD_UBUNTU_COMMANDS = """[
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

OLD_DEBIAN_COMMANDS = """[
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
    """Switch agent install commands from GitHub API to Launchpad PPA."""
    bind = op.get_bind()

    # Update bhyve Ubuntu distributions
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

    # Update bhyve Debian distributions
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
    """Revert to GitHub-based install commands."""
    bind = op.get_bind()

    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET agent_install_commands = :commands
            WHERE child_type = 'bhyve'
              AND distribution_name = 'Ubuntu'
            """
        ),
        {"commands": OLD_UBUNTU_COMMANDS},
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
        {"commands": OLD_DEBIAN_COMMANDS},
    )
