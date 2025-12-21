"""add_openbsd_74

Revision ID: o4p5q6r7s8t9
Revises: n3o4p5q6r7s8
Create Date: 2025-12-18 10:00:00.000000

This migration adds OpenBSD 7.4 as a VMM distribution.
Uses ftp.openbsd.org since older versions are not on the CDN.

"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "o4p5q6r7s8t9"
down_revision: Union[str, None] = "n3o4p5q6r7s8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# OpenBSD 7.4 distribution
OPENBSD_74 = {
    "child_type": "vmm",
    "distribution_name": "OpenBSD",
    "distribution_version": "7.4",
    "display_name": "OpenBSD 7.4",
    "install_identifier": "https://ftp.openbsd.org/pub/OpenBSD/7.4/amd64/install74.iso",
    "executable_name": None,
    "agent_install_method": "pkg_add",
    "agent_install_commands": """[
        "pkg_add python3",
        "pkg_add py3-pip",
        "pip3 install sysmanage-agent",
        "rcctl enable sysmanage_agent",
        "rcctl start sysmanage_agent"
    ]""",
    "notes": "OpenBSD 7.4 - Previous stable release with VMM support",
}


def upgrade() -> None:
    """Add OpenBSD 7.4 as a VMM distribution."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    dist = OPENBSD_74
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
    """Remove OpenBSD 7.4."""
    bind = op.get_bind()

    bind.execute(
        text(
            """
            DELETE FROM child_host_distribution
            WHERE child_type = 'vmm'
              AND distribution_name = 'OpenBSD'
              AND distribution_version = '7.4'
            """
        )
    )
