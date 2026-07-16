# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_ubuntu_26_04_distributions

Revision ID: s1ub26041tsa
Revises: r0c6t8d9v0n1
Create Date: 2026-05-01 12:00:00.000000

This migration seeds the child_host_distribution table with Ubuntu 26.04 LTS
entries for the LXD, KVM, and WSL child host types. Ubuntu 26.04 LTS has been
released, so it should be selectable wherever earlier Ubuntu LTS versions are.

The migration is fully idempotent: each row is checked first and either
inserted or updated. It is safe to re-run, and works on both SQLite and
PostgreSQL (the only difference is the timestamp expression).
"""

import uuid
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "s1ub26041tsa"
down_revision: Union[str, None] = "r0c6t8d9v0n1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Shared apt+PPA agent install snippet for Ubuntu 26.04 (matches existing
# Ubuntu 22.04 / 24.04 commands in the seed migrations).
UBUNTU_LXD_WSL_APT_PPA_COMMANDS = """[
    "apt-get update",
    "apt-get install -y software-properties-common",
    "add-apt-repository -y ppa:bceverly/sysmanage-agent",
    "apt-get update",
    "apt-get install -y sysmanage-agent"
]"""


# Ubuntu 26.04 LTS rows to upsert. install_identifier varies by child_type:
#   - lxd: container image alias (e.g. ubuntu:26.04)
#   - kvm: cloud image URL (also stored in cloud_image_url column)
#   - wsl: WSL distro identifier (also has executable_name)
UBUNTU_26_04_DISTRIBUTIONS = [
    {
        "child_type": "lxd",
        "distribution_name": "Ubuntu",
        "distribution_version": "26.04",
        "display_name": "Ubuntu 26.04 LTS",
        "install_identifier": "ubuntu:26.04",
        "executable_name": None,
        "cloud_image_url": None,
        "iso_url": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": UBUNTU_LXD_WSL_APT_PPA_COMMANDS,
        "notes": "Ubuntu 26.04 LTS - Long Term Support",
    },
    {
        "child_type": "kvm",
        "distribution_name": "Ubuntu Server",
        "distribution_version": "26.04",
        "display_name": "Ubuntu Server 26.04 LTS",
        "install_identifier": (
            "https://cloud-images.ubuntu.com/releases/26.04/release/"
            "ubuntu-26.04-server-cloudimg-amd64.img"
        ),
        "executable_name": None,
        "cloud_image_url": (
            "https://cloud-images.ubuntu.com/releases/26.04/release/"
            "ubuntu-26.04-server-cloudimg-amd64.img"
        ),
        "iso_url": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": UBUNTU_LXD_WSL_APT_PPA_COMMANDS,
        "notes": "Ubuntu Server 26.04 LTS - Cloud image with cloud-init support",
    },
    {
        "child_type": "wsl",
        "distribution_name": "Ubuntu",
        "distribution_version": "26.04",
        "display_name": "Ubuntu 26.04 LTS",
        "install_identifier": "Ubuntu-26.04",
        "executable_name": "ubuntu2604.exe",
        "cloud_image_url": None,
        "iso_url": None,
        "agent_install_method": "apt_launchpad",
        "agent_install_commands": UBUNTU_LXD_WSL_APT_PPA_COMMANDS,
        "notes": "Ubuntu 26.04 LTS - Long Term Support",
    },
]


def _column_exists(bind, table: str, column: str) -> bool:
    """Return True if `column` exists on `table` for the active dialect."""
    dialect = bind.dialect.name
    if dialect == "sqlite":
        rows = bind.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in rows)
    # postgresql / others
    result = bind.execute(
        text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


def _exists(bind, dist) -> bool:
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
    return (result.scalar() or 0) > 0


def _update(bind, dist, has_cloud_columns: bool) -> None:
    is_sqlite = bind.dialect.name == "sqlite"
    now_expr = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
    extra_assigns = ""
    params = {
        "child_type": dist["child_type"],
        "distribution_name": dist["distribution_name"],
        "distribution_version": dist["distribution_version"],
        "display_name": dist["display_name"],
        "install_identifier": dist["install_identifier"],
        "executable_name": dist["executable_name"],
        "agent_install_method": dist["agent_install_method"],
        "agent_install_commands": dist["agent_install_commands"],
        "notes": dist["notes"],
    }
    if has_cloud_columns:
        extra_assigns = (
            ",\n                    cloud_image_url = :cloud_image_url"
            ",\n                    iso_url = :iso_url"
        )
        params["cloud_image_url"] = dist["cloud_image_url"]
        params["iso_url"] = dist["iso_url"]

    bind.execute(
        text(
            f"""
            UPDATE child_host_distribution SET
                display_name = :display_name,
                install_identifier = :install_identifier,
                executable_name = :executable_name,
                agent_install_method = :agent_install_method,
                agent_install_commands = :agent_install_commands,
                notes = :notes{extra_assigns},
                updated_at = {now_expr}
            WHERE child_type = :child_type
              AND distribution_name = :distribution_name
              AND distribution_version = :distribution_version
            """
        ),
        params,
    )


def _insert(bind, dist, has_cloud_columns: bool) -> None:
    is_sqlite = bind.dialect.name == "sqlite"
    now_expr = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
    is_active_expr = "1" if is_sqlite else "true"

    extra_cols = ""
    extra_vals = ""
    params = {
        "id": str(uuid.uuid4()),
        "child_type": dist["child_type"],
        "distribution_name": dist["distribution_name"],
        "distribution_version": dist["distribution_version"],
        "display_name": dist["display_name"],
        "install_identifier": dist["install_identifier"],
        "executable_name": dist["executable_name"],
        "agent_install_method": dist["agent_install_method"],
        "agent_install_commands": dist["agent_install_commands"],
        "notes": dist["notes"],
    }
    if has_cloud_columns:
        extra_cols = ", cloud_image_url, iso_url"
        extra_vals = ", :cloud_image_url, :iso_url"
        params["cloud_image_url"] = dist["cloud_image_url"]
        params["iso_url"] = dist["iso_url"]

    bind.execute(
        text(
            f"""
            INSERT INTO child_host_distribution (
                id, child_type, distribution_name, distribution_version,
                display_name, install_identifier, executable_name,
                agent_install_method, agent_install_commands, notes,
                is_active, created_at, updated_at{extra_cols}
            ) VALUES (
                :id, :child_type, :distribution_name, :distribution_version,
                :display_name, :install_identifier, :executable_name,
                :agent_install_method, :agent_install_commands, :notes,
                {is_active_expr}, {now_expr}, {now_expr}{extra_vals}
            )
            """
        ),
        params,
    )


def upgrade() -> None:
    """Seed Ubuntu 26.04 LTS rows for lxd / kvm / wsl child types."""
    bind = op.get_bind()
    has_cloud_columns = _column_exists(
        bind, "child_host_distribution", "cloud_image_url"
    ) and _column_exists(bind, "child_host_distribution", "iso_url")

    for dist in UBUNTU_26_04_DISTRIBUTIONS:
        if _exists(bind, dist):
            _update(bind, dist, has_cloud_columns)
        else:
            _insert(bind, dist, has_cloud_columns)


def downgrade() -> None:
    """Remove the Ubuntu 26.04 LTS rows seeded above."""
    bind = op.get_bind()

    for dist in UBUNTU_26_04_DISTRIBUTIONS:
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
