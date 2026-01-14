"""update_bhyve_freebsd_versions

Revision ID: g2h3i4j5k6l7
Revises: f1g2h3i4j5k6
Create Date: 2026-01-14 12:00:00.000000

This migration updates the bhyve FreeBSD distributions to currently available versions.
FreeBSD 13.4, 14.1, and 14.2 have been archived and are no longer available.

Changes:
- Updates FreeBSD 13.4 to 13.5
- Updates FreeBSD 14.1 to 14.3 (removes duplicate, keeps one 14.x version)
- Updates FreeBSD 14.2 to 14.3
- Adds FreeBSD 15.0 as the newest release
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text
import uuid


# revision identifiers, used by Alembic.
revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, None] = "f1g2h3i4j5k6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Agent install commands for FreeBSD (shared by all versions)
FREEBSD_AGENT_INSTALL_COMMANDS = """[
    "LATEST=$(fetch -q -o - https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\\"tag_name\\\\": *\\\\"[^\\\\"]*\\\\"' | grep -o 'v[0-9.]*')",
    "VERSION=${LATEST#v}",
    "fetch -o /tmp/sysmanage-agent-${VERSION}.pkg https://github.com/bceverly/sysmanage-agent/releases/download/${LATEST}/sysmanage-agent-${VERSION}.pkg",
    "test $(stat -f%z /tmp/sysmanage-agent-${VERSION}.pkg 2>/dev/null || echo 0) -gt 10000 || (echo 'Download failed - file too small' && exit 1)",
    "cd / && tar -xf /tmp/sysmanage-agent-${VERSION}.pkg --include='usr/*'",
    "sysrc sysmanage_agent_enable=YES",
    "sysrc sysmanage_agent_user=root",
    "service sysmanage_agent restart 2>/dev/null || service sysmanage_agent start"
]"""


def upgrade() -> None:
    """Update bhyve FreeBSD distributions to currently available versions."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Step 1: Update FreeBSD 13.4 to 13.5
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '13.5',
                    display_name = 'FreeBSD 13.5-RELEASE',
                    install_identifier = 'FreeBSD-13.5',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/13.5-RELEASE/amd64/Latest/FreeBSD-13.5-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 13.5-RELEASE - Extended support release. Native bhyve guest with cloud-init support.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '13.4'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '13.5',
                    display_name = 'FreeBSD 13.5-RELEASE',
                    install_identifier = 'FreeBSD-13.5',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/13.5-RELEASE/amd64/Latest/FreeBSD-13.5-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 13.5-RELEASE - Extended support release. Native bhyve guest with cloud-init support.',
                    updated_at = NOW()
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '13.4'
                """
            )
        )

    # Step 2: Update FreeBSD 14.2 to 14.3
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '14.3',
                    display_name = 'FreeBSD 14.3-RELEASE',
                    install_identifier = 'FreeBSD-14.3',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/14.3-RELEASE/amd64/Latest/FreeBSD-14.3-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 14.3-RELEASE - Current stable release. Native bhyve guest with cloud-init support.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '14.2'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '14.3',
                    display_name = 'FreeBSD 14.3-RELEASE',
                    install_identifier = 'FreeBSD-14.3',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/14.3-RELEASE/amd64/Latest/FreeBSD-14.3-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 14.3-RELEASE - Current stable release. Native bhyve guest with cloud-init support.',
                    updated_at = NOW()
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '14.2'
                """
            )
        )

    # Step 3: Remove FreeBSD 14.1 (duplicate - we now have 14.3)
    bind.execute(
        text(
            """
            DELETE FROM child_host_distribution
            WHERE child_type = 'bhyve'
              AND distribution_name = 'FreeBSD'
              AND distribution_version = '14.1'
            """
        )
    )

    # Step 4: Add FreeBSD 15.0 if it doesn't exist
    result = bind.execute(
        text(
            """
            SELECT COUNT(*) FROM child_host_distribution
            WHERE child_type = 'bhyve'
              AND distribution_name = 'FreeBSD'
              AND distribution_version = '15.0'
            """
        )
    )
    if result.scalar() == 0:
        dist_id = str(uuid.uuid4())
        if is_sqlite:
            bind.execute(
                text(
                    """
                    INSERT INTO child_host_distribution (
                        id, child_type, distribution_name, distribution_version,
                        display_name, install_identifier, cloud_image_url, executable_name,
                        agent_install_method, agent_install_commands, notes,
                        is_active, created_at, updated_at
                    ) VALUES (
                        :id, 'bhyve', 'FreeBSD', '15.0',
                        'FreeBSD 15.0-RELEASE', 'FreeBSD-15.0',
                        'https://download.freebsd.org/releases/VM-IMAGES/15.0-RELEASE/amd64/Latest/FreeBSD-15.0-RELEASE-amd64.raw.xz',
                        NULL, 'pkg', :agent_commands,
                        'FreeBSD 15.0-RELEASE - Newest release. Native bhyve guest with cloud-init support.',
                        1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": dist_id, "agent_commands": FREEBSD_AGENT_INSTALL_COMMANDS},
            )
        else:
            bind.execute(
                text(
                    """
                    INSERT INTO child_host_distribution (
                        id, child_type, distribution_name, distribution_version,
                        display_name, install_identifier, cloud_image_url, executable_name,
                        agent_install_method, agent_install_commands, notes,
                        is_active, created_at, updated_at
                    ) VALUES (
                        :id, 'bhyve', 'FreeBSD', '15.0',
                        'FreeBSD 15.0-RELEASE', 'FreeBSD-15.0',
                        'https://download.freebsd.org/releases/VM-IMAGES/15.0-RELEASE/amd64/Latest/FreeBSD-15.0-RELEASE-amd64.raw.xz',
                        NULL, 'pkg', :agent_commands,
                        'FreeBSD 15.0-RELEASE - Newest release. Native bhyve guest with cloud-init support.',
                        true, NOW(), NOW()
                    )
                    """
                ),
                {"id": dist_id, "agent_commands": FREEBSD_AGENT_INSTALL_COMMANDS},
            )

    # Step 5: Ensure 13.5 and 14.3 have correct URLs (idempotent)
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    display_name = 'FreeBSD 13.5-RELEASE',
                    install_identifier = 'FreeBSD-13.5',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/13.5-RELEASE/amd64/Latest/FreeBSD-13.5-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 13.5-RELEASE - Extended support release. Native bhyve guest with cloud-init support.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '13.5'
                """
            )
        )
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    display_name = 'FreeBSD 14.3-RELEASE',
                    install_identifier = 'FreeBSD-14.3',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/14.3-RELEASE/amd64/Latest/FreeBSD-14.3-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 14.3-RELEASE - Current stable release. Native bhyve guest with cloud-init support.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '14.3'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    display_name = 'FreeBSD 13.5-RELEASE',
                    install_identifier = 'FreeBSD-13.5',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/13.5-RELEASE/amd64/Latest/FreeBSD-13.5-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 13.5-RELEASE - Extended support release. Native bhyve guest with cloud-init support.',
                    updated_at = NOW()
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '13.5'
                """
            )
        )
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    display_name = 'FreeBSD 14.3-RELEASE',
                    install_identifier = 'FreeBSD-14.3',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/14.3-RELEASE/amd64/Latest/FreeBSD-14.3-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 14.3-RELEASE - Current stable release. Native bhyve guest with cloud-init support.',
                    updated_at = NOW()
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '14.3'
                """
            )
        )


