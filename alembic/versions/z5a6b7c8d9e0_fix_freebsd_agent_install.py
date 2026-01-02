"""fix_freebsd_agent_install

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-01-02 20:00:00.000000

This migration fixes the FreeBSD KVM agent install commands to download
the sysmanage-agent package from GitHub releases instead of using pip.

The sysmanage-agent package is not on PyPI - it is distributed via
GitHub releases with platform-specific packages (.pkg for FreeBSD).

The install commands now:
1. Query GitHub API for the latest release version
2. Download the FreeBSD .pkg file
3. Install using pkg add
4. Enable and start the service
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "z5a6b7c8d9e0"
down_revision: Union[str, None] = "y4z5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# FreeBSD versions to update
FREEBSD_VERSIONS = ["14.2", "14.1", "14.0", "13.4", "13.3"]

# New install commands that download from GitHub releases
# Uses shell to get latest version dynamically
NEW_INSTALL_COMMANDS = """[
    "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\"tag_name\\\": *\\\"[^\\\"]*\\\"' | grep -o 'v[0-9.]*')",
    "VERSION=${LATEST#v}",
    "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
    "pkg add /tmp/sysmanage-agent-${VERSION}.pkg",
    "rm /tmp/sysmanage-agent-${VERSION}.pkg",
    "sysrc sysmanage_agent_enable=YES",
    "service sysmanage_agent start"
]"""

# Old install commands (for downgrade)
OLD_INSTALL_COMMANDS_14 = """[
    "pkg update",
    "pkg install -y python311 py311-pip",
    "pip install sysmanage-agent",
    "sysrc sysmanage_agent_enable=YES",
    "service sysmanage_agent start"
]"""

OLD_INSTALL_COMMANDS_13 = """[
    "pkg update",
    "pkg install -y python39 py39-pip",
    "pip install sysmanage-agent",
    "sysrc sysmanage_agent_enable=YES",
    "service sysmanage_agent start"
]"""


def upgrade() -> None:
    """Fix FreeBSD agent install commands to use GitHub releases."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for version in FREEBSD_VERSIONS:
        if is_sqlite:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_commands = :agent_install_commands,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE child_type = 'kvm'
                      AND distribution_name = 'FreeBSD'
                      AND distribution_version = :version
                    """
                ),
                {
                    "version": version,
                    "agent_install_commands": NEW_INSTALL_COMMANDS,
                },
            )
        else:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_commands = :agent_install_commands,
                        updated_at = NOW()
                    WHERE child_type = 'kvm'
                      AND distribution_name = 'FreeBSD'
                      AND distribution_version = :version
                    """
                ),
                {
                    "version": version,
                    "agent_install_commands": NEW_INSTALL_COMMANDS,
                },
            )


def downgrade() -> None:
    """Revert to old pip-based install commands."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for version in FREEBSD_VERSIONS:
        # Use Python 3.11 commands for 14.x, Python 3.9 for 13.x
        if version.startswith("14"):
            old_commands = OLD_INSTALL_COMMANDS_14
        else:
            old_commands = OLD_INSTALL_COMMANDS_13

        if is_sqlite:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_commands = :agent_install_commands,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE child_type = 'kvm'
                      AND distribution_name = 'FreeBSD'
                      AND distribution_version = :version
                    """
                ),
                {
                    "version": version,
                    "agent_install_commands": old_commands,
                },
            )
        else:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        agent_install_commands = :agent_install_commands,
                        updated_at = NOW()
                    WHERE child_type = 'kvm'
                      AND distribution_name = 'FreeBSD'
                      AND distribution_version = :version
                    """
                ),
                {
                    "version": version,
                    "agent_install_commands": old_commands,
                },
            )
