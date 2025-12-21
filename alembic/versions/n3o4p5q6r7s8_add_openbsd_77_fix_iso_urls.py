"""add_openbsd_77_fix_iso_urls

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
Create Date: 2025-12-07 06:30:00.000000

This migration:
1. Adds OpenBSD 7.7 as a VMM distribution
2. Updates existing OpenBSD ISO URLs from cdn.openbsd.org to ftp.openbsd.org
   (CDN only keeps last two versions, so older versions need the main FTP server)

"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "n3o4p5q6r7s8"
down_revision: Union[str, None] = "m2n3o4p5q6r7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New OpenBSD 7.7 distribution
OPENBSD_77 = {
    "child_type": "vmm",
    "distribution_name": "OpenBSD",
    "distribution_version": "7.7",
    "display_name": "OpenBSD 7.7",
    "install_identifier": "https://ftp.openbsd.org/pub/OpenBSD/7.7/amd64/install77.iso",
    "executable_name": None,
    "agent_install_method": "pkg_add",
    "agent_install_commands": """[
        "pkg_add python3",
        "pkg_add py3-pip",
        "pip3 install sysmanage-agent",
        "rcctl enable sysmanage_agent",
        "rcctl start sysmanage_agent"
    ]""",
    "notes": "OpenBSD 7.7 - Current stable release with VMM support",
}

# URL updates for existing OpenBSD versions (cdn -> ftp)
OPENBSD_URL_UPDATES = [
    {
        "distribution_version": "7.5",
        "new_url": "https://ftp.openbsd.org/pub/OpenBSD/7.5/amd64/install75.iso",
    },
    {
        "distribution_version": "7.6",
        "new_url": "https://ftp.openbsd.org/pub/OpenBSD/7.6/amd64/install76.iso",
    },
]


def upgrade() -> None:
    """Add OpenBSD 7.7 and fix ISO URLs to use ftp.openbsd.org."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # First, update existing OpenBSD URLs to use ftp.openbsd.org
    for update in OPENBSD_URL_UPDATES:
        if is_sqlite:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        install_identifier = :new_url,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE child_type = 'vmm'
                      AND distribution_name = 'OpenBSD'
                      AND distribution_version = :distribution_version
                    """
                ),
                {
                    "distribution_version": update["distribution_version"],
                    "new_url": update["new_url"],
                },
            )
        else:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        install_identifier = :new_url,
                        updated_at = NOW()
                    WHERE child_type = 'vmm'
                      AND distribution_name = 'OpenBSD'
                      AND distribution_version = :distribution_version
                    """
                ),
                {
                    "distribution_version": update["distribution_version"],
                    "new_url": update["new_url"],
                },
            )

    # Now add OpenBSD 7.7 (idempotent - check if it exists first)
    dist = OPENBSD_77
    dist_id = str(uuid.uuid4())

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
    """Remove OpenBSD 7.7 and revert URLs to cdn.openbsd.org."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Remove OpenBSD 7.7
    bind.execute(
        text(
            """
            DELETE FROM child_host_distribution
            WHERE child_type = 'vmm'
              AND distribution_name = 'OpenBSD'
              AND distribution_version = '7.7'
            """
        )
    )

    # Revert URLs back to cdn.openbsd.org
    cdn_url_reverts = [
        {
            "distribution_version": "7.5",
            "old_url": "https://cdn.openbsd.org/pub/OpenBSD/7.5/amd64/install75.iso",
        },
        {
            "distribution_version": "7.6",
            "old_url": "https://cdn.openbsd.org/pub/OpenBSD/7.6/amd64/install76.iso",
        },
    ]

    for revert in cdn_url_reverts:
        if is_sqlite:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        install_identifier = :old_url,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE child_type = 'vmm'
                      AND distribution_name = 'OpenBSD'
                      AND distribution_version = :distribution_version
                    """
                ),
                {
                    "distribution_version": revert["distribution_version"],
                    "old_url": revert["old_url"],
                },
            )
        else:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        install_identifier = :old_url,
                        updated_at = NOW()
                    WHERE child_type = 'vmm'
                      AND distribution_name = 'OpenBSD'
                      AND distribution_version = :distribution_version
                    """
                ),
                {
                    "distribution_version": revert["distribution_version"],
                    "old_url": revert["old_url"],
                },
            )
