"""Seed antivirus_default rows for the remaining supported OSes.

Revision ID: 4b3a68c8beee
Revises: k7l8m9n0o1p2
Create Date: 2026-04-25 21:00:00.000000

Earlier migrations seeded Linux, Fedora, and Debian. This migration
fills in every other OS the av_management_engine + open-source AV
planner know how to deploy, so the host detail page's lookup
(`GET /api/antivirus-defaults/{os_name}`) returns 200 with a usable
package name instead of a 404.

Idempotent — uses an existence check before each INSERT, and the
DELETE on downgrade is a no-op if rows are absent. Works on both
PostgreSQL and SQLite (no provider-specific types or syntax).
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "4b3a68c8beee"
down_revision: Union[str, None] = "k7l8m9n0o1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (os_name, antivirus_package). Windows uses ClamWin; everything else uses ClamAV.
# Keep this list in sync with av_plan_builder._linux_clamav_layout() and
# _bsd_clamav_layout(): if a new OS shows up there, add it here too so the
# UI can show "Deploy AV" for that host.
SEED_ROWS = [
    ("Ubuntu", "clamav"),
    ("CentOS", "clamav"),
    ("Rocky", "clamav"),
    ("AlmaLinux", "clamav"),
    ("Oracle", "clamav"),
    ("AmazonLinux", "clamav"),
    ("openSUSE", "clamav"),
    ("SLES", "clamav"),
    ("Arch", "clamav"),
    ("Manjaro", "clamav"),
    ("FreeBSD", "clamav"),
    ("OpenBSD", "clamav"),
    ("NetBSD", "clamav"),
    ("macOS", "clamav"),
    ("Darwin", "clamav"),
    ("Windows", "clamwin"),
]


def upgrade() -> None:
    """Insert each row only if the (os_name) doesn't already exist."""
    conn = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    for os_name, package in SEED_ROWS:
        result = conn.execute(
            text("SELECT COUNT(*) FROM antivirus_default WHERE os_name = :os_name"),
            {"os_name": os_name},
        )
        if result.scalar() != 0:
            continue
        conn.execute(
            text(
                """
                INSERT INTO antivirus_default
                  (id, os_name, antivirus_package, created_at, updated_at)
                VALUES
                  (:id, :os_name, :antivirus_package, :created_at, :updated_at)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "os_name": os_name,
                "antivirus_package": package,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    """Remove every row this migration could have inserted."""
    conn = op.get_bind()
    for os_name, _package in SEED_ROWS:
        conn.execute(
            text("DELETE FROM antivirus_default WHERE os_name = :os_name"),
            {"os_name": os_name},
        )
