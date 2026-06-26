"""create shared_mirror_known_version (Phase 13.1.D)

First migration in the **shared** reference-data chain.  Relocates the mirror
version catalog out of the per-tenant partition (where ``c1mirror50dropdown``
originally created ``mirror_known_version``) into the ``shared`` partition as
``shared_mirror_known_version``.  This catalog is canonical reference data —
identical for every tenant — so it lives once in the shared database instead of
being copied into each tenant database.

The data is migration-seeded reference data (no user-created rows), so the
relocation carries no data-loss risk: the tenant copy is dropped by a sibling
tenant-chain migration, and this migration re-seeds the canonical set here.  The
seed mirrors the post-``u1mirror60ubresolute`` state (26.04 = resolute, 25.10 =
questing added).

Idempotent and identical on SQLite (test) + PostgreSQL (prod): the table is
created only if absent, and each seed row is matched on (platform, version_key)
so re-running inserts nothing new.

Revision ID: s1shared
Revises:
Create Date: 2026-06-25
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

from backend.persistence.models.core import GUID

revision: str = "s1shared"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "shared_mirror_known_version"

# Canonical version catalog — keep in sync with the engine's known-good
# upstreams.  Columns: (platform, version_key, label, os_family, match_regex,
# default_upstream_url, default_suite, default_repoid, default_repo_alias,
# default_release).
_KNOWN_VERSIONS = [
    # ----- APT family -----
    (
        "apt",
        "ubuntu-24.04",
        "Ubuntu 24.04 (noble)",
        "ubuntu",
        r"ubuntu\s*24\.04|noble",
        "http://archive.ubuntu.com/ubuntu",
        "noble",
        None,
        None,
        None,
    ),
    (
        "apt",
        "ubuntu-22.04",
        "Ubuntu 22.04 (jammy)",
        "ubuntu",
        r"ubuntu\s*22\.04|jammy",
        "http://archive.ubuntu.com/ubuntu",
        "jammy",
        None,
        None,
        None,
    ),
    (
        "apt",
        "ubuntu-26.04",
        "Ubuntu 26.04 (resolute)",
        "ubuntu",
        r"ubuntu\s*26\.04|resolute",
        "http://archive.ubuntu.com/ubuntu",
        "resolute",
        None,
        None,
        None,
    ),
    (
        "apt",
        "ubuntu-25.10",
        "Ubuntu 25.10 (questing)",
        "ubuntu",
        r"ubuntu\s*25\.10|questing",
        "http://archive.ubuntu.com/ubuntu",
        "questing",
        None,
        None,
        None,
    ),
    (
        "apt",
        "debian-12",
        "Debian 12 (bookworm)",
        "debian",
        r"debian\s*12|bookworm",
        "http://deb.debian.org/debian",
        "bookworm",
        None,
        None,
        None,
    ),
    (
        "apt",
        "debian-11",
        "Debian 11 (bullseye)",
        "debian",
        r"debian\s*11|bullseye",
        "http://deb.debian.org/debian",
        "bullseye",
        None,
        None,
        None,
    ),
    # ----- DNF family -----
    (
        "dnf",
        "ol9-baseos",
        "Oracle Linux 9 — BaseOS",
        "oracle",
        r"\.el9|oracle\s*linux\s*9",
        "https://yum.oracle.com/repo/OracleLinux/OL9/baseos/latest/x86_64",
        None,
        "ol9_baseos_latest",
        None,
        None,
    ),
    (
        "dnf",
        "rhel9-baseos",
        "RHEL 9 — BaseOS",
        "rhel",
        r"\.el9|red\s*hat.*9|rhel.*9",
        "https://cdn.redhat.com/content/dist/rhel9/9/x86_64/baseos/os/",
        None,
        "rhel-9-for-x86_64-baseos-rpms",
        None,
        None,
    ),
    (
        "dnf",
        "rocky9-baseos",
        "Rocky Linux 9 — BaseOS",
        "rocky",
        r"\.el9|rocky.*9",
        "https://dl.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/",
        None,
        "rocky-9-baseos",
        None,
        None,
    ),
    (
        "dnf",
        "alma9-baseos",
        "AlmaLinux 9 — BaseOS",
        "alma",
        r"\.el9|almalinux.*9",
        "https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/",
        None,
        "alma-9-baseos",
        None,
        None,
    ),
    (
        "dnf",
        "fedora-41",
        "Fedora 41 — Everything",
        "fedora",
        r"\.fc41|fedora.*41",
        "https://dl.fedoraproject.org/pub/fedora/linux/releases/41/Everything/x86_64/os/",
        None,
        "fedora-41-everything",
        None,
        None,
    ),
    (
        "dnf",
        "fedora-40",
        "Fedora 40 — Everything",
        "fedora",
        r"\.fc40|fedora.*40",
        "https://dl.fedoraproject.org/pub/fedora/linux/releases/40/Everything/x86_64/os/",
        None,
        "fedora-40-everything",
        None,
        None,
    ),
    # ----- zypper family -----
    (
        "zypper",
        "leap-15.6",
        "openSUSE Leap 15.6 — OSS",
        "opensuse-leap",
        r"opensuse.*15\.6|leap.*15\.6",
        "http://download.opensuse.org/distribution/leap/15.6/repo/oss/",
        None,
        None,
        "leap-15-6-oss",
        None,
    ),
    (
        "zypper",
        "leap-15.5",
        "openSUSE Leap 15.5 — OSS",
        "opensuse-leap",
        r"opensuse.*15\.5|leap.*15\.5",
        "http://download.opensuse.org/distribution/leap/15.5/repo/oss/",
        None,
        None,
        "leap-15-5-oss",
        None,
    ),
    (
        "zypper",
        "sles-15-sp6",
        "SLES 15 SP6",
        "sles",
        r"sles.*15.*sp6|sle.*15\.6",
        "https://updates.suse.com/SUSE/Updates/SLE-Module-Basesystem/15-SP6/x86_64/update/",
        None,
        None,
        "sles-15-sp6-base",
        None,
    ),
    # ----- pkg family -----
    (
        "pkg",
        "freebsd-14",
        "FreeBSD 14 — quarterly (amd64)",
        "freebsd",
        r"freebsd\s*14",
        "https://pkg.FreeBSD.org/FreeBSD:14:amd64/quarterly",
        None,
        None,
        None,
        "FreeBSD:14:amd64",
    ),
    (
        "pkg",
        "freebsd-13",
        "FreeBSD 13 — quarterly (amd64)",
        "freebsd",
        r"freebsd\s*13",
        "https://pkg.FreeBSD.org/FreeBSD:13:amd64/quarterly",
        None,
        None,
        None,
        "FreeBSD:13:amd64",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("version_key", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=200), nullable=False),
            sa.Column("os_family", sa.String(length=40), nullable=False),
            sa.Column("match_regex", sa.String(length=400), nullable=False),
            sa.Column("default_upstream_url", sa.String(length=500), nullable=False),
            sa.Column("default_suite", sa.String(length=80), nullable=True),
            sa.Column("default_repoid", sa.String(length=120), nullable=True),
            sa.Column("default_repo_alias", sa.String(length=120), nullable=True),
            sa.Column("default_release", sa.String(length=80), nullable=True),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "platform", "version_key", name="uq_smkv_platform_versionkey"
            ),
        )

    # Seed (idempotent — match on (platform, version_key)).
    for (
        platform,
        version_key,
        label,
        os_family,
        match_regex,
        default_upstream_url,
        default_suite,
        default_repoid,
        default_repo_alias,
        default_release,
    ) in _KNOWN_VERSIONS:
        existing = list(
            bind.execute(
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                text(
                    f"SELECT id FROM {_TABLE} "
                    "WHERE platform = :platform AND version_key = :version_key"
                ),
                {"platform": platform, "version_key": version_key},
            )
        )
        if existing:
            continue
        bind.execute(
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"INSERT INTO {_TABLE} "
                "(id, platform, version_key, label, os_family, match_regex, "
                " default_upstream_url, default_suite, default_repoid, "
                " default_repo_alias, default_release, is_active) "
                "VALUES (:id, :platform, :version_key, :label, :os_family, "
                " :match_regex, :upstream, :suite, :repoid, :alias, :release, :active)"
            ),
            {
                "id": str(uuid.uuid4()),
                "platform": platform,
                "version_key": version_key,
                "label": label,
                "os_family": os_family,
                "match_regex": match_regex,
                "upstream": default_upstream_url,
                "suite": default_suite,
                "repoid": default_repoid,
                "alias": default_repo_alias,
                "release": default_release,
                "active": True,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table(_TABLE):
        op.drop_table(_TABLE)
