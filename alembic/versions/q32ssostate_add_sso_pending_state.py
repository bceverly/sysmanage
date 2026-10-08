# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add sso_pending_state (Phase 22.8)

The OIDC ``state`` / SAML ``RelayState`` of a sign-in in progress, shared by
every server worker.  They were held in one worker's memory, so with several
workers the identity provider's redirect often reached a worker that did not
know them and the sign-in failed after the user had passed MFA.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q32ssostate
Revises: q31idpmfa
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q32ssostate"
down_revision: Union[str, None] = "q31idpmfa"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "sso_pending_state"
_INDEX = "ix_sso_pending_state_created_at"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column("state", sa.String(64), primary_key=True),
            sa.Column(
                "provider_id",
                GUID(),
                sa.ForeignKey("external_idp_provider.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("request_id", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    indexes = {ix["name"] for ix in inspect(op.get_bind()).get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, ["created_at"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE in set(inspector.get_table_names()):
        op.drop_table(_TABLE)
