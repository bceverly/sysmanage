"""seed_lxd_distributions

Revision ID: k0l1m2n3o4p5
Revises: j9k0l1m2n3o4
Create Date: 2025-12-05 10:00:00.000000

This migration seeds the child_host_distribution table with commonly
available LXD container images from ubuntu: and images: remotes.

"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "k0l1m2n3o4p5"
down_revision: Union[str, None] = "j9k0l1m2n3o4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# LXD distributions available from ubuntu: and images: remotes
LXD_DISTRIBUTIONS = [
    {
        "child_type": "lxd",
        "distribution_name": "Ubuntu",
        "distribution_version": "24.04",
        "display_name": "Ubuntu 24.04 LTS",
        "install_identifier": "ubuntu:24.04",
        "executable_name": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y software-properties-common",
            "add-apt-repository -y ppa:bceverly/sysmanage-agent",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Ubuntu 24.04 LTS (Noble Numbat) - Long Term Support",
    },
    {
        "child_type": "lxd",
        "distribution_name": "Ubuntu",
        "distribution_version": "22.04",
        "display_name": "Ubuntu 22.04 LTS",
        "install_identifier": "ubuntu:22.04",
        "executable_name": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y software-properties-common",
            "add-apt-repository -y ppa:bceverly/sysmanage-agent",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Ubuntu 22.04 LTS (Jammy Jellyfish) - Long Term Support",
    },
    {
        "child_type": "lxd",
        "distribution_name": "Debian",
        "distribution_version": "12",
        "display_name": "Debian 12 (Bookworm)",
        "install_identifier": "images:debian/12",
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
        "notes": "Debian 12 (Bookworm) - Stable release",
    },
    {
        "child_type": "lxd",
        "distribution_name": "Fedora",
        "distribution_version": "40",
        "display_name": "Fedora 40",
        "install_identifier": "images:fedora/40",
        "executable_name": None,
        "agent_install_method": "dnf_copr",
        "agent_install_commands": """[
            "dnf install -y dnf-plugins-core",
            "dnf copr enable -y bceverly/sysmanage-agent",
            "dnf install -y sysmanage-agent"
        ]""",
        "notes": "Fedora 40 - Current stable release",
    },
    {
        "child_type": "lxd",
        "distribution_name": "Rocky Linux",
        "distribution_version": "9",
        "display_name": "Rocky Linux 9",
        "install_identifier": "images:rockylinux/9",
        "executable_name": None,
        "agent_install_method": "dnf_copr",
        "agent_install_commands": """[
            "dnf install -y dnf-plugins-core epel-release",
            "dnf copr enable -y bceverly/sysmanage-agent",
            "dnf install -y sysmanage-agent"
        ]""",
        "notes": "Rocky Linux 9 - RHEL-compatible enterprise Linux",
    },
    {
        "child_type": "lxd",
        "distribution_name": "AlmaLinux",
        "distribution_version": "9",
        "display_name": "AlmaLinux 9",
        "install_identifier": "images:almalinux/9",
        "executable_name": None,
        "agent_install_method": "dnf_copr",
        "agent_install_commands": """[
            "dnf install -y dnf-plugins-core epel-release",
            "dnf copr enable -y bceverly/sysmanage-agent",
            "dnf install -y sysmanage-agent"
        ]""",
        "notes": "AlmaLinux 9 - RHEL-compatible enterprise Linux",
    },
]


def upgrade() -> None:
    """Seed child_host_distribution table with LXD distributions."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for dist in LXD_DISTRIBUTIONS:
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
    """Remove seeded LXD distributions."""
    bind = op.get_bind()

    # Remove only the distributions we seeded
    for dist in LXD_DISTRIBUTIONS:
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
