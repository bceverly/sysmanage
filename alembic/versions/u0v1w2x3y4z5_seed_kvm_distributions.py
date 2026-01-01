"""seed_kvm_distributions

Revision ID: u0v1w2x3y4z5
Revises: t9u0v1w2x3y4
Create Date: 2025-12-31 14:00:00.000000

This migration seeds the child_host_distribution table with commonly
available KVM virtual machine operating systems for Linux hosts.

KVM VMs are full virtual machines that support:
- Cloud images with cloud-init for automated configuration (preferred)
- Traditional ISO installation as fallback
- SSH-based agent installation after OS is running

Cloud images are preferred because they:
- Are smaller and faster to download
- Support cloud-init for automated user creation and agent installation
- Don't require interactive installation
"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "u0v1w2x3y4z5"
down_revision: Union[str, None] = "t9u0v1w2x3y4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# KVM distributions - full VMs that can be installed on Linux KVM/libvirt
# install_identifier contains the cloud image URL (preferred) or ISO URL
# Cloud images support cloud-init for automated configuration
KVM_DISTRIBUTIONS = [
    # Ubuntu - using cloud images with cloud-init support
    {
        "child_type": "kvm",
        "distribution_name": "Ubuntu Server",
        "distribution_version": "24.04",
        "display_name": "Ubuntu Server 24.04 LTS",
        "install_identifier": "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",
        "executable_name": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y software-properties-common",
            "add-apt-repository -y ppa:bceverly/sysmanage-agent",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Ubuntu Server 24.04 LTS (Noble Numbat) - Cloud image with cloud-init support",
    },
    {
        "child_type": "kvm",
        "distribution_name": "Ubuntu Server",
        "distribution_version": "22.04",
        "display_name": "Ubuntu Server 22.04 LTS",
        "install_identifier": "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img",
        "executable_name": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y software-properties-common",
            "add-apt-repository -y ppa:bceverly/sysmanage-agent",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Ubuntu Server 22.04 LTS (Jammy Jellyfish) - Cloud image with cloud-init support",
    },
    # Debian - using cloud images
    {
        "child_type": "kvm",
        "distribution_name": "Debian",
        "distribution_version": "12",
        "display_name": "Debian 12 (Bookworm)",
        "install_identifier": "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2",
        "executable_name": None,
        "agent_install_method": "apt_obs",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl gnupg",
            "curl -fsSL https://download.opensuse.org/repositories/home:/bceverly:/sysmanage-agent/Debian_12/Release.key | gpg --dearmor -o /usr/share/keyrings/sysmanage-agent.gpg",
            "echo 'deb [signed-by=/usr/share/keyrings/sysmanage-agent.gpg] https://download.opensuse.org/repositories/home:/bceverly:/sysmanage-agent/Debian_12/ /' > /etc/apt/sources.list.d/sysmanage-agent.list",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Debian 12 (Bookworm) - Cloud image with cloud-init support",
    },
    {
        "child_type": "kvm",
        "distribution_name": "Debian",
        "distribution_version": "11",
        "display_name": "Debian 11 (Bullseye)",
        "install_identifier": "https://cloud.debian.org/images/cloud/bullseye/latest/debian-11-generic-amd64.qcow2",
        "executable_name": None,
        "agent_install_method": "apt_obs",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y curl gnupg",
            "curl -fsSL https://download.opensuse.org/repositories/home:/bceverly:/sysmanage-agent/Debian_11/Release.key | gpg --dearmor -o /usr/share/keyrings/sysmanage-agent.gpg",
            "echo 'deb [signed-by=/usr/share/keyrings/sysmanage-agent.gpg] https://download.opensuse.org/repositories/home:/bceverly:/sysmanage-agent/Debian_11/ /' > /etc/apt/sources.list.d/sysmanage-agent.list",
            "apt-get update",
            "apt-get install -y sysmanage-agent"
        ]""",
        "notes": "Debian 11 (Bullseye) - Cloud image with cloud-init support",
    },
    # Fedora - using cloud images
    {
        "child_type": "kvm",
        "distribution_name": "Fedora Server",
        "distribution_version": "41",
        "display_name": "Fedora Server 41",
        "install_identifier": "https://download.fedoraproject.org/pub/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2",
        "executable_name": None,
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y python3 python3-pip",
            "pip3 install sysmanage-agent",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Fedora Server 41 - Cloud image with cloud-init support",
    },
    {
        "child_type": "kvm",
        "distribution_name": "Fedora Server",
        "distribution_version": "40",
        "display_name": "Fedora Server 40",
        "install_identifier": "https://download.fedoraproject.org/pub/fedora/linux/releases/40/Cloud/x86_64/images/Fedora-Cloud-Base-Generic.x86_64-40-1.14.qcow2",
        "executable_name": None,
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y python3 python3-pip",
            "pip3 install sysmanage-agent",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Fedora Server 40 - Cloud image with cloud-init support",
    },
    # AlmaLinux - RHEL clone
    {
        "child_type": "kvm",
        "distribution_name": "AlmaLinux",
        "distribution_version": "9",
        "display_name": "AlmaLinux 9",
        "install_identifier": "https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/AlmaLinux-9-GenericCloud-latest.x86_64.qcow2",
        "executable_name": None,
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y python3 python3-pip",
            "pip3 install sysmanage-agent",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "AlmaLinux 9 - RHEL-compatible cloud image with cloud-init support",
    },
    # Rocky Linux - RHEL clone
    {
        "child_type": "kvm",
        "distribution_name": "Rocky Linux",
        "distribution_version": "9",
        "display_name": "Rocky Linux 9",
        "install_identifier": "https://download.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2",
        "executable_name": None,
        "agent_install_method": "dnf",
        "agent_install_commands": """[
            "dnf install -y python3 python3-pip",
            "pip3 install sysmanage-agent",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Rocky Linux 9 - RHEL-compatible cloud image with cloud-init support",
    },
    # Alpine Linux - lightweight
    {
        "child_type": "kvm",
        "distribution_name": "Alpine Linux",
        "distribution_version": "3.20",
        "display_name": "Alpine Linux 3.20",
        "install_identifier": "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/cloud/nocloud_alpine-3.20.3-x86_64-bios-cloudinit-r0.qcow2",
        "executable_name": None,
        "agent_install_method": "apk",
        "agent_install_commands": """[
            "apk update",
            "apk add python3 py3-pip",
            "pip3 install sysmanage-agent",
            "rc-update add sysmanage_agent default",
            "rc-service sysmanage_agent start"
        ]""",
        "notes": "Alpine Linux 3.20 - Lightweight cloud image with cloud-init support",
    },
    {
        "child_type": "kvm",
        "distribution_name": "Alpine Linux",
        "distribution_version": "3.19",
        "display_name": "Alpine Linux 3.19",
        "install_identifier": "https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/cloud/nocloud_alpine-3.19.4-x86_64-bios-cloudinit-r0.qcow2",
        "executable_name": None,
        "agent_install_method": "apk",
        "agent_install_commands": """[
            "apk update",
            "apk add python3 py3-pip",
            "pip3 install sysmanage-agent",
            "rc-update add sysmanage_agent default",
            "rc-service sysmanage_agent start"
        ]""",
        "notes": "Alpine Linux 3.19 - Lightweight cloud image with cloud-init support",
    },
    # openSUSE Leap
    {
        "child_type": "kvm",
        "distribution_name": "openSUSE Leap",
        "distribution_version": "15.6",
        "display_name": "openSUSE Leap 15.6",
        "install_identifier": "https://download.opensuse.org/distribution/leap/15.6/appliances/openSUSE-Leap-15.6-Minimal-VM.x86_64-Cloud.qcow2",
        "executable_name": None,
        "agent_install_method": "zypper",
        "agent_install_commands": """[
            "zypper refresh",
            "zypper install -y python3 python3-pip",
            "pip3 install sysmanage-agent",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "openSUSE Leap 15.6 - Enterprise-grade cloud image with cloud-init support",
    },
]


def upgrade() -> None:
    """Seed child_host_distribution table with KVM distributions."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for dist in KVM_DISTRIBUTIONS:
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
    """Remove seeded KVM distributions."""
    bind = op.get_bind()

    # Remove only the distributions we seeded
    for dist in KVM_DISTRIBUTIONS:
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
