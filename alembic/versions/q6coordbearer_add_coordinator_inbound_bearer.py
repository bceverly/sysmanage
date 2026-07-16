# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_coordinator_inbound_bearer

Phase 12.10 Slice 3: federation wire protocol — symmetric bearer
for the coordinator → site direction.

Slice 1 minted a one-way bearer the SITE uses to push data into
the coordinator's ingest endpoints.  This slice adds the REVERSE-
direction credential the COORDINATOR uses when it pushes policy
versions and dispatched-command envelopes back to the site.

Adds two columns, one per side of the relationship:

  ``federation_sites.coordinator_outbound_bearer_token``
      Plaintext.  The coordinator presents this on every HTTP push
      to a subordinate site.  Stored on the coordinator because
      THIS is the side that originates the call.

  ``federation_coordinator.coordinator_inbound_bearer_token_hash``
      SHA-256.  The site uses this to verify that incoming
      ``/site/policies`` and ``/site/commands`` calls really came
      from the coordinator (and not, say, a leaked URL hitting a
      random Internet attacker).

Plaintext lives on exactly one side per direction, just like the
``sync_bearer_token`` / ``sync_bearer_token_hash`` split from
Slice 1 — a DB leak on the verifier side never exposes a
usable secret.

Idempotent + cross-dialect: guards on the column-exists check
before adding.

Revision ID: q6coordbearer
Revises: p5sitebearer
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "q6coordbearer"
down_revision: Union[str, None] = "p5sitebearer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES_AND_COLUMNS = (
    ("federation_sites", "coordinator_outbound_bearer_token", sa.Text()),
    ("federation_coordinator", "coordinator_inbound_bearer_token_hash", sa.String(128)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table, column_name, column_type in _TABLES_AND_COLUMNS:
        if table not in table_names:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column_name not in existing:
            op.add_column(table, sa.Column(column_name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table, column_name, _ in reversed(_TABLES_AND_COLUMNS):
        if table not in table_names:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column_name in existing:
            op.drop_column(table, column_name)
