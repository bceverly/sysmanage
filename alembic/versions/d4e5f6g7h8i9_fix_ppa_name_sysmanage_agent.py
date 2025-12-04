"""Fix PPA name to sysmanage-agent

Revision ID: d4e5f6g7h8i9
Revises: f6g7h8i9j0k1
Create Date: 2025-12-02 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: Union[str, None] = "f6g7h8i9j0k1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Correct PPA install commands
CORRECT_PPA_COMMANDS = '["apt-get update", "apt-get install -y software-properties-common", "add-apt-repository -y ppa:bceverly/sysmanage-agent", "apt-get update", "apt-get install -y sysmanage-agent"]'
OLD_PPA_COMMANDS = '["apt-get update", "apt-get install -y software-properties-common", "add-apt-repository -y ppa:bceverly/sysmanage", "apt-get update", "apt-get install -y sysmanage-agent"]'


def upgrade() -> None:
    """Update agent_install_commands to use correct PPA name."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Fix Ubuntu/Debian distributions to use ppa:bceverly/sysmanage-agent
    # Only update if the record exists and has the old incorrect value (idempotent)
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :new_commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'wsl'
                  AND agent_install_method = 'apt_launchpad'
                  AND agent_install_commands LIKE '%ppa:bceverly/sysmanage"%'
                  AND agent_install_commands NOT LIKE '%ppa:bceverly/sysmanage-agent%'
                """
            ),
            {"new_commands": CORRECT_PPA_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :new_commands,
                    updated_at = NOW()
                WHERE child_type = 'wsl'
                  AND agent_install_method = 'apt_launchpad'
                  AND agent_install_commands LIKE '%ppa:bceverly/sysmanage"%'
                  AND agent_install_commands NOT LIKE '%ppa:bceverly/sysmanage-agent%'
                """
            ),
            {"new_commands": CORRECT_PPA_COMMANDS},
        )


def downgrade() -> None:
    """Revert to old PPA name."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :old_commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'wsl'
                  AND agent_install_method = 'apt_launchpad'
                  AND agent_install_commands LIKE '%ppa:bceverly/sysmanage-agent%'
                """
            ),
            {"old_commands": OLD_PPA_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :old_commands,
                    updated_at = NOW()
                WHERE child_type = 'wsl'
                  AND agent_install_method = 'apt_launchpad'
                  AND agent_install_commands LIKE '%ppa:bceverly/sysmanage-agent%'
                """
            ),
            {"old_commands": OLD_PPA_COMMANDS},
        )
