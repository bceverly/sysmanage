# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""external IdP user linkage (Phase 13.1.E / 10.5)

Adds the columns that link a local ``user`` row to an external IdP identity, so
LDAP/OIDC/SAML sign-in (and JIT provisioning) can find/attach the account:

  * ``external_idp_provider_id`` — SOFT reference to ``external_idp_provider.id``
    (the account is authenticated by that provider instead of by Argon2).
  * ``external_subject`` — the IdP's stable per-user identifier (OIDC ``sub`` /
    SAML NameID).

Both NULL for a normal password account.  The OIDC callback + the SAML ACS look
a user up by ``(external_idp_provider_id, external_subject)``; without these
columns that lookup cannot run, so this backfills the model the IdP flow has
always assumed.

Idempotent and SQLite + PostgreSQL safe.  Chains off ``e2samlprovider``.

Revision ID: e3idpuserlink
Revises: e2samlprovider
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "e3idpuserlink"
down_revision: Union[str, None] = "e2samlprovider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "user"
_COLUMNS = ("external_idp_provider_id", "external_subject")


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        if "external_idp_provider_id" not in existing:
            batch.add_column(
                sa.Column("external_idp_provider_id", GUID(), nullable=True)
            )
        if "external_subject" not in existing:
            batch.add_column(
                sa.Column("external_subject", sa.String(length=500), nullable=True)
            )
    # Index for the IdP-identity lookup (created outside batch; idempotent).
    indexes = {i["name"] for i in insp.get_indexes(_TABLE)}
    if "ix_user_external_idp_provider_id" not in indexes:
        op.create_index(
            "ix_user_external_idp_provider_id",
            _TABLE,
            ["external_idp_provider_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    indexes = {i["name"] for i in insp.get_indexes(_TABLE)}
    if "ix_user_external_idp_provider_id" in indexes:
        op.drop_index("ix_user_external_idp_provider_id", table_name=_TABLE)
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for col in _COLUMNS:
            if col in existing:
                batch.drop_column(col)
