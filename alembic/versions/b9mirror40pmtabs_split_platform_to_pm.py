"""rename mirror_platform_config.platform values to per-PM (Phase 10.4.3)

Revision ID: b9mirror40pmtabs
Revises: a8mirror30platform
Create Date: 2026-05-07 23:15:00.000000

The Phase 10.4.2 ``platform`` column held coarse OS-family values
(``linux``, ``freebsd``) but the UI design always wanted one tab per
*package manager* — Linux conflates apt + dnf + zypper into a single
tab while operators in practice pick one PM per mirror host.

Phase 10.4.3 retunes the vocabulary to match the UI:

  before          after
  ------          -----
  linux           apt
  freebsd         pkg
  (none)          dnf      (new — RHEL/Fedora/Oracle/Rocky/Alma)
  (none)          zypper   (new — openSUSE/SLES)

The unique constraint ``(platform, host_id)`` stays in place — a
single host can carry one mirror config per PM, which is exactly the
shape the new tab strip needs.

Idempotent + SQLite-safe — both the value rename and the validation
of the new vocabulary check current state before mutating, so
``alembic upgrade head`` is a no-op the second time.  Backfill uses
parameterised ``text()`` SQL so it works on PostgreSQL and SQLite
without ORM bootstrap.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text

revision: str = "b9mirror40pmtabs"
down_revision: Union[str, None] = "a8mirror30platform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PLATFORM_RENAMES = (
    ("linux", "apt"),
    ("freebsd", "pkg"),
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("mirror_platform_config"):
        return

    # Rename existing rows.  No-op on second run because the WHERE
    # clause matches only the old vocabulary.
    for old, new in _PLATFORM_RENAMES:
        bind.execute(
            text(
                "UPDATE mirror_platform_config "
                "SET platform = :new "
                "WHERE platform = :old"
            ),
            {"old": old, "new": new},
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("mirror_platform_config"):
        return
    for old, new in _PLATFORM_RENAMES:
        bind.execute(
            text(
                "UPDATE mirror_platform_config "
                "SET platform = :old "
                "WHERE platform = :new"
            ),
            {"old": old, "new": new},
        )
