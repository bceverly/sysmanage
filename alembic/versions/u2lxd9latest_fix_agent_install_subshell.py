"""fix_agent_install_subshell

Revision ID: u2lxd9latest
Revises: t1ubu26nlts
Create Date: 2026-05-04 11:50:00.000000

The Linux KVM/LXD ``agent_install_commands`` introduced by
``r0c6t8d9v0n1`` captured the GitHub release URL into a shell variable
``LATEST`` in one entry, then referenced ``$LATEST`` in the next:

    "LATEST=$(curl -sL .../releases/latest | grep ... | head -1)",
    "curl -fL -o /tmp/sysmanage-agent.deb \"$LATEST\"",

That works in cloud-init's ``runcmd`` block on KVM **only** if the two
entries happen to share a process — which they don't, each runcmd
entry is a fresh ``sh -c``.  And it definitely doesn't work on LXD,
where each entry runs as a separate ``lxc exec ... -- sh -c '<cmd>'``
invocation: the variable evaporates between processes.

Fix: collapse the LATEST capture and the curl download into a single
entry using command substitution, so the URL is computed in the same
subshell that consumes it.  Five entries instead of six.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "u2lxd9latest"
down_revision: Union[str, None] = "t1ubu26nlts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Self-contained per-entry: the inner ``$(...)`` runs in the same
# subshell as the outer ``curl``, so no cross-entry variable leakage.
FIXED_INSTALL_COMMANDS = """[
    "apt-get update",
    "apt-get install -y curl ca-certificates",
    "curl -fL -o /tmp/sysmanage-agent.deb $(curl -sL https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\"browser_download_url\\\": *\\\"[^\\\"]*\\\\.deb\\\"' | grep -o 'https://[^\\\"]*\\\\.deb' | head -1)",
    "DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/sysmanage-agent.deb",
    "rm -f /tmp/sysmanage-agent.deb"
]"""

# The broken six-entry form from r0c6t8d9v0n1 — used by downgrade().
BROKEN_INSTALL_COMMANDS = """[
    "apt-get update",
    "apt-get install -y curl ca-certificates",
    "LATEST=$(curl -sL https://api.github.com/repos/bceverly/sysmanage-agent/releases/latest | grep -o '\\\"browser_download_url\\\": *\\\"[^\\\"]*\\\\.deb\\\"' | grep -o 'https://[^\\\"]*\\\\.deb' | head -1)",
    "curl -fL -o /tmp/sysmanage-agent.deb \\\"$LATEST\\\"",
    "DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/sysmanage-agent.deb",
    "rm -f /tmp/sysmanage-agent.deb"
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
    _update_commands(bind, "kvm", "Ubuntu%", FIXED_INSTALL_COMMANDS)
    _update_commands(bind, "kvm", "Debian%", FIXED_INSTALL_COMMANDS)
    _update_commands(bind, "lxd", "Ubuntu%", FIXED_INSTALL_COMMANDS)
    _update_commands(bind, "lxd", "Debian%", FIXED_INSTALL_COMMANDS)


def downgrade() -> None:
    bind = op.get_bind()
    _update_commands(bind, "kvm", "Ubuntu%", BROKEN_INSTALL_COMMANDS)
    _update_commands(bind, "kvm", "Debian%", BROKEN_INSTALL_COMMANDS)
    _update_commands(bind, "lxd", "Ubuntu%", BROKEN_INSTALL_COMMANDS)
    _update_commands(bind, "lxd", "Debian%", BROKEN_INSTALL_COMMANDS)
