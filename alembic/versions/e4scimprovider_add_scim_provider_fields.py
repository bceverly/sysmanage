"""SCIM 2.0 inbound-provisioning fields (Phase 13.1.E)

Adds the columns that turn an ``external_idp_provider`` into a SCIM 2.0 target
the IdP can PUSH user provisioning to:

  * ``scim_enabled`` — gate the per-provider SCIM endpoints on/off.
  * ``scim_bearer_token_secret_id`` — Vault reference to the bearer token the IdP
    presents on every SCIM request (the token value never lives in the DB).

Both default to "off"/NULL, so existing providers are unchanged.  Idempotent and
SQLite + PostgreSQL safe.  Chains off ``e3idpuserlink``.

Revision ID: e4scimprovider
Revises: e3idpuserlink
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "e4scimprovider"
down_revision: Union[str, None] = "e3idpuserlink"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "external_idp_provider"
_COLUMNS = ("scim_enabled", "scim_bearer_token_secret_id")


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        if "scim_enabled" not in existing:
            batch.add_column(
                sa.Column(
                    "scim_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
        if "scim_bearer_token_secret_id" not in existing:
            batch.add_column(
                sa.Column(
                    "scim_bearer_token_secret_id",
                    sa.String(length=255),
                    nullable=True,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for col in _COLUMNS:
            if col in existing:
                batch.drop_column(col)
