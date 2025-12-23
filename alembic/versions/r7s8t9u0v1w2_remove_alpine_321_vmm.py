"""remove_alpine_321_vmm

Revision ID: r7s8t9u0v1w2
Revises: q6r7s8t9u0v1
Create Date: 2025-12-23 12:00:00.000000

This migration removes Alpine Linux 3.21 from the child_host_distribution table
for VMM virtual machines on OpenBSD hosts.

Alpine Linux 3.21 has been found to have compatibility issues with OpenBSD VMM,
so it is being removed from the list of available distributions.

The migration is idempotent - it only deletes if the record exists.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "r7s8t9u0v1w2"
down_revision: Union[str, None] = "q6r7s8t9u0v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Alpine Linux 3.21 distribution to remove (for VMM only)
ALPINE_321_VMM = {
    "child_type": "vmm",
    "distribution_name": "Alpine Linux",
    "distribution_version": "3.21",
}

# Original Alpine 3.21 distribution data for downgrade (restore)
ALPINE_321_RESTORE = {
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
        "pip3 install sysmanage-agent",
        "rc-update add sysmanage_agent default",
        "rc-service sysmanage_agent start"
    ]""",
    "notes": "Alpine Linux 3.21 - Latest stable. Lightweight, security-focused. Uses alpine-virt for VMM compatibility",
}


def upgrade() -> None:
    """Remove Alpine Linux 3.21 from VMM distributions."""
    bind = op.get_bind()

    # Check if the distribution exists before deleting (idempotent)
    result = bind.execute(
        text(
            """
            SELECT COUNT(*) FROM child_host_distribution
            WHERE child_type = :child_type
              AND distribution_name = :distribution_name
              AND distribution_version = :distribution_version
            """
        ),
        ALPINE_321_VMM,
    )
    exists = result.scalar() > 0

    if exists:
        # Delete the Alpine 3.21 VMM distribution
        bind.execute(
            text(
                """
                DELETE FROM child_host_distribution
                WHERE child_type = :child_type
                  AND distribution_name = :distribution_name
                  AND distribution_version = :distribution_version
                """
            ),
            ALPINE_321_VMM,
        )


def downgrade() -> None:
    """Restore Alpine Linux 3.21 to VMM distributions."""
    import uuid

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Check if the distribution already exists (idempotent)
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
            "child_type": ALPINE_321_RESTORE["child_type"],
            "distribution_name": ALPINE_321_RESTORE["distribution_name"],
            "distribution_version": ALPINE_321_RESTORE["distribution_version"],
        },
    )
    exists = result.scalar() > 0

    if not exists:
        dist_id = str(uuid.uuid4())

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
                    "child_type": ALPINE_321_RESTORE["child_type"],
                    "distribution_name": ALPINE_321_RESTORE["distribution_name"],
                    "distribution_version": ALPINE_321_RESTORE["distribution_version"],
                    "display_name": ALPINE_321_RESTORE["display_name"],
                    "install_identifier": ALPINE_321_RESTORE["install_identifier"],
                    "executable_name": ALPINE_321_RESTORE["executable_name"],
                    "agent_install_method": ALPINE_321_RESTORE["agent_install_method"],
                    "agent_install_commands": ALPINE_321_RESTORE["agent_install_commands"],
                    "notes": ALPINE_321_RESTORE["notes"],
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
                    "child_type": ALPINE_321_RESTORE["child_type"],
                    "distribution_name": ALPINE_321_RESTORE["distribution_name"],
                    "distribution_version": ALPINE_321_RESTORE["distribution_version"],
                    "display_name": ALPINE_321_RESTORE["display_name"],
                    "install_identifier": ALPINE_321_RESTORE["install_identifier"],
                    "executable_name": ALPINE_321_RESTORE["executable_name"],
                    "agent_install_method": ALPINE_321_RESTORE["agent_install_method"],
                    "agent_install_commands": ALPINE_321_RESTORE["agent_install_commands"],
                    "notes": ALPINE_321_RESTORE["notes"],
                },
            )
