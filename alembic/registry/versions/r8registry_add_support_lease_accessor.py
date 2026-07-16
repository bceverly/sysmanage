# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_support_lease_accessor

Phase 13.1.E (vendor-support / break-glass grants — OpenBAO lease binding).

A support grant's ``expires_at`` already auto-revokes app access (the
request-time ``has_active_grant`` gate refuses it the instant it lapses).  This
column binds the grant to a **live OpenBAO lease object**: when the grant is
minted, the server creates a short-lived OpenBAO token whose TTL mirrors the
grant window and records its *accessor* here.  That gives a vault-visible lease
that auto-expires with the grant and can be revoked immediately (kill-the-
break-glass) — ``revoke_support_grant`` expires the grant AND revokes this lease.

Nullable: leases are best-effort and only minted when OpenBAO is enabled, so a
single-tenant / vault-less deployment simply leaves it NULL and relies on
``expires_at`` alone (unchanged behaviour).

Eighth migration in the **registry** chain (chains off ``r7registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod).

Revision ID: r8registry
Revises: r7registry
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r8registry"
down_revision: Union[str, None] = "r7registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_user_tenant_grant"
_COLUMN = "support_lease_accessor"


def upgrade() -> None:
    """Add ``registry_user_tenant_grant.support_lease_accessor`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return  # registry schema not present (e.g. shared/tenant-only run)
    columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.String(255), nullable=True),
        )


def downgrade() -> None:
    """Drop ``registry_user_tenant_grant.support_lease_accessor`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
