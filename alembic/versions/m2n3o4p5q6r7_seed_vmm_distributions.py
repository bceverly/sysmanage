"""seed_vmm_distributions

Revision ID: m2n3o4p5q6r7
Revises: l1m2n3o4p5q6
Create Date: 2025-12-06 12:00:00.000000

This migration seeds the child_host_distribution table with commonly
available VMM virtual machine operating systems for OpenBSD hosts.

VMM VMs are full virtual machines (not containers) that require:
- ISO image download and installation OR
- Autoinstall/preseed configuration for unattended installation
- SSH-based agent installation after OS is running

"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "m2n3o4p5q6r7"
down_revision: Union[str, None] = "l1m2n3o4p5q6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# VMM distributions - full VMs that can be installed on OpenBSD VMM/vmd
# install_identifier contains the ISO URL or installation method
VMM_DISTRIBUTIONS = [
    {
        "child_type": "vmm",
        "distribution_name": "OpenBSD",
        "distribution_version": "7.6",
        "display_name": "OpenBSD 7.6",
        "install_identifier": "https://cdn.openbsd.org/pub/OpenBSD/7.6/amd64/install76.iso",
        "executable_name": None,
        "agent_install_method": "pkg_add",
        "agent_install_commands": """[
            "pkg_add python3",
            "pkg_add py3-pip",
            "pip3 install sysmanage-agent",
            "rcctl enable sysmanage_agent",
            "rcctl start sysmanage_agent"
        ]""",
        "notes": "OpenBSD 7.6 - Native VMM guest OS with serial console support",
    },
    {
        "child_type": "vmm",
        "distribution_name": "OpenBSD",
        "distribution_version": "7.5",
        "display_name": "OpenBSD 7.5",
        "install_identifier": "https://cdn.openbsd.org/pub/OpenBSD/7.5/amd64/install75.iso",
        "executable_name": None,
        "agent_install_method": "pkg_add",
        "agent_install_commands": """[
            "pkg_add python3",
            "pkg_add py3-pip",
            "pip3 install sysmanage-agent",
            "rcctl enable sysmanage_agent",
            "rcctl start sysmanage_agent"
        ]""",
        "notes": "OpenBSD 7.5 - Previous stable release",
    },
    {
        "child_type": "vmm",
        "distribution_name": "Debian",
        "distribution_version": "12",
        "display_name": "Debian 12 (Bookworm)",
        "install_identifier": "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.8.0-amd64-netinst.iso",
        "executable_name": None,
        "agent_install_method": "apt_obs",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl gnupg",
            "curl -fsSL https://download.opensuse.org/repositories/home:/bceverly:/sysmanage-agent/Debian_12/Release.key | gpg --dearmor -o /usr/share/keyrings/sysmanage-agent.gpg",
            "echo 'deb [signed-by=/usr/share/keyrings/sysmanage-agent.gpg] https://download.opensuse.org/repositories/home:/bceverly:/sysmanage-agent/Debian_12/ /' > /etc/apt/sources.list.d/sysmanage-agent.list",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Debian 12 (Bookworm) - Requires console=ttyS0 kernel parameter for serial console",
    },
    {
        "child_type": "vmm",
        "distribution_name": "Ubuntu Server",
        "distribution_version": "24.04",
        "display_name": "Ubuntu Server 24.04 LTS",
        "install_identifier": "https://releases.ubuntu.com/24.04/ubuntu-24.04.1-live-server-amd64.iso",
        "executable_name": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y software-properties-common",
            "add-apt-repository -y ppa:bceverly/sysmanage-agent",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Ubuntu Server 24.04 LTS - Requires console=ttyS0 kernel parameter for serial console",
    },
    {
        "child_type": "vmm",
        "distribution_name": "Ubuntu Server",
        "distribution_version": "22.04",
        "display_name": "Ubuntu Server 22.04 LTS",
        "install_identifier": "https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso",
        "executable_name": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y software-properties-common",
            "add-apt-repository -y ppa:bceverly/sysmanage-agent",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Ubuntu Server 22.04 LTS - Requires console=ttyS0 kernel parameter for serial console",
    },
    {
        "child_type": "vmm",
        "distribution_name": "Alpine Linux",
        "distribution_version": "3.20",
        "display_name": "Alpine Linux 3.20",
        "install_identifier": "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/alpine-virt-3.20.3-x86_64.iso",
        "executable_name": None,
        "agent_install_method": "apk",
        "agent_install_commands": """[
            "apk update",
            "apk add python3 py3-pip",
            "pip3 install sysmanage-agent",
            "rc-update add sysmanage_agent default",
            "rc-service sysmanage_agent start"
        ]""",
        "notes": "Alpine Linux 3.20 - Lightweight, security-focused. Uses alpine-virt for VMM compatibility",
    },
]


def upgrade() -> None:
    """Seed child_host_distribution table with VMM distributions."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for dist in VMM_DISTRIBUTIONS:
        dist_id = str(uuid.uuid4())

        # Check if this distribution already exists (idempotent)
        result = bind.execute(
            text(
                """
                SELECT COUNT(*) FROM child_host_distribution
                WHERE child_type = :child_type
                  AND distribution_name = :distribution_name
                  AND distribution_version = :distribution_version
                """
            ),
            {
                "child_type": dist["child_type"],
                "distribution_name": dist["distribution_name"],
                "distribution_version": dist["distribution_version"],
            },
        )
        exists = result.scalar() > 0

        if exists:
            # Update existing record
            if is_sqlite:
                bind.execute(
                    text(
                        """
                        UPDATE child_host_distribution SET
                            display_name = :display_name,
                            install_identifier = :install_identifier,
                            executable_name = :executable_name,
                            agent_install_method = :agent_install_method,
                            agent_install_commands = :agent_install_commands,
                            notes = :notes,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE child_type = :child_type
                          AND distribution_name = :distribution_name
                          AND distribution_version = :distribution_version
                        """
                    ),
                    {
                        "child_type": dist["child_type"],
                        "distribution_name": dist["distribution_name"],
                        "distribution_version": dist["distribution_version"],
                        "display_name": dist["display_name"],
                        "install_identifier": dist["install_identifier"],
                        "executable_name": dist["executable_name"],
                        "agent_install_method": dist["agent_install_method"],
                        "agent_install_commands": dist["agent_install_commands"],
                        "notes": dist["notes"],
                    },
                )
            else:
                bind.execute(
                    text(
                        """
                        UPDATE child_host_distribution SET
                            display_name = :display_name,
                            install_identifier = :install_identifier,
                            executable_name = :executable_name,
                            agent_install_method = :agent_install_method,
                            agent_install_commands = :agent_install_commands,
                            notes = :notes,
                            updated_at = NOW()
                        WHERE child_type = :child_type
                          AND distribution_name = :distribution_name
                          AND distribution_version = :distribution_version
                        """
                    ),
                    {
                        "child_type": dist["child_type"],
                        "distribution_name": dist["distribution_name"],
                        "distribution_version": dist["distribution_version"],
                        "display_name": dist["display_name"],
                        "install_identifier": dist["install_identifier"],
                        "executable_name": dist["executable_name"],
                        "agent_install_method": dist["agent_install_method"],
                        "agent_install_commands": dist["agent_install_commands"],
                        "notes": dist["notes"],
                    },
                )
        else:
            # Insert new record
            if is_sqlite:
                bind.execute(
                    text(
                        """
                        INSERT INTO child_host_distribution (
                            id, child_type, distribution_name, distribution_version,
                            display_name, install_identifier, executable_name,
                            agent_install_method, agent_install_commands, notes,
                            is_active, created_at, updated_at
                        ) VALUES (
                            :id, :child_type, :distribution_name, :distribution_version,
                            :display_name, :install_identifier, :executable_name,
                            :agent_install_method, :agent_install_commands, :notes,
                            1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "id": dist_id,
                        "child_type": dist["child_type"],
                        "distribution_name": dist["distribution_name"],
                        "distribution_version": dist["distribution_version"],
                        "display_name": dist["display_name"],
                        "install_identifier": dist["install_identifier"],
                        "executable_name": dist["executable_name"],
                        "agent_install_method": dist["agent_install_method"],
                        "agent_install_commands": dist["agent_install_commands"],
                        "notes": dist["notes"],
                    },
                )
            else:
                bind.execute(
                    text(
                        """
                        INSERT INTO child_host_distribution (
                            id, child_type, distribution_name, distribution_version,
                            display_name, install_identifier, executable_name,
                            agent_install_method, agent_install_commands, notes,
                            is_active, created_at, updated_at
                        ) VALUES (
                            :id, :child_type, :distribution_name, :distribution_version,
                            :display_name, :install_identifier, :executable_name,
                            :agent_install_method, :agent_install_commands, :notes,
                            true, NOW(), NOW()
                        )
                        """
                    ),
                    {
                        "id": dist_id,
                        "child_type": dist["child_type"],
                        "distribution_name": dist["distribution_name"],
                        "distribution_version": dist["distribution_version"],
                        "display_name": dist["display_name"],
                        "install_identifier": dist["install_identifier"],
                        "executable_name": dist["executable_name"],
                        "agent_install_method": dist["agent_install_method"],
                        "agent_install_commands": dist["agent_install_commands"],
                        "notes": dist["notes"],
                    },
                )


def downgrade() -> None:
    """Remove seeded VMM distributions."""
    bind = op.get_bind()

    # Remove only the distributions we seeded
    for dist in VMM_DISTRIBUTIONS:
        bind.execute(
            text(
                """
            DELETE FROM child_host_distribution
            WHERE child_type = :child_type
              AND distribution_name = :distribution_name
              AND distribution_version = :distribution_version
            """
            ),
            {
                "child_type": dist["child_type"],
                "distribution_name": dist["distribution_name"],
                "distribution_version": dist["distribution_version"],
            },
        )
