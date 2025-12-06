"""Fix LXD PPA name from sysmanage to bceverly

Revision ID: l1m2n3o4p5q6
Revises: k0l1m2n3o4p5
Create Date: 2025-12-05 11:35:00.000000

This migration fixes the PPA name in existing LXD Ubuntu distributions
from ppa:sysmanage/sysmanage-agent to ppa:bceverly/sysmanage-agent.
The seeder migration k0l1m2n3o4p5 had an incorrect PPA name.

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "k0l1m2n3o4p5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix PPA name from ppa:sysmanage/sysmanage-agent to ppa:bceverly/sysmanage-agent."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Update all LXD distributions that have the incorrect PPA name
    # This is idempotent - it only updates records with the wrong value
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = REPLACE(
                    agent_install_commands,
                    'ppa:sysmanage/sysmanage-agent',
                    'ppa:bceverly/sysmanage-agent'
                ),
                updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'lxd'
                  AND agent_install_commands LIKE '%ppa:sysmanage/sysmanage-agent%'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = REPLACE(
                    agent_install_commands,
                    'ppa:sysmanage/sysmanage-agent',
                    'ppa:bceverly/sysmanage-agent'
                ),
                updated_at = NOW()
                WHERE child_type = 'lxd'
                  AND agent_install_commands LIKE '%ppa:sysmanage/sysmanage-agent%'
                """
            )
        )


def downgrade() -> None:
    """Revert PPA name back to ppa:sysmanage/sysmanage-agent (not recommended)."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = REPLACE(
                    agent_install_commands,
                    'ppa:bceverly/sysmanage-agent',
                    'ppa:sysmanage/sysmanage-agent'
                ),
                updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'lxd'
                  AND agent_install_commands LIKE '%ppa:bceverly/sysmanage-agent%'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution
                SET agent_install_commands = REPLACE(
                    agent_install_commands,
                    'ppa:bceverly/sysmanage-agent',
                    'ppa:sysmanage/sysmanage-agent'
                ),
                updated_at = NOW()
                WHERE child_type = 'lxd'
                  AND agent_install_commands LIKE '%ppa:bceverly/sysmanage-agent%'
                """
            )
        )
