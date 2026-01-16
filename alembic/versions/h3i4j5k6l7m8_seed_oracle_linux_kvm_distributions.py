"""seed_oracle_linux_kvm_distributions

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-01-16 15:00:00.000000

This migration seeds the child_host_distribution table with Oracle Linux
KVM virtual machine distributions for Linux hosts.

Oracle Linux is a 100% free and compatible alternative to RHEL that uses dnf
as its package manager. Cloud images with cloud-init support are available
from Oracle's yum repository.
"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Oracle Linux KVM distributions - full VMs using official Oracle cloud images
# Cloud images support cloud-init for automated configuration
# Agent installation uses dnf and GitHub releases (same as other RHEL-family distros)
ORACLE_LINUX_DISTRIBUTIONS = [
    # Oracle Linux 9 - current release
    {
        "child_type": "kvm",
        "distribution_name": "Oracle Linux",
        "distribution_version": "9",
        "display_name": "Oracle Linux 9",
        "install_identifier": "https://yum.oracle.com/templates/OracleLinux/OL9/u5/x86_64/OL9U5_x86_64-kvm-b253.qcow2",
        "executable_name": None,
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "timedatectl set-ntp true || true",
            "sleep 5",
            "dnf install -y python3 python3-pip curl jq",
            "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
            "VERSION=${LATEST#v}",
            "curl -sSL --retry 3 -o /tmp/sysmanage-agent-${VERSION}-1.x86_64.rpm https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}-1.x86_64.rpm",
            "test $(stat -c%s /tmp/sysmanage-agent-${VERSION}-1.x86_64.rpm 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
            "dnf install -y /tmp/sysmanage-agent-${VERSION}-1.x86_64.rpm",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Oracle Linux 9 (Update 5) - RHEL-compatible cloud image with cloud-init and UEK kernel support",
    },
    # Oracle Linux 8 - LTS release
    {
        "child_type": "kvm",
        "distribution_name": "Oracle Linux",
        "distribution_version": "8",
        "display_name": "Oracle Linux 8",
        "install_identifier": "https://yum.oracle.com/templates/OracleLinux/OL8/u10/x86_64/OL8U10_x86_64-kvm-b237.qcow2",
        "executable_name": None,
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "timedatectl set-ntp true || true",
            "sleep 5",
            "dnf install -y python3 python3-pip curl jq",
            "LATEST=$(curl -sS --retry 3 https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | jq -r .tag_name)",
            "VERSION=${LATEST#v}",
            "curl -sSL --retry 3 -o /tmp/sysmanage-agent-${VERSION}-1.x86_64.rpm https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}-1.x86_64.rpm",
            "test $(stat -c%s /tmp/sysmanage-agent-${VERSION}-1.x86_64.rpm 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
            "dnf install -y /tmp/sysmanage-agent-${VERSION}-1.x86_64.rpm",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Oracle Linux 8 (Update 10) - RHEL-compatible cloud image with cloud-init and UEK kernel support",
    },
]


def upgrade() -> None:
    """Seed child_host_distribution table with Oracle Linux KVM distributions."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for dist in ORACLE_LINUX_DISTRIBUTIONS:
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
    """Remove seeded Oracle Linux KVM distributions."""
    bind = op.get_bind()

    # Remove only the distributions we seeded
    for dist in ORACLE_LINUX_DISTRIBUTIONS:
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
