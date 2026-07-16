# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""air-gap consume-side install channels (Phase 11.8)

Revision ID: f4airgap30install
Revises: e3airgap20repo
Create Date: 2026-05-10 09:00:00.000000

Switch the per-distro ``agent_install_commands`` for the RPM-family and
SUSE-family KVM children to consume their published upstream channels
(Fedora Copr / openSUSE OBS) instead of curling sysmanage-agent rpms
directly from GitHub.

Why this matters for Phase 11
-----------------------------

GitHub-direct downloads can't be substituted with a private mirror in
an air-gapped Phase 11.2 (``role: repository``) deployment — no DNS,
no HTTPS to api.github.com.  Copr/OBS URLs CAN be substituted: the
repository engine's ``build_agent_repoint_plan`` rewrites the same
file (``/etc/yum.repos.d/sysmanage-airgap.repo`` for DNF,
``/etc/zypp/repos.d/sysmanage-airgap.repo`` for zypper) to point at
the local mirror.  So every KVM/bhyve/VMM child host on the air-gapped
side can come up with the agent installed without ever touching the
internet.

For Ubuntu/Debian, the Phase 10.4 close-out already switched to PPA
(``ppa:bceverly/sysmanage-agent``) which is substitutable the same way.
This migration leaves Ubuntu/Debian alone — they're fine.

For FreeBSD/OpenBSD/NetBSD, no upstream Copr/OBS exists; those distros
fall back to direct GitHub download or pre-staged .pkg files.  Air-gap
support for BSDs is tracked as a separate follow-up; for now the
air-gap repository engine emits a per-host repoint plan that points
``pkg`` at the local mirror, so the FreeBSD child still gets the
agent without touching the internet — just via a different path
than its first-boot script expects.

Idempotent: re-running just re-sets the same string.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "f4airgap30install"
down_revision: Union[str, None] = "e3airgap20repo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Fedora Copr install path.  ``dnf copr enable`` adds the repo, then
# ``dnf install`` pulls the package + deps.  Repository (Phase 11.2)
# overrides this at runtime by writing /etc/yum.repos.d/sysmanage-
# airgap.repo BEFORE the agent install runs.
COPR_FEDORA_RHEL_INSTALL = """[
    "dnf install -y dnf-plugins-core",
    "dnf copr enable -y bceverly/sysmanage-agent",
    "dnf install -y sysmanage-agent"
]"""

# openSUSE / SLES via OBS.  The repo URL points at home:bceverly's
# OBS project; air-gap overrides this same file with a local mirror.
OBS_OPENSUSE_INSTALL = """[
    "zypper --non-interactive ar -f https://download.opensuse.org/repositories/home:bceverly/openSUSE_Tumbleweed/home:bceverly.repo",
    "zypper --non-interactive --gpg-auto-import-keys refresh",
    "zypper --non-interactive install sysmanage-agent"
]"""

OBS_SLES_INSTALL = """[
    "zypper --non-interactive ar -f https://download.opensuse.org/repositories/home:bceverly/SLE_15_SP5/home:bceverly.repo",
    "zypper --non-interactive --gpg-auto-import-keys refresh",
    "zypper --non-interactive install sysmanage-agent"
]"""


def _update_commands(bind, name_pattern: str, commands: str) -> int:
    """Update every child_host_distribution row matching ``name_pattern``.
    Returns count of rows updated for diagnostic logging."""
    is_sqlite = bind.dialect.name == "sqlite"
    timestamp_expr = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
    result = bind.execute(
        text(
            f"""
            UPDATE child_host_distribution SET
                agent_install_commands = :commands,
                updated_at = {timestamp_expr}
            WHERE distribution_name LIKE :name_pattern
            """
        ),
        {"commands": commands, "name_pattern": name_pattern},
    )
    return result.rowcount or 0


def upgrade() -> None:
    bind = op.get_bind()
    # Fedora + RHEL family
    _update_commands(bind, "%fedora%", COPR_FEDORA_RHEL_INSTALL)
    _update_commands(bind, "%rhel%", COPR_FEDORA_RHEL_INSTALL)
    _update_commands(bind, "%rocky%", COPR_FEDORA_RHEL_INSTALL)
    _update_commands(bind, "%alma%", COPR_FEDORA_RHEL_INSTALL)
    _update_commands(bind, "%oracle%", COPR_FEDORA_RHEL_INSTALL)
    _update_commands(bind, "%centos%", COPR_FEDORA_RHEL_INSTALL)
    # openSUSE family
    _update_commands(bind, "%opensuse%", OBS_OPENSUSE_INSTALL)
    _update_commands(bind, "%tumbleweed%", OBS_OPENSUSE_INSTALL)
    # SLES — separate repo URL, different SP version
    _update_commands(bind, "%sles%", OBS_SLES_INSTALL)
    _update_commands(bind, "%suse linux enterprise%", OBS_SLES_INSTALL)


def downgrade() -> None:
    # No-op: the previous values were a mix of GitHub-direct and PPA
    # paths that we don't have a clean reverse for.  Operators
    # reverting Phase 11.8 should restore the relevant rows from a
    # backup taken before this migration ran.
    pass
