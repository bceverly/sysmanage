# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add external_idp_provider MFA columns (Phase 22.8)

``require_mfa``: refuse an SSO token that does not show multi-factor
sign-in.  ``oidc_acr_values``: ``acr`` values also accepted as multi-factor
(and requested).  ``saml_mfa_authn_contexts``: the AuthnContextClassRefs
accepted as multi-factor (Entra ID's multipleauthn when empty).

Additive; ``require_mfa`` defaults to false, so existing providers sign in
exactly as before.  Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q31idpmfa
Revises: q30fedsyncnext
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q31idpmfa"
down_revision: Union[str, None] = "q30fedsyncnext"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "external_idp_provider"
_COLUMNS = (
    ("require_mfa", lambda: sa.Column("require_mfa", sa.Boolean(), nullable=False,
                                      server_default=sa.false())),
    ("oidc_acr_values", lambda: sa.Column("oidc_acr_values", sa.String(500), nullable=True)),
    ("saml_mfa_authn_contexts",
     lambda: sa.Column("saml_mfa_authn_contexts", sa.Text(), nullable=True)),
)  # fmt: skip


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    present = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, column in _COLUMNS:
        if name not in present:
            op.add_column(_TABLE, column())


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    present = {c["name"] for c in inspector.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for name, _column in reversed(_COLUMNS):
            if name in present:
                batch.drop_column(name)
