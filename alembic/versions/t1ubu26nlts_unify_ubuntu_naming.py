"""unify_ubuntu_distribution_naming

Revision ID: t1ubu26nlts
Revises: s1ub26041tsa
Create Date: 2026-05-02 19:15:00.000000

Two related cleanups so the host-detail Distribution column reads
consistently across hypervisors:

1. Unify ``Ubuntu Server`` → ``Ubuntu`` across kvm/vmm child-host
   distributions (lxd/wsl already use ``Ubuntu``).  Display names drop
   the "Server" suffix so a kvm guest reads "Ubuntu 24.04 LTS" not
   "Ubuntu Server 24.04 LTS".

2. Map any Ubuntu-codename that leaked into ``host_child.distribution_version``
   back to the numeric release.  The agent's ``child_host_listing``
   parser maps codenames → versions but its map was missing the recent
   ones (oracular / plucky / questing / resolute), so 26.04 LXD
   containers ended up with ``distribution_version = 'resolute'``.
   Forward-looking fix is the agent's map (separate change); this
   migration cleans up rows already inserted with the codename.

The migration is fully idempotent: every UPDATE checks the current
value before writing.  Works on both PostgreSQL and SQLite — no
dialect-specific syntax used.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "t1ubu26nlts"
down_revision: Union[str, None] = "s1ub26041tsa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Forward map: Ubuntu codename → numeric release.  Mirrors the (newly
# extended) agent-side map in
# ``sysmanage-agent/src/sysmanage_agent/operations/child_host_listing.py``.
UBUNTU_CODENAME_TO_VERSION = {
    "xenial": "16.04",
    "bionic": "18.04",
    "focal": "20.04",
    "groovy": "20.10",
    "hirsute": "21.04",
    "impish": "21.10",
    "jammy": "22.04",
    "kinetic": "22.10",
    "lunar": "23.04",
    "mantic": "23.10",
    "noble": "24.04",
    "oracular": "24.10",
    "plucky": "25.04",
    "questing": "25.10",
    "resolute": "26.04",
}

DEBIAN_CODENAME_TO_VERSION = {
    "buster": "10",
    "bullseye": "11",
    "bookworm": "12",
    "trixie": "13",
}


def upgrade() -> None:
    """Unify Ubuntu Server → Ubuntu and remap codenames to versions."""
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. child_host_distribution: rename "Ubuntu Server" → "Ubuntu"
    #    Drop the "Server" suffix from display_name.
    # ------------------------------------------------------------------
    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET distribution_name = 'Ubuntu',
                display_name = REPLACE(display_name, 'Ubuntu Server', 'Ubuntu')
            WHERE distribution_name = 'Ubuntu Server'
            """
        )
    )

    # ------------------------------------------------------------------
    # 2. host_child: rename live "Ubuntu Server" rows to "Ubuntu" so
    #    the host-detail column matches the new naming.
    # ------------------------------------------------------------------
    bind.execute(
        text(
            """
            UPDATE host_child
            SET distribution = 'Ubuntu'
            WHERE distribution = 'Ubuntu Server'
            """
        )
    )

    # ------------------------------------------------------------------
    # 3. host_child: remap leaked Ubuntu codenames →
    #    numeric versions (e.g. 'resolute' → '26.04').
    # ------------------------------------------------------------------
    for codename, version in UBUNTU_CODENAME_TO_VERSION.items():
        bind.execute(
            text(
                """
                UPDATE host_child
                SET distribution_version = :version
                WHERE distribution = 'Ubuntu'
                  AND distribution_version = :codename
                """
            ),
            {"codename": codename, "version": version},
        )

    # ------------------------------------------------------------------
    # 4. host_child: same for Debian codenames (defensive — same agent
    #    code path could leak Debian codenames if a non-LTS version
    #    ships before the agent map is updated).
    # ------------------------------------------------------------------
    for codename, version in DEBIAN_CODENAME_TO_VERSION.items():
        bind.execute(
            text(
                """
                UPDATE host_child
                SET distribution_version = :version
                WHERE distribution = 'Debian'
                  AND distribution_version = :codename
                """
            ),
            {"codename": codename, "version": version},
        )


def downgrade() -> None:
    """Reverse the rename (best-effort).

    The codename → version remap is NOT reversed — there's no way to
    know which version-numbered rows were originally codenames vs which
    were always numeric, and re-introducing codenames would re-create
    the inconsistency this migration was meant to fix.
    """
    bind = op.get_bind()

    bind.execute(
        text(
            """
            UPDATE child_host_distribution
            SET distribution_name = 'Ubuntu Server',
                display_name = REPLACE(display_name, 'Ubuntu ', 'Ubuntu Server ')
            WHERE child_type IN ('kvm', 'vmm')
              AND distribution_name = 'Ubuntu'
            """
        )
    )

    bind.execute(
        text(
            """
            UPDATE host_child
            SET distribution = 'Ubuntu Server'
            WHERE child_type IN ('kvm', 'vmm')
              AND distribution = 'Ubuntu'
            """
        )
    )
