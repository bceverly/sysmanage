"""fix_linux_kvm_agent_install

Revision ID: r0c6t8d9v0n1
Revises: q9b5s7c8u9m0
Create Date: 2026-05-02 14:15:00.000000

The Ubuntu/Debian KVM ``agent_install_commands`` previously relied on a
Launchpad PPA (``add-apt-repository -y ppa:bceverly/sysmanage-agent``).
That has two failure modes:
  1. The PPA may not publish a package for the exact Ubuntu codename in
     question (noble, jammy, focal — release timing differs from the
     distribution catalog we ship).
  2. ``add-apt-repository`` requires ``software-properties-common``,
     which means an apt round-trip before we even know whether the PPA
     will resolve.

Switch to a direct .deb fetch from the latest GitHub release — same
pattern we already use for the FreeBSD KVM bootstrap.  The agent's
release workflow publishes a Debian .deb at
``https://github.com/bceverly/sysmanage-agent/releases/latest`` for
both Debian and Ubuntu.

Idempotent: re-running just re-sets the same string.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "r0c6t8d9v0n1"
down_revision: Union[str, None] = "q9b5s7c8u9m0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Direct .deb fetch from GitHub releases.  Mirrors the FreeBSD KVM
# bootstrap.sh (engine v0.6.x).  The cloud-init runcmd block runs each
# entry as ``sh -c "<cmd>"`` so we can chain pipelines inside one entry.
NEW_INSTALL_COMMANDS = """[
    "apt-get update",
    "apt-get install -y curl ca-certificates",
    "LATEST=$(curl -sL https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\"browser_download_url\\\": *\\\"[^\\\"]*\\\\.deb\\\"' | grep -o 'https://[^\\\"]*\\\\.deb' | head -1)",
    "curl -fL -o /tmp/sysmanage-agent.deb \\\"$LATEST\\\"",
    "DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/sysmanage-agent.deb",
    "rm -f /tmp/sysmanage-agent.deb"
]"""

# Old install commands (for downgrade) — the PPA-based path that used
# to be in the seed migrations.
OLD_INSTALL_COMMANDS = """[
    "apt-get update",
    "apt-get install -y software-properties-common",
    "add-apt-repository -y ppa:bceverly/sysmanage-agent",
    "apt-get update",
    "apt-get install -y sysmanage-agent"
]"""


def _update_commands(bind, child_type: str, name_pattern: str, commands: str) -> None:
    is_sqlite = bind.dialect.name == "sqlite"
    timestamp_expr = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
    bind.execute(
        text(
            f"""
            UPDATE child_host_distribution SET
                agent_install_commands = :agent_install_commands,
                updated_at = {timestamp_expr}
            WHERE child_type = :child_type
              AND distribution_name LIKE :name_pattern
            """
        ),
        {
            "child_type": child_type,
            "name_pattern": name_pattern,
            "agent_install_commands": commands,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    # KVM Linux guests boot from a cloud image and run cloud-init runcmd
    # — the new commands fetch the agent .deb from GitHub releases.
    _update_commands(bind, "kvm", "Ubuntu%", NEW_INSTALL_COMMANDS)
    _update_commands(bind, "kvm", "Debian%", NEW_INSTALL_COMMANDS)
    # LXD containers run the same commands inside ``lxc exec`` — same
    # fetch path works (the LXD container has curl + dpkg available).
    _update_commands(bind, "lxd", "Ubuntu%", NEW_INSTALL_COMMANDS)
    _update_commands(bind, "lxd", "Debian%", NEW_INSTALL_COMMANDS)


def downgrade() -> None:
    bind = op.get_bind()
    _update_commands(bind, "kvm", "Ubuntu%", OLD_INSTALL_COMMANDS)
    _update_commands(bind, "kvm", "Debian%", OLD_INSTALL_COMMANDS)
    _update_commands(bind, "lxd", "Ubuntu%", OLD_INSTALL_COMMANDS)
    _update_commands(bind, "lxd", "Debian%", OLD_INSTALL_COMMANDS)
