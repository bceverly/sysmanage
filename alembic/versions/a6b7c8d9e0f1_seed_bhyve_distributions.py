"""seed_bhyve_distributions

Revision ID: a6b7c8d9e0f1
Revises: z5a6b7c8d9e0
Create Date: 2026-01-05 12:00:00.000000

This migration seeds the child_host_distribution table with commonly
available bhyve virtual machine operating systems for FreeBSD hosts.

bhyve is FreeBSD's native hypervisor. It supports:
- FreeBSD guests (via bhyveload or UEFI)
- Linux guests (via UEFI with grub2-bhyve or native UEFI)
- Other BSD variants (via UEFI)

Cloud images are preferred for bhyve as they support cloud-init for
automated provisioning (hostname, users, ssh keys, etc).

FreeBSD cloud images work particularly well since bhyve is the native
FreeBSD hypervisor.
"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "z5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# bhyve distributions - cloud images that work with FreeBSD's bhyve hypervisor
# These use cloud-init for provisioning

# FreeBSD distributions for bhyve
# FreeBSD provides official raw VM images at download.freebsd.org
# The .raw.xz images work well with bhyve
BHYVE_DISTRIBUTIONS = [
    # FreeBSD 14.x (current stable branch)
    {
        "child_type": "bhyve",
        "distribution_name": "FreeBSD",
        "distribution_version": "14.2",
        "display_name": "FreeBSD 14.2-RELEASE",
        "install_identifier": "FreeBSD-14.2",
        "cloud_image_url": "https://download.freebsd.org/releases/VM-IMAGES/14.2-RELEASE/amd64/Latest/FreeBSD-14.2-RELEASE-amd64.raw.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\\\\"tag_name\\\\\\": *\\\\\\"[^\\\\\\"]*\\\\\\"' | grep -o 'v[0-9.]*')",
            "VERSION=${LATEST#v}",
            "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
            "pkg install -y python311 py311-pip py311-aiosqlite py311-cryptography py311-pyyaml py311-aiohttp py311-sqlalchemy20 py311-alembic py311-websockets",
            "pkg add /tmp/sysmanage-agent-${VERSION}.pkg || true",
            "cd / && tar -xf /tmp/sysmanage-agent-${VERSION}.pkg --include='usr/*'",
            "sysrc sysmanage_agent_enable=YES",
            "sysrc sysmanage_agent_user=root",
            "service sysmanage_agent restart 2>/dev/null || service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 14.2-RELEASE - Current stable release. Native bhyve guest with cloud-init support.",
    },
    {
        "child_type": "bhyve",
        "distribution_name": "FreeBSD",
        "distribution_version": "14.1",
        "display_name": "FreeBSD 14.1-RELEASE",
        "install_identifier": "FreeBSD-14.1",
        "cloud_image_url": "https://download.freebsd.org/releases/VM-IMAGES/14.1-RELEASE/amd64/Latest/FreeBSD-14.1-RELEASE-amd64.raw.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\\\\"tag_name\\\\\\": *\\\\\\"[^\\\\\\"]*\\\\\\"' | grep -o 'v[0-9.]*')",
            "VERSION=${LATEST#v}",
            "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
            "pkg install -y python311 py311-pip py311-aiosqlite py311-cryptography py311-pyyaml py311-aiohttp py311-sqlalchemy20 py311-alembic py311-websockets",
            "pkg add /tmp/sysmanage-agent-${VERSION}.pkg || true",
            "cd / && tar -xf /tmp/sysmanage-agent-${VERSION}.pkg --include='usr/*'",
            "sysrc sysmanage_agent_enable=YES",
            "sysrc sysmanage_agent_user=root",
            "service sysmanage_agent restart 2>/dev/null || service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 14.1-RELEASE - Stable release. Native bhyve guest with cloud-init support.",
    },
    # FreeBSD 13.x (extended support branch)
    {
        "child_type": "bhyve",
        "distribution_name": "FreeBSD",
        "distribution_version": "13.4",
        "display_name": "FreeBSD 13.4-RELEASE",
        "install_identifier": "FreeBSD-13.4",
        "cloud_image_url": "https://download.freebsd.org/releases/VM-IMAGES/13.4-RELEASE/amd64/Latest/FreeBSD-13.4-RELEASE-amd64.raw.xz",
        "executable_name": None,
        "agent_install_method": "pkg",
        "agent_install_commands": """[
            "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\\\\"tag_name\\\\\\": *\\\\\\"[^\\\\\\"]*\\\\\\"' | grep -o 'v[0-9.]*')",
            "VERSION=${LATEST#v}",
            "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
            "pkg install -y python39 py39-pip py39-aiosqlite py39-cryptography py39-pyyaml py39-aiohttp py39-sqlalchemy20 py39-alembic py39-websockets",
            "pkg add /tmp/sysmanage-agent-${VERSION}.pkg || true",
            "cd / && tar -xf /tmp/sysmanage-agent-${VERSION}.pkg --include='usr/*'",
            "sysrc sysmanage_agent_enable=YES",
            "sysrc sysmanage_agent_user=root",
            "service sysmanage_agent restart 2>/dev/null || service sysmanage_agent start"
        ]""",
        "notes": "FreeBSD 13.4-RELEASE - Extended support release. Native bhyve guest with cloud-init support.",
    },
    # Ubuntu 24.04 LTS (requires UEFI boot)
    {
        "child_type": "bhyve",
        "distribution_name": "Ubuntu",
        "distribution_version": "24.04",
        "display_name": "Ubuntu 24.04 LTS (Noble Numbat)",
        "install_identifier": "Ubuntu-24.04",
        "cloud_image_url": "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img",
        "executable_name": None,
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y python3 python3-pip python3-venv curl",
            "LATEST=$(curl -s https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\\\"tag_name\\\\\": *\\\\\"[^\\\\\"]*\\\\\"' | grep -o 'v[0-9.]*')",
            "VERSION=${LATEST#v}",
            "curl -L -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
            "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb || apt-get install -f -y",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Ubuntu 24.04 LTS (Noble Numbat) - Requires UEFI firmware. Cloud image with cloud-init support.",
    },
    # Ubuntu 22.04 LTS (requires UEFI boot)
    {
        "child_type": "bhyve",
        "distribution_name": "Ubuntu",
        "distribution_version": "22.04",
        "display_name": "Ubuntu 22.04 LTS (Jammy Jellyfish)",
        "install_identifier": "Ubuntu-22.04",
        "cloud_image_url": "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img",
        "executable_name": None,
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y python3 python3-pip python3-venv curl",
            "LATEST=$(curl -s https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\\\"tag_name\\\\\": *\\\\\"[^\\\\\"]*\\\\\"' | grep -o 'v[0-9.]*')",
            "VERSION=${LATEST#v}",
            "curl -L -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
            "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb || apt-get install -f -y",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Ubuntu 22.04 LTS (Jammy Jellyfish) - Requires UEFI firmware. Cloud image with cloud-init support.",
    },
    # Debian 12 (requires UEFI boot)
    {
        "child_type": "bhyve",
        "distribution_name": "Debian",
        "distribution_version": "12",
        "display_name": "Debian 12 (Bookworm)",
        "install_identifier": "Debian-12",
        "cloud_image_url": "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.raw",
        "executable_name": None,
        "agent_install_method": "apt",
        "agent_install_commands": """[
            "apt-get update",
            "apt-get install -y python3 python3-pip python3-venv curl",
            "LATEST=$(curl -s https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\\\"tag_name\\\\\": *\\\\\"[^\\\\\"]*\\\\\"' | grep -o 'v[0-9.]*')",
            "VERSION=${LATEST#v}",
            "curl -L -o /tmp/sysmanage-agent_${VERSION}_amd64.deb https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent_${VERSION}_amd64.deb",
            "dpkg -i /tmp/sysmanage-agent_${VERSION}_amd64.deb || apt-get install -f -y",
            "systemctl enable sysmanage-agent",
            "systemctl start sysmanage-agent"
        ]""",
        "notes": "Debian 12 (Bookworm) - Requires UEFI firmware. Cloud image with cloud-init support.",
    },
]


def upgrade() -> None:
    """Add bhyve distributions to child_host_distribution table."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for dist in BHYVE_DISTRIBUTIONS:
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
                            cloud_image_url = :cloud_image_url,
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
                        "cloud_image_url": dist["cloud_image_url"],
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
                            cloud_image_url = :cloud_image_url,
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
                        "cloud_image_url": dist["cloud_image_url"],
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
                            display_name, install_identifier, cloud_image_url,
                            executable_name, agent_install_method, agent_install_commands,
                            notes, is_active, created_at, updated_at
                        ) VALUES (
                            :id, :child_type, :distribution_name, :distribution_version,
                            :display_name, :install_identifier, :cloud_image_url,
                            :executable_name, :agent_install_method, :agent_install_commands,
                            :notes, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                        "cloud_image_url": dist["cloud_image_url"],
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
                            display_name, install_identifier, cloud_image_url,
                            executable_name, agent_install_method, agent_install_commands,
                            notes, is_active, created_at, updated_at
                        ) VALUES (
                            :id, :child_type, :distribution_name, :distribution_version,
                            :display_name, :install_identifier, :cloud_image_url,
                            :executable_name, :agent_install_method, :agent_install_commands,
                            :notes, true, NOW(), NOW()
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
                        "cloud_image_url": dist["cloud_image_url"],
                        "executable_name": dist["executable_name"],
                        "agent_install_method": dist["agent_install_method"],
                        "agent_install_commands": dist["agent_install_commands"],
                        "notes": dist["notes"],
                    },
                )


def downgrade() -> None:
    """Remove bhyve distributions."""
    bind = op.get_bind()

    # Remove only the distributions we seeded
    for dist in BHYVE_DISTRIBUTIONS:
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
