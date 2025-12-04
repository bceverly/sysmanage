"""Update WSL agent installation commands with real package manager commands

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2025-12-02 18:00:00.000000

This migration updates the child_host_distribution table with real agent
installation commands for each package manager type:
- apt (Ubuntu, Debian, Kali): Uses Launchpad PPA
- zypper (openSUSE, SLES): Uses OBS repository
- dnf (Fedora, AlmaLinux, Rocky, Oracle): Uses COPR repository

"""

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "f6g7h8i9j0k1"
down_revision: Union[str, None] = "e5f6g7h8i9j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Real agent installation commands by package manager type
APT_INSTALL_COMMANDS = json.dumps([
    "apt-get update",
    "apt-get install -y software-properties-common",
    "add-apt-repository -y ppa:bceverly/sysmanage",
    "apt-get update",
    "apt-get install -y sysmanage-agent"
])

ZYPPER_INSTALL_COMMANDS = json.dumps([
    "zypper refresh",
    "zypper addrepo -f https://download.opensuse.org/repositories/home:/bceverly/openSUSE_Tumbleweed/home:bceverly.repo",
    "zypper --gpg-auto-import-keys refresh",
    "zypper install -y sysmanage-agent"
])

ZYPPER_LEAP_INSTALL_COMMANDS = json.dumps([
    "zypper refresh",
    "zypper addrepo -f https://download.opensuse.org/repositories/home:/bceverly/15.5/home:bceverly.repo",
    "zypper --gpg-auto-import-keys refresh",
    "zypper install -y sysmanage-agent"
])

ZYPPER_SLES_INSTALL_COMMANDS = json.dumps([
    "zypper refresh",
    "zypper addrepo -f https://download.opensuse.org/repositories/home:/bceverly/SLE_15/home:bceverly.repo",
    "zypper --gpg-auto-import-keys refresh",
    "zypper install -y sysmanage-agent"
])

DNF_INSTALL_COMMANDS = json.dumps([
    "dnf install -y dnf-plugins-core",
    "dnf copr enable -y bceverly/sysmanage",
    "dnf install -y sysmanage-agent"
])


def upgrade() -> None:
    """Update agent_install_commands with real package manager commands."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Update APT-based distributions (Ubuntu, Debian, Kali)
    apt_distros = [
        ("Ubuntu", "24.04"),
        ("Ubuntu", "22.04"),
        ("Ubuntu", "20.04"),
        ("Debian", "12"),
        ("Kali", "rolling"),
    ]

    for dist_name, dist_version in apt_distros:
        if is_sqlite:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_method = 'apt_launchpad',
                        agent_install_commands = :commands,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE distribution_name = :dist_name
                      AND distribution_version = :dist_version
                    """
                ),
                {
                    "dist_name": dist_name,
                    "dist_version": dist_version,
                    "commands": APT_INSTALL_COMMANDS,
                },
            )
        else:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_method = 'apt_launchpad',
                        agent_install_commands = :commands,
                        updated_at = NOW()
                    WHERE distribution_name = :dist_name
                      AND distribution_version = :dist_version
                    """
                ),
                {
                    "dist_name": dist_name,
                    "dist_version": dist_version,
                    "commands": APT_INSTALL_COMMANDS,
                },
            )

    # Update openSUSE Tumbleweed
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_method = 'zypper_obs',
                    agent_install_commands = :commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE distribution_name = 'openSUSE'
                  AND distribution_version = 'Tumbleweed'
                """
            ),
            {"commands": ZYPPER_INSTALL_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_method = 'zypper_obs',
                    agent_install_commands = :commands,
                    updated_at = NOW()
                WHERE distribution_name = 'openSUSE'
                  AND distribution_version = 'Tumbleweed'
                """
            ),
            {"commands": ZYPPER_INSTALL_COMMANDS},
        )

    # Update openSUSE Leap
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_method = 'zypper_obs',
                    agent_install_commands = :commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE distribution_name = 'openSUSE'
                  AND distribution_version = 'Leap-15'
                """
            ),
            {"commands": ZYPPER_LEAP_INSTALL_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_method = 'zypper_obs',
                    agent_install_commands = :commands,
                    updated_at = NOW()
                WHERE distribution_name = 'openSUSE'
                  AND distribution_version = 'Leap-15'
                """
            ),
            {"commands": ZYPPER_LEAP_INSTALL_COMMANDS},
        )

    # Update SUSE Enterprise
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_method = 'zypper_obs',
                    agent_install_commands = :commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE distribution_name = 'SUSE'
                  AND distribution_version = '15'
                """
            ),
            {"commands": ZYPPER_SLES_INSTALL_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_method = 'zypper_obs',
                    agent_install_commands = :commands,
                    updated_at = NOW()
                WHERE distribution_name = 'SUSE'
                  AND distribution_version = '15'
                """
            ),
            {"commands": ZYPPER_SLES_INSTALL_COMMANDS},
        )

    # Update DNF-based distributions (Fedora, AlmaLinux, Rocky, Oracle)
    dnf_distros = [
        ("Fedora", "39"),
        ("AlmaLinux", "9"),
        ("RockyLinux", "9"),
        ("Oracle", "9"),
    ]

    for dist_name, dist_version in dnf_distros:
        if is_sqlite:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_method = 'dnf_copr',
                        agent_install_commands = :commands,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE distribution_name = :dist_name
                      AND distribution_version = :dist_version
                    """
                ),
                {
                    "dist_name": dist_name,
                    "dist_version": dist_version,
                    "commands": DNF_INSTALL_COMMANDS,
                },
            )
        else:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_method = 'dnf_copr',
                        agent_install_commands = :commands,
                        updated_at = NOW()
                    WHERE distribution_name = :dist_name
                      AND distribution_version = :dist_version
                    """
                ),
                {
                    "dist_name": dist_name,
                    "dist_version": dist_version,
                    "commands": DNF_INSTALL_COMMANDS,
                },
            )


def downgrade() -> None:
    """Revert to placeholder commands."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    placeholder_commands = json.dumps([
        "apt-get update",
        "apt-get install -y curl",
        "curl -fsSL https://example.com/sysmanage-agent-install.sh | bash"
    ])

    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_commands = :commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'wsl'
                """
            ),
            {"commands": placeholder_commands},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    agent_install_commands = :commands,
                    updated_at = NOW()
                WHERE child_type = 'wsl'
                """
            ),
            {"commands": placeholder_commands},
        )
