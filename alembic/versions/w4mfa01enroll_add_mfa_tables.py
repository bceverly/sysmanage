"""add MFA enrollment + settings tables (Phase 10.3)

Revision ID: w4mfa01enroll
Revises: v3uchildist0
Create Date: 2026-05-07 18:30:00.000000

Two new tables backing the OSS multi-factor authentication feature:

  user_mfa_enrollment
      One row per user that has enrolled.  Holds the Fernet-encrypted
      TOTP shared secret, an Argon2-hashed list of unused backup codes,
      and audit timestamps.  Unique on ``user_id`` so a user can only
      have one active enrollment.

  mfa_settings
      Singleton row of admin defaults.  Pre-seeded with sensible values
      (issuer="SysManage", 6 digits, 30s period, 10 backup codes,
      admin_required=False, 14-day grace period) so the feature works
      out of the box without admin intervention.

The migration is idempotent — re-running ``alembic upgrade head`` after
a previous successful run is a no-op (table-create checks via
``inspect().has_table()``).
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "w4mfa01enroll"
down_revision: Union[str, None] = "v3uchildist0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Match the singleton id used by the model so the seed insert lines
# up with ``MfaSettings.SINGLETON_MFA_SETTINGS_ID``.
_SINGLETON_MFA_SETTINGS_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("user_mfa_enrollment"):
        op.create_table(
            "user_mfa_enrollment",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "user_id",
                GUID(),
                sa.ForeignKey("user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("totp_secret_encrypted", sa.Text(), nullable=False),
            sa.Column("backup_codes_hashed", sa.JSON(), nullable=False),
            sa.Column("enrolled_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("last_used_method", sa.String(length=20), nullable=True),
            sa.UniqueConstraint("user_id", name="uq_user_mfa_enrollment_user_id"),
        )

    if not insp.has_table("mfa_settings"):
        op.create_table(
            "mfa_settings",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "issuer_name",
                sa.String(length=120),
                nullable=False,
                server_default="SysManage",
            ),
            sa.Column("totp_digits", sa.Integer(), nullable=False, server_default="6"),
            sa.Column(
                "totp_period_seconds",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
            sa.Column(
                "backup_code_count",
                sa.Integer(),
                nullable=False,
                server_default="10",
            ),
            sa.Column(
                "admin_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "grace_period_days",
                sa.Integer(),
                nullable=False,
                server_default="14",
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column(
                "updated_by",
                GUID(),
                sa.ForeignKey("user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        # Seed the singleton row so GET /api/settings/mfa returns
        # defaults from the start; the admin can update via PUT.
        op.execute(
            sa.text(
                "INSERT INTO mfa_settings "
                "(id, issuer_name, totp_digits, totp_period_seconds, "
                "backup_code_count, admin_required, grace_period_days) "
                "VALUES (:id, :issuer, :digits, :period, :count, :req, :grace)"
            ).bindparams(
                # psycopg3 sends parameters with explicit types, so a stringified
                # UUID is rejected by a uuid column ("type uuid but expression is
                # of type character varying"); psycopg2 coerced it silently. Bind
                # with the GUID type so it goes over as a real uuid on every driver.
                sa.bindparam("id", _SINGLETON_MFA_SETTINGS_ID, type_=GUID()),
                issuer="SysManage",
                digits=6,
                period=30,
                count=10,
                req=False,
                grace=14,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("mfa_settings"):
        op.drop_table("mfa_settings")
    if insp.has_table("user_mfa_enrollment"):
        op.drop_table("user_mfa_enrollment")
