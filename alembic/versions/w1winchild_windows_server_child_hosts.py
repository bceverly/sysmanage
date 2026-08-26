# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""windows server child hosts — Phase 12.5 frontend slice

Revision ID: w1winchild
Revises: s1agentmirror
Create Date: 2026-08-05 00:00:00.000000

Two things, both needed before the Create Child Host dialog's Windows path
does anything:

1. ``host_child.windows_key_secret_id`` — the OpenBAO-backed Secret row holding
   the licence key.  The key itself is NEVER stored in this table (or any
   other); only the id is, so it cannot be read out of the database.  NULL for
   every non-Windows child and for Windows guests installed from evaluation
   media, which needs no key at all.

2. Windows Server 2022 / 2025 rows in ``child_host_distribution`` so the
   versions appear in the dialog's picker.  ``install_identifier`` is the token
   the engine dispatches on (``virtualization_engine.is_windows_distribution``
   and its edition/os-variant/virtio-release tables all key off it), so these
   strings are load-bearing — they are not display text.

Deliberately absent: an ``iso_url``/``cloud_image_url``.  Microsoft does not
publish a stable unauthenticated URL for Server media, and unlike the Linux
distributions there is no cloud image to fetch.  The operator supplies a local
ISO path per request instead (``windows_iso_path``), which is also what the
air-gapped case needs.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w1winchild"
down_revision: Union[str, None] = "s1agentmirror"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WINDOWS_KVM_DISTRIBUTIONS = [
    {
        "child_type": "kvm",
        "distribution_name": "Windows Server",
        "distribution_version": "2022",
        "display_name": "Windows Server 2022 LTSC",
        "install_identifier": "windows-server-2022",
        "notes": (
            "Installs from operator-supplied retail/eval ISO (windows_iso_path) "
            "with a generated Autounattend.xml.  Needs virtio-win.iso on the "
            "parent for storage/network drivers.  Agent arrives as an MSI on "
            "the per-VM config CD: winget is absent on Server Core."
        ),
    },
    {
        "child_type": "kvm",
        "distribution_name": "Windows Server",
        "distribution_version": "2025",
        "display_name": "Windows Server 2025",
        "install_identifier": "windows-server-2025",
        "notes": (
            "As Server 2022, but virtio drivers are taken from the 2k25 "
            "directories — the 2k22 drivers are not signed for this release "
            "and Setup refuses them."
        ),
    },
]


def _has_column(bind, table: str, column: str) -> bool:
    """True when ``table.column`` already exists (migration is idempotent)."""
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. the licence-key reference column ------------------------------
    if not _has_column(bind, "host_child", "windows_key_secret_id"):
        # GUID() maps to CHAR(36) on SQLite and UUID on PostgreSQL; the models
        # layer handles that, but a raw add_column needs a concrete type, so
        # use the same String(36) width the other id columns in this table use.
        op.add_column(
            "host_child",
            sa.Column("windows_key_secret_id", sa.String(36), nullable=True),
        )

    # --- 2. the Windows Server catalog entries ----------------------------
    for dist in WINDOWS_KVM_DISTRIBUTIONS:
        exists = (
            bind.execute(
                text("""
                    SELECT COUNT(*) FROM child_host_distribution
                    WHERE child_type = :child_type
                      AND distribution_name = :distribution_name
                      AND distribution_version = :distribution_version
                    """),
                {
                    "child_type": dist["child_type"],
                    "distribution_name": dist["distribution_name"],
                    "distribution_version": dist["distribution_version"],
                },
            ).scalar()
            > 0
        )
        # A literal 1 works on SQLite but PostgreSQL's boolean column
        # rejects it, so bind a real Python bool.
        params = dict(dist, is_active=True)
        if exists:
            bind.execute(
                text("""
                    UPDATE child_host_distribution SET
                        display_name = :display_name,
                        install_identifier = :install_identifier,
                        notes = :notes,
                        is_active = :is_active,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE child_type = :child_type
                      AND distribution_name = :distribution_name
                      AND distribution_version = :distribution_version
                    """),
                params,
            )
            continue
        params["id"] = str(uuid.uuid4())
        bind.execute(
            text("""
                INSERT INTO child_host_distribution (
                    id, child_type, distribution_name, distribution_version,
                    display_name, install_identifier, notes, is_active,
                    created_at, updated_at
                ) VALUES (
                    :id, :child_type, :distribution_name, :distribution_version,
                    :display_name, :install_identifier, :notes, :is_active,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """),
            params,
        )


def downgrade() -> None:
    bind = op.get_bind()
    for dist in WINDOWS_KVM_DISTRIBUTIONS:
        bind.execute(
            text("""
                DELETE FROM child_host_distribution
                WHERE child_type = :child_type
                  AND distribution_name = :distribution_name
                  AND distribution_version = :distribution_version
                """),
            {
                "child_type": dist["child_type"],
                "distribution_name": dist["distribution_name"],
                "distribution_version": dist["distribution_version"],
            },
        )
    if _has_column(bind, "host_child", "windows_key_secret_id"):
        op.drop_column("host_child", "windows_key_secret_id")
