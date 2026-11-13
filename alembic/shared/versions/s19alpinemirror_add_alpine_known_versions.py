# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Alpine releases in the mirror version catalog (2026-11-13).

The Pro+ mirroring engine mirrors Alpine now (``apk``: rsync from an Alpine
rsync mirror, one directory per architecture), and the air-gap collector
already takes Alpine targets; the catalog had no Alpine row for a mirror to
name, so neither could be used.  ``version_key`` is the release (``3.22``),
which is what the collector stages as ``alpine/<version>`` and the air-gapped
repository serves; the default upstream is the release's ``main``.

Idempotent (rows matched on platform + version_key); the downgrade removes
only these rows.

Revision ID: s19alpinemirror
Revises: s18malwarefeed
"""

import uuid
from typing import Sequence, Union

from sqlalchemy import inspect, text

from alembic import op

revision: str = "s19alpinemirror"
down_revision: Union[str, None] = "s18malwarefeed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "shared_mirror_known_version"
_RELEASES = ("3.21", "3.22", "3.23", "3.24")


def _rows():
    for release in _RELEASES:
        yield {
            "platform": "apk",
            "version_key": release,
            "label": f"Alpine Linux {release}",
            "os_family": "alpine",
            "match_regex": r"alpine\s*(linux\s*)?v?" + release.replace(".", r"\."),
            "upstream": f"rsync://rsync.alpinelinux.org/alpine/v{release}/main",
        }


def upgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE):
        return
    for row in _rows():
        found = list(
            bind.execute(
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                text(
                    f"SELECT id FROM {_TABLE} WHERE platform = :platform AND version_key = :version_key"
                ),
                {"platform": row["platform"], "version_key": row["version_key"]},
            )
        )
        if found:
            continue
        bind.execute(
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"INSERT INTO {_TABLE} (id, platform, version_key, label, os_family, match_regex, "
                "default_upstream_url, is_active) VALUES (:id, :platform, :version_key, :label, "
                ":os_family, :match_regex, :upstream, :active)"
            ),
            {**row, "id": str(uuid.uuid4()), "active": True},
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE):
        return
    for release in _RELEASES:
        bind.execute(
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"DELETE FROM {_TABLE} WHERE platform = 'apk' AND version_key = :version_key"
            ),
            {"version_key": release},
        )
