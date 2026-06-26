"""Update mirror_known_version for Ubuntu 26.04 (resolute) + add 25.10 (questing).

Revision ID: u1mirror60ubresolute
Revises: t0absize
Create Date: 2026-05-26 17:50:00.000000

The earlier ``c1mirror50version_dropdown`` migration seeded an
"Ubuntu 26.04 (next)" placeholder row when the codename for 26.04
hadn't been announced yet, and pointed its ``default_suite`` at
``noble`` as a stand-in.  26.04 is now ``resolute`` and the row is
wrong on two counts: the label and the suite.  This migration:

  * Updates the existing ubuntu-26.04 row to use the real codename
    (``resolute``) in label, suite, and match_regex.
  * Adds Ubuntu 25.10 (``questing``), which was skipped entirely by
    the original seed (it only covered 22.04, 24.04, and the 26.04
    placeholder).

Reversible — downgrade restores "(next)" + ``noble`` and removes the
25.10 row.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u1mirror60ubresolute"
down_revision: Union[str, None] = "t0absize"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Update the existing 26.04 row: real codename in label + suite +
    # match_regex.  Matches by version_key so we don't depend on the
    # label text (the thing we're changing).
    conn.execute(
        sa.text(
            "UPDATE mirror_known_version "
            "   SET label = :label, "
            "       default_suite = :suite, "
            "       match_regex = :regex "
            " WHERE platform = 'apt' "
            "   AND version_key = 'ubuntu-26.04'"
        ),
        {
            "label": "Ubuntu 26.04 (resolute)",
            "suite": "resolute",
            "regex": r"ubuntu\s*26\.04|resolute",
        },
    )

    # Add Ubuntu 25.10 (questing) — missed by the original seed.
    # Guard with a SELECT so re-applying the migration (or applying
    # against a DB someone hand-patched) is a no-op rather than a
    # duplicate-key blow-up.
    existing = conn.execute(
        sa.text(
            "SELECT 1 FROM mirror_known_version "
            " WHERE platform = 'apt' AND version_key = 'ubuntu-25.10'"
        )
    ).fetchone()
    if not existing:
        # Generate the id in Python rather than calling ``gen_random_uuid()``
        # in SQL (that function is Postgres-only and breaks SQLite with
        # "no such function: gen_random_uuid").  Do NOT cast in the SQL:
        # ``:id::uuid`` looks like a cast to SQLAlchemy, which then refuses
        # to treat ``:id`` as a bind parameter (it reserves ``::`` for
        # Postgres casts) and emits it literally — a syntax error.  Instead
        # bind a value the driver maps to the column type directly:
        # psycopg2 adapts a ``uuid.UUID`` object to the uuid column natively,
        # and SQLite stores the string form in its CHAR(36) GUID column.
        is_sqlite = conn.dialect.name == "sqlite"
        new_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO mirror_known_version "
                "    (id, platform, version_key, label, os_family, "
                "     match_regex, default_upstream_url, default_suite, "
                "     default_repoid, default_repo_alias, default_release, "
                "     is_active) "
                "VALUES (:id, :platform, :version_key, :label, "
                "        :os_family, :regex, :url, :suite, :repoid, :alias, "
                "        :release, :active)"
            ),
            {
                "id": str(new_id) if is_sqlite else new_id,
                "platform": "apt",
                "version_key": "ubuntu-25.10",
                "label": "Ubuntu 25.10 (questing)",
                "os_family": "ubuntu",
                "regex": r"ubuntu\s*25\.10|questing",
                "url": "http://archive.ubuntu.com/ubuntu",
                "suite": "questing",
                "repoid": None,
                "alias": None,
                "release": None,
                "active": True,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Restore the placeholder label + noble suite for 26.04.
    conn.execute(
        sa.text(
            "UPDATE mirror_known_version "
            "   SET label = :label, "
            "       default_suite = :suite, "
            "       match_regex = :regex "
            " WHERE platform = 'apt' "
            "   AND version_key = 'ubuntu-26.04'"
        ),
        {
            "label": "Ubuntu 26.04 (next)",
            "suite": "noble",
            "regex": r"ubuntu\s*26\.04",
        },
    )

    # Remove the 25.10 row.
    conn.execute(
        sa.text(
            "DELETE FROM mirror_known_version "
            " WHERE platform = 'apt' AND version_key = 'ubuntu-25.10'"
        )
    )
