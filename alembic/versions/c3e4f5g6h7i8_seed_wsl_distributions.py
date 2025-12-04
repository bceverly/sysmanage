"""seed_wsl_distributions

Revision ID: c3e4f5g6h7i8
Revises: b2d3e4f5g6h7
Create Date: 2025-12-02 10:00:00.000000

This migration seeds the child_host_distribution table with commonly
available WSL distributions from the Microsoft Store.

"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "c3e4f5g6h7i8"
down_revision: Union[str, None] = "b2d3e4f5g6h7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# WSL distributions available from Microsoft
WSL_DISTRIBUTIONS = [
    {
        "child_type": "wsl",
        "distribution_name": "Ubuntu",
        "distribution_version": "24.04",
        "display_name": "Ubuntu 24.04 LTS",
        "install_identifier": "Ubuntu-24.04",
        "executable_name": "ubuntu2404.exe",
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Ubuntu 24.04 LTS (Noble Numbat) - Long Term Support",
    },
    {
        "child_type": "wsl",
        "distribution_name": "Ubuntu",
        "distribution_version": "22.04",
        "display_name": "Ubuntu 22.04 LTS",
        "install_identifier": "Ubuntu-22.04",
        "executable_name": "ubuntu2204.exe",
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Ubuntu 22.04 LTS (Jammy Jellyfish) - Long Term Support",
    },
    {
        "child_type": "wsl",
        "distribution_name": "Ubuntu",
        "distribution_version": "20.04",
        "display_name": "Ubuntu 20.04 LTS",
        "install_identifier": "Ubuntu-20.04",
        "executable_name": "ubuntu2004.exe",
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Ubuntu 20.04 LTS (Focal Fossa) - Long Term Support",
    },
    {
        "child_type": "wsl",
        "distribution_name": "Debian",
        "distribution_version": "12",
        "display_name": "Debian",
        "install_identifier": "Debian",
        "executable_name": "debian.exe",
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Debian GNU/Linux (Bookworm)",
    },
    {
        "child_type": "wsl",
        "distribution_name": "Kali",
        "distribution_version": "rolling",
        "display_name": "Kali Linux",
        "install_identifier": "kali-linux",
        "executable_name": "kali.exe",
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Kali Linux - Security and penetration testing distribution",
    },
    {
        "child_type": "wsl",
        "distribution_name": "openSUSE",
        "distribution_version": "Tumbleweed",
        "display_name": "openSUSE Tumbleweed",
        "install_identifier": "openSUSE-Tumbleweed",
        "executable_name": "opensuse-tumbleweed.exe",
        "agent_install_method": "zypper",
        "agent_install_commands": """[
            "zypper refresh",
            "zypper install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "openSUSE Tumbleweed - Rolling release",
    },
    {
        "child_type": "wsl",
        "distribution_name": "openSUSE",
        "distribution_version": "Leap-15",
        "display_name": "openSUSE Leap 15",
        "install_identifier": "openSUSE-Leap-15",
        "executable_name": "opensuse-leap-15.exe",
        "agent_install_method": "zypper",
        "agent_install_commands": """[
            "zypper refresh",
            "zypper install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "openSUSE Leap 15 - Stable enterprise release",
    },
    {
        "child_type": "wsl",
        "distribution_name": "SUSE",
        "distribution_version": "15",
        "display_name": "SUSE Linux Enterprise 15",
        "install_identifier": "SLES-15",
        "executable_name": "sles-15.exe",
        "agent_install_method": "zypper",
        "agent_install_commands": """[
            "zypper refresh",
            "zypper install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "SUSE Linux Enterprise Server 15",
    },
    {
        "child_type": "wsl",
        "distribution_name": "Fedora",
        "distribution_version": "39",
        "display_name": "Fedora",
        "install_identifier": "Fedora",
        "executable_name": "fedora.exe",
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Fedora Linux",
    },
    {
        "child_type": "wsl",
        "distribution_name": "AlmaLinux",
        "distribution_version": "9",
        "display_name": "AlmaLinux 9",
        "install_identifier": "AlmaLinux-9",
        "executable_name": "almalinux-9.exe",
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "AlmaLinux 9 - RHEL-compatible enterprise Linux",
    },
    {
        "child_type": "wsl",
        "distribution_name": "RockyLinux",
        "distribution_version": "9",
        "display_name": "Rocky Linux 9",
        "install_identifier": "RockyLinux-9",
        "executable_name": "rockylinux-9.exe",
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Rocky Linux 9 - RHEL-compatible enterprise Linux",
    },
    {
        "child_type": "wsl",
        "distribution_name": "Oracle",
        "distribution_version": "9",
        "display_name": "Oracle Linux 9",
        "install_identifier": "OracleLinux_9_1",
        "executable_name": "oraclelinux.exe",
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y curl",
            "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
        ]""",
        "notes": "Oracle Linux 9",
    },
]


def upgrade() -> None:
    """Seed child_host_distribution table with WSL distributions."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for dist in WSL_DISTRIBUTIONS:
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
    """Remove seeded WSL distributions."""
    bind = op.get_bind()

    # Remove only the distributions we seeded
    for dist in WSL_DISTRIBUTIONS:
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