def downgrade() -> None:
    """Revert bhyve FreeBSD versions (note: old URLs no longer work)."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Remove 15.0
    bind.execute(
        text(
            """
            DELETE FROM child_host_distribution
            WHERE child_type = 'bhyve'
              AND distribution_name = 'FreeBSD'
              AND distribution_version = '15.0'
            """
        )
    )

    # Revert 14.3 back to 14.2 (note: URL won't work)
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '14.2',
                    display_name = 'FreeBSD 14.2-RELEASE',
                    install_identifier = 'FreeBSD-14.2',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/14.2-RELEASE/amd64/Latest/FreeBSD-14.2-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 14.2-RELEASE - Current stable release. Native bhyve guest with cloud-init support.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '14.3'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '14.2',
                    display_name = 'FreeBSD 14.2-RELEASE',
                    install_identifier = 'FreeBSD-14.2',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/14.2-RELEASE/amd64/Latest/FreeBSD-14.2-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 14.2-RELEASE - Current stable release. Native bhyve guest with cloud-init support.',
                    updated_at = NOW()
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '14.3'
                """
            )
        )

    # Revert 13.5 back to 13.4 (note: URL won't work)
    if is_sqlite:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '13.4',
                    display_name = 'FreeBSD 13.4-RELEASE',
                    install_identifier = 'FreeBSD-13.4',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/13.4-RELEASE/amd64/Latest/FreeBSD-13.4-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 13.4-RELEASE - Extended support release. Native bhyve guest with cloud-init support.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '13.5'
                """
            )
        )
    else:
        bind.execute(
            text(
                """
                UPDATE child_host_distribution SET
                    distribution_version = '13.4',
                    display_name = 'FreeBSD 13.4-RELEASE',
                    install_identifier = 'FreeBSD-13.4',
                    cloud_image_url = 'https://download.freebsd.org/releases/VM-IMAGES/13.4-RELEASE/amd64/Latest/FreeBSD-13.4-RELEASE-amd64.raw.xz',
                    notes = 'FreeBSD 13.4-RELEASE - Extended support release. Native bhyve guest with cloud-init support.',
                    updated_at = NOW()
                WHERE child_type = 'bhyve'
                  AND distribution_name = 'FreeBSD'
                  AND distribution_version = '13.5'
                """
            )
        )

    # Note: We don't restore 14.1 as it was a duplicate entry
