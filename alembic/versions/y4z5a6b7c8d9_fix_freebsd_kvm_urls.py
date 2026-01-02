"""fix_freebsd_kvm_urls

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-01-02 15:00:00.000000

This migration fixes the FreeBSD KVM distribution URLs.
The original URLs pointed to outdated versions that no longer exist.

Changes:
- Removes FreeBSD 14.2, 14.1, 14.0, 13.4, 13.3 (no longer available)
- Adds FreeBSD 15.0, 14.3, 13.5 with correct cloud-init URLs
"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "y4z5a6b7c8d9"
down_revision: Union[str, None] = "x3y4z5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old versions to remove (no longer available on FreeBSD download servers)
OLD_FREEBSD_VERSIONS = ["14.2", "14.1", "14.0", "13.4", "13.3"]

# New FreeBSD distributions with correct URLs
# FreeBSD provides BASIC-CLOUDINIT images with cloud-init support
NEW_FREEBSD_KVM_DISTRIBUTIONS = [
    # FreeBSD 15.0 (newest release)
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "15.0",
        "display_name": "FreeBSD 15.0-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/15.0-RELEASE/amd64/Latest/FreeBSD-15.0-RELEASE-amd64-BASIC-CLOUDINIT-ufs.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python311 py311-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 15.0-RELEASE - Newest release with cloud-init support. Supports bhyve nested virtualization.",
    },
    # FreeBSD 14.3 (current stable branch)
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "14.3",
        "display_name": "FreeBSD 14.3-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/14.3-RELEASE/amd64/Latest/FreeBSD-14.3-RELEASE-amd64-BASIC-CLOUDINIT-ufs.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python311 py311-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 14.3-RELEASE - Current stable release with cloud-init support. Supports bhyve nested virtualization.",
    },
    # FreeBSD 13.5 (extended support branch)
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "13.5",
        "display_name": "FreeBSD 13.5-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/13.5-RELEASE/amd64/Latest/FreeBSD-13.5-RELEASE-amd64.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python311 py311-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 13.5-RELEASE - Extended support release. Supports bhyve nested virtualization.",
    },
]


def upgrade() -> None:
    """Fix FreeBSD KVM distribution URLs."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Step 1: Remove old FreeBSD versions that no longer exist
    for version in OLD_FREEBSD_VERSIONS:
        bind.execute(
            text(
                """
                DELETE FROM child_host_distribution
                WHERE child_type = 'kvm'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = :version
                """
            ),
            {"version": version},
        )

    # Step 2: Add new FreeBSD distributions with correct URLs (idempotent)
    for dist in NEW_FREEBSD_KVM_DISTRIBUTIONS:
        dist_id = str(uuid.uuid4())

        # Check if this distribution already exists
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
    """Revert to old FreeBSD versions (note: these URLs no longer work)."""
    bind = op.get_bind()

    # Remove new versions
    for dist in NEW_FREEBSD_KVM_DISTRIBUTIONS:
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

    # Note: We don't restore old versions since they would have broken URLs
    # The previous migration (x3y4z5a6b7c8) would need to be run again to restore them
