"""Fix COPR and OBS repository names for Fedora and Tumbleweed

Revision ID: g6h7i8j9k0l1
Revises: d4e5f6g7h8i9
Create Date: 2025-12-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "g6h7i8j9k0l1"
down_revision: Union[str, None] = "d4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Correct COPR commands for Fedora
CORRECT_FEDORA_COMMANDS = '["dnf install -y dnf-plugins-core", "dnf copr enable -y bceverly/sysmanage-agent", "dnf install -y sysmanage-agent"]'
OLD_FEDORA_COMMANDS = '["dnf install -y dnf-plugins-core", "dnf copr enable -y bceverly/sysmanage", "dnf install -y sysmanage-agent"]'

# Correct OBS commands for Tumbleweed
CORRECT_TUMBLEWEED_COMMANDS = '["zypper refresh", "zypper addrepo -f https://download.opensuse.org/repositories/home:/bryaneverly/openSUSE_Tumbleweed/home:bryaneverly.repo", "zypper --gpg-auto-import-keys refresh", "zypper install -y sysmanage-agent"]'
OLD_TUMBLEWEED_COMMANDS = '["zypper refresh", "zypper addrepo -f https://download.opensuse.org/repositories/home:/bceverly/openSUSE_Tumbleweed/home:bceverly.repo", "zypper --gpg-auto-import-keys refresh", "zypper install -y sysmanage-agent"]'


def upgrade() -> None:
    """Fix Fedora COPR and openSUSE OBS repository names."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Fix Fedora to use correct COPR repo: bceverly/sysmanage-agent
    # Only update if the record has the old incorrect value (idempotent)
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :new_commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE install_identifier = 'Fedora'
                  AND agent_install_method = 'dnf_copr'
                  AND agent_install_commands LIKE '%bceverly/sysmanage"%'
                  AND agent_install_commands NOT LIKE '%bceverly/sysmanage-agent%'
                """
            ),
            {"new_commands": CORRECT_FEDORA_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :new_commands,
                    updated_at = NOW()
                WHERE install_identifier = 'Fedora'
                  AND agent_install_method = 'dnf_copr'
                  AND agent_install_commands LIKE '%bceverly/sysmanage"%'
                  AND agent_install_commands NOT LIKE '%bceverly/sysmanage-agent%'
                """
            ),
            {"new_commands": CORRECT_FEDORA_COMMANDS},
        )

    # Fix openSUSE Tumbleweed to use correct OBS repo: home:bryaneverly
    # Only update if the record has the old incorrect value (idempotent)
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :new_commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE install_identifier = 'openSUSE-Tumbleweed'
                  AND agent_install_method = 'zypper_obs'
                  AND agent_install_commands LIKE '%home:/bceverly%'
                  AND agent_install_commands NOT LIKE '%home:/bryaneverly%'
                """
            ),
            {"new_commands": CORRECT_TUMBLEWEED_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :new_commands,
                    updated_at = NOW()
                WHERE install_identifier = 'openSUSE-Tumbleweed'
                  AND agent_install_method = 'zypper_obs'
                  AND agent_install_commands LIKE '%home:/bceverly%'
                  AND agent_install_commands NOT LIKE '%home:/bryaneverly%'
                """
            ),
            {"new_commands": CORRECT_TUMBLEWEED_COMMANDS},
        )


def downgrade() -> None:
    """Revert to old incorrect repository names."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Revert Fedora
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :old_commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE install_identifier = 'Fedora'
                  AND agent_install_method = 'dnf_copr'
                  AND agent_install_commands LIKE '%bceverly/sysmanage-agent%'
                """
            ),
            {"old_commands": OLD_FEDORA_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :old_commands,
                    updated_at = NOW()
                WHERE install_identifier = 'Fedora'
                  AND agent_install_method = 'dnf_copr'
                  AND agent_install_commands LIKE '%bceverly/sysmanage-agent%'
                """
            ),
            {"old_commands": OLD_FEDORA_COMMANDS},
        )

    # Revert openSUSE Tumbleweed
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :old_commands,
                    updated_at = CURRENT_TIMESTAMP
                WHERE install_identifier = 'openSUSE-Tumbleweed'
                  AND agent_install_method = 'zypper_obs'
                  AND agent_install_commands LIKE '%home:/bryaneverly%'
                """
            ),
            {"old_commands": OLD_TUMBLEWEED_COMMANDS},
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = :old_commands,
                    updated_at = NOW()
                WHERE install_identifier = 'openSUSE-Tumbleweed'
                  AND agent_install_method = 'zypper_obs'
                  AND agent_install_commands LIKE '%home:/bryaneverly%'
                """
            ),
            {"old_commands": OLD_TUMBLEWEED_COMMANDS},
        )
