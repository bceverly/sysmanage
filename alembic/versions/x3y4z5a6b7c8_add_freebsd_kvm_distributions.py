"""add_freebsd_kvm_distributions

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-01-02 12:00:00.000000

This migration adds FreeBSD as a KVM virtual machine distribution.
FreeBSD works well as a KVM guest and can run bhyve for nested virtualization
when the KVM host has nested virtualization enabled.

FreeBSD versions included:
- FreeBSD 14.2 (current stable)
- FreeBSD 14.1
- FreeBSD 14.0
- FreeBSD 13.4 (extended support)
- FreeBSD 13.3

FreeBSD provides official cloud images with cloud-init support via the
'firstboot' mechanism. The images are in qcow2 format compressed with xz.

NOTE: These URLs became invalid after FreeBSD removed older versions.
See migration y4z5a6b7c8d9 for the fix.
"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "x3y4z5a6b7c8"
down_revision: Union[str, None] = "w2x3y4z5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# FreeBSD distributions for KVM
# FreeBSD provides official VM images at download.freebsd.org
# These are qcow2 images that work with KVM/QEMU and support cloud-init
FREEBSD_KVM_DISTRIBUTIONS = [
    # FreeBSD 14.x (current stable branch)
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "14.2",
        "display_name": "FreeBSD 14.2-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/14.2-RELEASE/amd64/Latest/FreeBSD-14.2-RELEASE-amd64.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python311 py311-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 14.2-RELEASE - Current stable release with cloud-init support. Supports bhyve nested virtualization.",
    },
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "14.1",
        "display_name": "FreeBSD 14.1-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/14.1-RELEASE/amd64/Latest/FreeBSD-14.1-RELEASE-amd64.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python311 py311-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 14.1-RELEASE - Stable release with cloud-init support. Supports bhyve nested virtualization.",
    },
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "14.0",
        "display_name": "FreeBSD 14.0-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/14.0-RELEASE/amd64/Latest/FreeBSD-14.0-RELEASE-amd64.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python311 py311-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 14.0-RELEASE - First 14.x release with cloud-init support. Supports bhyve nested virtualization.",
    },
    # FreeBSD 13.x (extended support branch)
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "13.4",
        "display_name": "FreeBSD 13.4-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/13.4-RELEASE/amd64/Latest/FreeBSD-13.4-RELEASE-amd64.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python39 py39-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 13.4-RELEASE - Extended support release with cloud-init support. Supports bhyve nested virtualization.",
    },
    {
        "child_type": "kvm",
        "distribution_name": "FreeBSD",
        "distribution_version": "13.3",
        "display_name": "FreeBSD 13.3-RELEASE",
        "install_identifier": "https://download.freebsd.org/releases/VM-IMAGES/13.3-RELEASE/amd64/Latest/FreeBSD-13.3-RELEASE-amd64.qcow2.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "pkg update",
            "pkg install -y python39 py39-pip",
            "pip install sysmanage-agent",
            "sysrc sysmanage_agent_enable=YES",
            "service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 13.3-RELEASE - Extended support release with cloud-init support. Supports bhyve nested virtualization.",
    },
]


def upgrade() -> None:
    """Add FreeBSD distributions to child_host_distribution table for KVM."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for dist in FREEBSD_KVM_DISTRIBUTIONS:
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
    """Remove FreeBSD KVM distributions."""
    bind = op.get_bind()

    # Remove only the distributions we seeded
    for dist in FREEBSD_KVM_DISTRIBUTIONS:
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
