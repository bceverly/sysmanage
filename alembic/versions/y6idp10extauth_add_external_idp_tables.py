"""add external IdP tables (Phase 10.5)

Revision ID: y6idp10extauth
Revises: x5mirror10orig
Create Date: 2026-05-07 19:30:00.000000

Three new tables backing the Pro+ ``external_idp_engine`` integration:

  external_idp_provider       — one row per LDAP/AD or OIDC IdP
  idp_role_mapping            — external_group → SecurityRole table
  external_idp_settings       — singleton cross-provider defaults

Idempotent — re-running ``alembic upgrade head`` is a no-op via
``inspect().has_table()``.  Singleton settings row seeded with sensible
defaults (local fallback enabled, 5 max failed attempts).

User table picks up two columns so the login flow can route an account
to its IdP and remember the external subject identifier:
  ``external_idp_provider_id``  — FK to external_idp_provider; NULL for
                                  local-only accounts.
  ``external_subject``          — IdP-side stable identifier (LDAP DN
                                  or OIDC ``sub`` claim).  Used to
                                  re-link if the userid changes.

Both columns are nullable + indexed so existing rows are unaffected.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "y6idp10extauth"
down_revision: Union[str, None] = "x5mirror10orig"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SINGLETON_IDP_SETTINGS_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("external_idp_provider"):
        op.create_table(
            "external_idp_provider",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("type", sa.String(length=20), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("ldap_server_url", sa.String(length=500), nullable=True),
            sa.Column("ldap_bind_dn", sa.String(length=500), nullable=True),
            sa.Column(
                "ldap_bind_password_secret_id",
                sa.String(length=255),
                nullable=True,
            ),
            sa.Column("ldap_user_search_base", sa.String(length=500), nullable=True),
            sa.Column("ldap_user_search_filter", sa.String(length=500), nullable=True),
            sa.Column("ldap_group_search_base", sa.String(length=500), nullable=True),
            sa.Column("ldap_group_search_filter", sa.String(length=500), nullable=True),
            sa.Column("ldap_tls_ca_bundle_path", sa.String(length=500), nullable=True),
            sa.Column(
                "ldap_connection_timeout",
                sa.Integer(),
                nullable=False,
                server_default="10",
            ),
            sa.Column("oidc_issuer_url", sa.String(length=500), nullable=True),
            sa.Column("oidc_client_id", sa.String(length=255), nullable=True),
            sa.Column(
                "oidc_client_secret_secret_id",
                sa.String(length=255),
                nullable=True,
            ),
            sa.Column("oidc_redirect_uri", sa.String(length=500), nullable=True),
            sa.Column(
                "oidc_scopes",
                sa.String(length=500),
                nullable=False,
                server_default="openid profile email",
            ),
            sa.Column("oidc_discovery_url", sa.String(length=500), nullable=True),
            sa.Column(
                "oidc_group_claim",
                sa.String(length=120),
                nullable=False,
                server_default="groups",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("name", name="uq_external_idp_provider_name"),
        )

    if not insp.has_table("idp_role_mapping"):
        op.create_table(
            "idp_role_mapping",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "provider_id",
                GUID(),
                sa.ForeignKey("external_idp_provider.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("external_group", sa.String(length=500), nullable=False),
            sa.Column("role_name", sa.String(length=120), nullable=False),
            sa.Column(
                "default_for_unmapped",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if not insp.has_table("external_idp_settings"):
        op.create_table(
            "external_idp_settings",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "local_account_fallback",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "max_failed_attempts",
                sa.Integer(),
                nullable=False,
                server_default="5",
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column(
                "updated_by",
                GUID(),
                sa.ForeignKey("user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.execute(
            sa.text(
                "INSERT INTO external_idp_settings "
                "(id, local_account_fallback, max_failed_attempts) "
                "VALUES (:id, :fb, :max)"
            ).bindparams(
                id=str(_SINGLETON_IDP_SETTINGS_ID),
                fb=True,
                max=5,
            )
        )

    # Add external_idp linkage columns to user.  Skip if already there.
    # SQLite can't ALTER a table to add a column that carries a constraint,
    # so the FK column has to go through ``batch_alter_table(recreate="auto")``
    # — same pattern as a8mirror30platform_add_platform_config.py.  The
    # plain string column doesn't need batch mode but we pipe both through
    # one ``with`` block so the table is only rewritten once.
    user_cols = {c["name"] for c in insp.get_columns("user")}
    needs_fk = "external_idp_provider_id" not in user_cols
    needs_subject = "external_subject" not in user_cols
    if needs_fk or needs_subject:
        with op.batch_alter_table("user", recreate="auto") as batch:
            if needs_fk:
                # Explicit constraint name is required by SQLite batch mode;
                # PostgreSQL would otherwise auto-generate one.
                batch.add_column(
                    sa.Column(
                        "external_idp_provider_id",
                        GUID(),
                        sa.ForeignKey(
                            "external_idp_provider.id",
                            name="fk_user_external_idp_provider_id",
                            ondelete="SET NULL",
                        ),
                        nullable=True,
                    )
                )
            if needs_subject:
                batch.add_column(
                    sa.Column(
                        "external_subject", sa.String(length=500), nullable=True
                    )
                )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    user_cols = {c["name"] for c in insp.get_columns("user")}
    drop_subject = "external_subject" in user_cols
    drop_fk = "external_idp_provider_id" in user_cols
    if drop_subject or drop_fk:
        with op.batch_alter_table("user", recreate="auto") as batch:
            if drop_subject:
                batch.drop_column("external_subject")
            if drop_fk:
                batch.drop_column("external_idp_provider_id")
    if insp.has_table("external_idp_settings"):
        op.drop_table("external_idp_settings")
    if insp.has_table("idp_role_mapping"):
        op.drop_table("idp_role_mapping")
    if insp.has_table("external_idp_provider"):
        op.drop_table("external_idp_provider")
