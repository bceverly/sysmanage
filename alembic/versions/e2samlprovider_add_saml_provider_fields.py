# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""SAML 2.0 provider fields (Phase 13.1.E)

Adds the SAML 2.0 columns to ``external_idp_provider`` so a provider row of
``type='saml'`` carries a full SP/IdP configuration alongside the existing
LDAP/OIDC fields:

  * ``saml_idp_entity_id`` / ``saml_idp_sso_url`` — the IdP's entityID and SSO
    redirect endpoint.
  * ``saml_idp_x509_cert`` — the IdP's PUBLIC signing certificate, used to
    verify assertion signatures (stored inline; it is not a secret).
  * ``saml_sp_entity_id`` / ``saml_sp_acs_url`` — our SP entityID and Assertion
    Consumer Service URL.
  * ``saml_sp_x509_cert`` — optional SP certificate (public).
  * ``saml_sp_private_key_secret_id`` — Vault reference to the SP private key
    (the key itself never lives in the DB).
  * ``saml_email_attribute`` — attribute carrying the email (NameID when empty).
  * ``saml_group_attribute`` — attribute carrying group memberships.
  * ``saml_want_assertions_signed`` — require signed assertions (safe default).

Idempotent and SQLite + PostgreSQL safe (inspector guard + batch_alter_table).
Chains off ``e1idptenancy`` (the main-chain head).

Revision ID: e2samlprovider
Revises: e1idptenancy
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "e2samlprovider"
down_revision: Union[str, None] = "e1idptenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "external_idp_provider"


def _columns():
    """The SAML columns to add, in declaration order."""
    return [
        sa.Column("saml_idp_entity_id", sa.String(length=500), nullable=True),
        sa.Column("saml_idp_sso_url", sa.String(length=500), nullable=True),
        sa.Column("saml_idp_x509_cert", sa.Text(), nullable=True),
        sa.Column("saml_sp_entity_id", sa.String(length=500), nullable=True),
        sa.Column("saml_sp_acs_url", sa.String(length=500), nullable=True),
        sa.Column("saml_sp_x509_cert", sa.Text(), nullable=True),
        sa.Column(
            "saml_sp_private_key_secret_id", sa.String(length=255), nullable=True
        ),
        sa.Column("saml_email_attribute", sa.String(length=255), nullable=True),
        sa.Column(
            "saml_group_attribute",
            sa.String(length=255),
            nullable=False,
            server_default="groups",
        ),
        sa.Column(
            "saml_want_assertions_signed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for col in _columns():
            if col.name not in existing:
                batch.add_column(col)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for col in _columns():
            if col.name in existing:
                batch.drop_column(col.name)
