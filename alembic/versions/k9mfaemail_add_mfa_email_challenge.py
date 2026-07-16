# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add MFA email-OTP challenge table (Phase 10.3 follow-up)

Revision ID: k9mfaemail
Revises: j8install08ppacopr
Create Date: 2026-05-13 14:30:00.000000

Phase 10.3 closeout — adds the email-OTP fallback path alongside the
existing TOTP + backup-code authentication factors.  Stores short-lived,
one-time codes that the verification endpoint can accept in place of a
TOTP code when a user can't reach their authenticator app.

The codes themselves are never stored in plaintext — only an Argon2 hash
is persisted, mirroring the backup-code pattern in
``UserMfaEnrollment.backup_codes_hashed``.  Each row has an explicit
``expires_at`` so the verify path can reject stale codes without a
separate sweep job.

Idempotent: re-running ``alembic upgrade head`` after a previous
successful run is a no-op (``inspect().has_table()`` check).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "k9mfaemail"
down_revision: Union[str, None] = "j8install08ppacopr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("mfa_email_challenge"):
        op.create_table(
            "mfa_email_challenge",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "user_id",
                GUID(),
                sa.ForeignKey("user.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            # Argon2 hash of the 6-digit OTP — never stored in plaintext.
            sa.Column("code_hash", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            # Hard expiration enforced at verify time.  Default lifetime
            # is 10 minutes (set by the service when creating the row);
            # making expires_at a stored column rather than computed
            # keeps the verify path's check a simple ``<`` against
            # ``datetime.utcnow()``.
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            # Set when the code is successfully consumed.  NULL means
            # the code is still live; the verify path's "still good"
            # filter is ``consumed_at IS NULL AND expires_at > now()``.
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            # Audit-only; recorded so an admin investigating a
            # suspicious challenge can correlate origin.  Stored as a
            # plain string because the OSS server accepts both v4 and
            # v6 inbound — no validation here.
            sa.Column("ip_address", sa.String(length=45), nullable=True),
        )
        # Composite index supports the common "any live challenge for
        # this user?" lookup the verify path issues without a full scan.
        op.create_index(
            "ix_mfa_email_challenge_user_live",
            "mfa_email_challenge",
            ["user_id", "consumed_at", "expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("mfa_email_challenge"):
        op.drop_index(
            "ix_mfa_email_challenge_user_live",
            table_name="mfa_email_challenge",
        )
        op.drop_table("mfa_email_challenge")
