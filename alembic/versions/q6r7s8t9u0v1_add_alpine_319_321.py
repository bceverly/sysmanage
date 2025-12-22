"""add_alpine_319_321

Revision ID: q6r7s8t9u0v1
Revises: p5q6r7s8t9u0
Create Date: 2025-12-22 12:00:00.000000

This migration adds Alpine Linux 3.19 and 3.21 distributions to the
child_host_distribution table for VMM virtual machines on OpenBSD hosts.

Alpine Linux 3.20 was already seeded in m2n3o4p5q6r7_seed_vmm_distributions.py.
This migration adds the other supported versions (3.19 and 3.21).

The migration is idempotent - it will update existing records if they exist,
or insert new ones if they don't.
"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "q6r7s8t9u0v1"
down_revision: Union[str, None] = "p5q6r7s8t9u0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Additional Alpine Linux distributions for VMM
# Alpine 3.20 already exists from m2n3o4p5q6r7_seed_vmm_distributions.py
ALPINE_DISTRIBUTIONS = [
    {
        "child_type": "vmm",
        "distribution_name": "Alpine Linux",
        "distribution_version": "3.19",
        "display_name": "Alpine Linux 3.19",
        "install_identifier": "https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/x86_64/alpine-virt-3.19.7-x86_64.iso",
        "executable_name": None,
        "agent_install_method": "apk",
        "agent_install_commands": """[
            "apk update",
            "apk add python3 py3-pip",
            "pip3 install --break-system-packages sysmanage-agent",
            "rc-update add sysmanage_agent default",
            "rc-service sysmanage_agent start"
        ]""",
        "notes": "Alpine Linux 3.19 - Lightweight, security-focused. Uses alpine-virt for VMM compatibility",
    },
    {
        "child_type": "vmm",
        "distribution_name": "Alpine Linux",
        "distribution_version": "3.21",
        "display_name": "Alpine Linux 3.21",
        "install_identifier": "https://dl-cdn.alpinelinux.org/alpine/v3.21/releases/x86_64/alpine-virt-3.21.3-x86_64.iso",
        "executable_name": None,
        "agent_install_method": "apk",
        "agent_install_commands": """[
            "apk update",
            "apk add python3 py3-pip",
            "pip3 install --break-system-packages sysmanage-agent",
            "rc-update add sysmanage_agent default",
            "rc-service sysmanage_agent start"
        ]""",
        "notes": "Alpine Linux 3.21 - Latest stable. Lightweight, security-focused. Uses alpine-virt for VMM compatibility",
    },
]

# Also update Alpine 3.20 to include --break-system-packages flag
ALPINE_320_UPDATE = {
    "child_type": "vmm",
    "distribution_name": "Alpine Linux",
    "distribution_version": "3.20",
    "display_name": "Alpine Linux 3.20",
    "install_identifier": "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/alpine-virt-3.20.6-x86_64.iso",
    "agent_install_commands": """[
        "apk update",
        "apk add python3 py3-pip",
        "pip3 install --break-system-packages sysmanage-agent",
        "rc-update add sysmanage_agent default",
        "rc-service sysmanage_agent start"
    ]""",
    "notes": "Alpine Linux 3.20 - Lightweight, security-focused. Uses alpine-virt for VMM compatibility",
}


def upgrade() -> None:
    """Add Alpine Linux 3.19 and 3.21 distributions, update 3.20."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # First, update Alpine 3.20 if it exists (fix ISO URL and add --break-system-packages)
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
            "child_type": ALPINE_320_UPDATE["child_type"],
            "distribution_name": ALPINE_320_UPDATE["distribution_name"],
            "distribution_version": ALPINE_320_UPDATE["distribution_version"],
        },
    )
    if result.scalar() > 0:
        if is_sqlite:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        display_name = :display_name,
                        install_identifier = :install_identifier,
                        agent_install_commands = :agent_install_commands,
                        notes = :notes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE child_type = :child_type
                      AND distribution_name = :distribution_name
                      AND distribution_version = :distribution_version
                    """
                ),
                ALPINE_320_UPDATE,
            )
        else:
            bind.execute(
                text(
                    """
                    UPDATE child_host_distribution SET
                        display_name = :display_name,
                        install_identifier = :install_identifier,
                        agent_install_commands = :agent_install_commands,
                        notes = :notes,
                        updated_at = NOW()
                    WHERE child_type = :child_type
                      AND distribution_name = :distribution_name
                      AND distribution_version = :distribution_version
                    """
                ),
                ALPINE_320_UPDATE,
            )

    # Now add Alpine 3.19 and 3.21
    for dist in ALPINE_DISTRIBUTIONS:
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
    """Remove Alpine Linux 3.19 and 3.21 distributions.

    Note: This does NOT remove Alpine 3.20 as it was added in a different migration.
    """
    bind = op.get_bind()

    # Remove only the distributions we added in this migration
    for dist in ALPINE_DISTRIBUTIONS:
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

    # Revert Alpine 3.20 install_identifier to original (without latest ISO version)
    # Note: The original had alpine-virt-3.20.3, we updated to 3.20.6
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    install_identifier = 'https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/alpine-virt-3.20.3-x86_64.iso',
                    agent_install_commands = '[
                        "apk update",
                        "apk add python3 py3-pip",
                        "pip3 install sysmanage-agent",
                        "rc-update add sysmanage_agent default",
                        "rc-service sysmanage_agent start"
                    ]',
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'vmm'
                  AND distribution_name = 'Alpine Linux'
                  AND distribution_version = '3.20'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    install_identifier = 'https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/alpine-virt-3.20.3-x86_64.iso',
                    agent_install_commands = '[
                        "apk update",
                        "apk add python3 py3-pip",
                        "pip3 install sysmanage-agent",
                        "rc-update add sysmanage_agent default",
                        "rc-service sysmanage_agent start"
                    ]',
                    updated_at = NOW()
                WHERE child_type = 'vmm'
                  AND distribution_name = 'Alpine Linux'
                  AND distribution_version = '3.20'
                """
            )
        )
