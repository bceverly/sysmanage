# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""per-tenant external IdP + JIT provisioning (Phase 13.1.E)

Adds three columns to ``external_idp_provider``:

  * ``tenant_id``     — SOFT reference to ``registry_tenant.id`` (no FK; the
    registry is a different partition).  NULL = server-global provider (the
    pre-13.1.E behaviour); a value scopes the provider to one tenant so a SaaS
    tenant brings its own Entra/Okta/OIDC directory.
  * ``jit_provisioning`` — when True, a successful SSO login for a subject with
    no linked account auto-creates the account + a grant into the provider's
    tenant (gated by that tenant's email-domain allowlist).
  * ``jit_default_role`` — the grant role for a JIT-created membership.

Idempotent and SQLite + PostgreSQL safe (inspector guard + batch_alter_table).

Revision ID: e1idptenancy
Revises: d1sharedmkv
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "e1idptenancy"
down_revision: Union[str, None] = "d1sharedmkv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "external_idp_provider"
_COLUMNS = ("tenant_id", "jit_provisioning", "jit_default_role")


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        if "tenant_id" not in existing:
            batch.add_column(sa.Column("tenant_id", GUID(), nullable=True))
        if "jit_provisioning" not in existing:
            batch.add_column(
                sa.Column(
                    "jit_provisioning",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
        if "jit_default_role" not in existing:
            batch.add_column(
                sa.Column(
                    "jit_default_role",
                    sa.String(length=64),
                    nullable=False,
                    server_default="member",
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
