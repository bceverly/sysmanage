"""align_install_commands_to_dispatch

Revision ID: j8install08ppacopr
Revises: i7airgap60cron
Create Date: 2026-05-11 18:30:00.000000

Phase 11.8 close-out: bring ``child_host_distribution.agent_install_commands``
for every Linux distro across **kvm + lxd + vmm** child_types into
alignment with the canonical dispatch table in
``virtualization_engine._AGENT_INSTALL``.

Pre-migration state (data audit captured 2026-05-11):

  KVM — Legacy direct-download (curl + dpkg / curl + rpm -i) on:
    Ubuntu 22.04, 24.04, 26.04
    Debian 11, 12
    Oracle Linux 8, 9
    Rocky Linux 9
    AlmaLinux 9

  KVM — pip-from-PyPI (broken — sysmanage-agent is not published
  to PyPI) on:
    Fedora Server 40, 41

  LXD — Legacy direct-download on:
    Ubuntu 22.04, 24.04, 26.04
    Debian 12

  VMM — Legacy direct-download on:
    Debian 12

  VMM — pip-from-PyPI (broken — sysmanage-agent is not published to
  PyPI, every install fails) on:
    OpenBSD 7.4, 7.5, 7.6, 7.7

  Already on dispatch (kept as-is):
    KVM openSUSE Leap 15.6
    LXD AlmaLinux 9, Fedora 40, Rocky Linux 9
    VMM Ubuntu 22.04, 24.04
    Every WSL row

  Legacy-by-design — direct-download pattern is functional today,
  switches to upstream package channels when ports submissions land
  (engine flags ``legacy=True`` for these):
    KVM Alpine 3.19, 3.20
    KVM FreeBSD 13.5, 14.3, 15.0  (already use ``fetch`` + ``pkg add``
        correctly — left as-is)
    VMM Alpine 3.19, 3.20
    bhyve FreeBSD 15.0

  Not seeded — NetBSD is not currently offered as a child host
  distribution.  Adding it would be a separate seed migration once a
  NetBSD release artifact exists in the agent build pipeline.

Why this matters:
  The KVM cloud-init runcmd block embeds ``req.agent_install_commands``
  verbatim.  When that list contains the legacy direct-download recipe
  the VM's apt knows about sysmanage-agent as a one-shot ``.deb``
  install but the PPA is never registered.  Result: ``apt-get upgrade``
  never picks up new agent releases, and the in-app "Update Agent"
  button silently no-ops.

  Phase 11.8 added the dispatch table + a ``get_agent_install_commands``
  helper on the engine; the OSS plan-build path also reads from
  the engine first now (see
  ``backend/api/child_host_virtualization.py:_parse_agent_install_commands``).
  This migration ensures the DB fallback row is correct for OSS-only
  deployments that don't load the Pro+ engine.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "j8install08ppacopr"
down_revision: Union[str, None] = "i7airgap60cron"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror of ``virtualization_engine._AGENT_INSTALL`` for the Linux
# distros KVM currently provisions.  Keep this in sync with the engine
# table; the OSS plan-build path consults the engine FIRST and only
# falls back to these DB-stored commands when the engine is absent
# (OSS-only deployment).
_PPA_COMMANDS = [
    "add-apt-repository -y ppa:bceverly/sysmanage-agent",
    "apt-get update",
    "apt-get install -y sysmanage-agent",
]

_COPR_COMMANDS = [
    "dnf copr enable -y bceverly/sysmanage-agent",
    "dnf install -y sysmanage-agent",
]


def _as_json_array(cmds):
    """Render a Python list of strings as a JSON array literal suitable
    for the ``agent_install_commands`` text column.  We don't use
    ``json.dumps`` because the existing column values are hand-formatted
    with 4-space indentation and the prior migrations followed the same
    style — keeping it visually consistent on inspection."""
    body = ",\n        ".join('"' + c.replace('"', '\\"') + '"' for c in cmds)
    return "[\n        " + body + "\n    ]"


_TARGETS_PPA = [
    # (child_type, distribution_name, distribution_version)
    ("kvm", "Ubuntu", "22.04"),
    ("kvm", "Ubuntu", "24.04"),
    ("kvm", "Ubuntu", "26.04"),
    ("kvm", "Debian", "11"),
    ("kvm", "Debian", "12"),
    ("lxd", "Ubuntu", "22.04"),
    ("lxd", "Ubuntu", "24.04"),
    ("lxd", "Ubuntu", "26.04"),
    ("lxd", "Debian", "12"),
    ("vmm", "Debian", "12"),
]

_TARGETS_COPR = [
    ("kvm", "Fedora Server", "40"),
    ("kvm", "Fedora Server", "41"),
    ("kvm", "Oracle Linux", "8"),
    ("kvm", "Oracle Linux", "9"),
    ("kvm", "Rocky Linux", "9"),
    ("kvm", "AlmaLinux", "9"),
]


def _openbsd_commands(version_nodot: str) -> list:
    """Per-OpenBSD-version direct-download commands.

    Mirrors the FreeBSD ``fetch`` + ``pkg add`` pattern but adapted for
    OpenBSD's tooling:
      * ``ftp(1)`` instead of ``fetch`` (OpenBSD's base HTTP client)
      * ``pkg_add -D unsigned`` on a local ``.tgz`` (the release tarball
        is checksummed via ``.sha256`` but not signed with an OpenBSD
        signing key, so signature verification has to be explicitly
        bypassed for local installs)
      * ``rcctl`` for service management

    The artifact URL embeds the OpenBSD version without dots (``77``
    for 7.7, ``74`` for 7.4, etc.) because the build pipeline's
    OpenBSD job emits ``sysmanage-agent-${VERSION}-openbsd${NODOT}.tgz``
    (see ``.github/workflows/build-and-release.yml`` line 1654 in
    sysmanage-agent).
    """
    api_url = (
        "https://api.github.com/repos/bceverly/sysmanage-agent/"
        "releases/latest"
    )
    release_url = (
        "https://github.com/bceverly/sysmanage-agent/releases/download/"
        "${LATEST}/sysmanage-agent-${VERSION}-openbsd" + version_nodot + ".tgz"
    )
    return [
        # ftp -V silences progress; ``-o -`` writes the API JSON to
        # stdout.  Grep extracts the ``tag_name`` field.
        (
            "LATEST=$(ftp -V -o - " + api_url +
            " | grep -o '\"tag_name\": *\"[^\"]*\"' | "
            "grep -o 'v[0-9.]*')"
        ),
        "VERSION=${LATEST#v}",
        "ftp -V -o /tmp/sysmanage-agent.tgz " + release_url,
        "pkg_add -D unsigned /tmp/sysmanage-agent.tgz",
        "rm -f /tmp/sysmanage-agent.tgz",
        "rcctl enable sysmanage_agent",
        "rcctl start sysmanage_agent",
    ]


# (child_type, distribution_name, distribution_version, openbsd_version_nodot)
_TARGETS_OPENBSD = [
    ("vmm", "OpenBSD", "7.4", "74"),
    ("vmm", "OpenBSD", "7.5", "75"),
    ("vmm", "OpenBSD", "7.6", "76"),
    ("vmm", "OpenBSD", "7.7", "77"),
]


def upgrade() -> None:
    bind = op.get_bind()
    ppa_json = _as_json_array(_PPA_COMMANDS)
    copr_json = _as_json_array(_COPR_COMMANDS)

    for child_type, name, version in _TARGETS_PPA:
        bind.execute(
            text(
                "UPDATE child_host_distribution "
                "SET agent_install_commands = :cmds, updated_at = CURRENT_TIMESTAMP "
                "WHERE child_type = :ct AND distribution_name = :dn "
                "AND distribution_version = :dv"
            ),
            {"cmds": ppa_json, "ct": child_type, "dn": name, "dv": version},
        )

    for child_type, name, version in _TARGETS_COPR:
        bind.execute(
            text(
                "UPDATE child_host_distribution "
                "SET agent_install_commands = :cmds, updated_at = CURRENT_TIMESTAMP "
                "WHERE child_type = :ct AND distribution_name = :dn "
                "AND distribution_version = :dv"
            ),
            {"cmds": copr_json, "ct": child_type, "dn": name, "dv": version},
        )

    # OpenBSD: per-version command list (URL encodes the OS version
    # number without dots).  These rows were broken pre-migration
    # because they tried to pip-install sysmanage-agent from PyPI
    # (which doesn't host the package).
    for child_type, name, version, nodot in _TARGETS_OPENBSD:
        bind.execute(
            text(
                "UPDATE child_host_distribution "
                "SET agent_install_commands = :cmds, updated_at = CURRENT_TIMESTAMP "
                "WHERE child_type = :ct AND distribution_name = :dn "
                "AND distribution_version = :dv"
            ),
            {
                "cmds": _as_json_array(_openbsd_commands(nodot)),
                "ct": child_type,
                "dn": name,
                "dv": version,
            },
        )


def downgrade() -> None:
    # Restoring the exact prior values for every row is not feasible —
    # each (distro, version) had slightly different curl URL patterns
    # baked in.  The downgrade path resets the column to NULL so the
    # caller falls back entirely to the engine's dispatch table (or,
    # if the engine isn't loaded, gets an empty install list — which
    # is the same failure mode as a missing distribution row, surfacing
    # the misconfiguration loudly rather than silently shipping a stale
    # recipe).
    bind = op.get_bind()
    rows = (
        _TARGETS_PPA
        + _TARGETS_COPR
        + [(t[0], t[1], t[2]) for t in _TARGETS_OPENBSD]
    )
    for child_type, name, version in rows:
        bind.execute(
            text(
                "UPDATE child_host_distribution "
                "SET agent_install_commands = NULL, updated_at = CURRENT_TIMESTAMP "
                "WHERE child_type = :ct AND distribution_name = :dn "
                "AND distribution_version = :dv"
            ),
            {"ct": child_type, "dn": name, "dv": version},
        )
