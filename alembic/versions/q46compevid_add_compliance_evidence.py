# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""host_compliance_evidence + a wider compliance grade (ROADMAP 24.4, 2026-10-18)

Tenant data.  ``host_compliance_evidence``: one row per host, the inputs its
compliance checks read (effective sshd settings, sysctls, file modes, PAM,
auditd, AIDE...) as the agent last reported them -- before this, the scan
judged every host against empty data.

``host_compliance_scan.compliance_grade`` grows from VARCHAR(2) to
VARCHAR(8): a scan with nothing applicable is graded ``N/A`` (three
characters), which PostgreSQL refused in a VARCHAR(2).  SQLite does not
enforce the length, so the column is only altered on PostgreSQL.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q46compevid
Revises: q45discnames
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q46compevid"
down_revision: Union[str, None] = "q45discnames"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host_compliance_evidence"
_INDEX = "ix_host_compliance_evidence_host_id"
_SCAN = "host_compliance_scan"
_GRADE = "compliance_grade"


def _grade_length(insp):
    for column in insp.get_columns(_SCAN):
        if column["name"] == _GRADE:
            return getattr(column["type"], "length", None)
    return None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "host" in tables and _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("platform", sa.String(32), nullable=True),
            sa.Column("sections", sa.Text(), nullable=False),
            sa.Column("sources", sa.Text(), nullable=True),
            sa.Column("collected_at", sa.DateTime(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False),
        )
    if _TABLE in set(inspect(bind).get_table_names()) and _INDEX not in {
        ix["name"] for ix in inspect(bind).get_indexes(_TABLE)
    }:
        op.create_index(_INDEX, _TABLE, ["host_id"], unique=True)
    length = _grade_length(insp) if _SCAN in tables else None
    if bind.dialect.name == "postgresql" and length is not None and length < 8:
        op.alter_column(
            _SCAN,
            _GRADE,
            existing_type=sa.String(length),
            type_=sa.String(8),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE in insp.get_table_names():
        if _INDEX in {ix["name"] for ix in insp.get_indexes(_TABLE)}:
            op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)
    # The grade column stays VARCHAR(8): narrowing it would fail on any "N/A"
    # row, and a wider column is harmless to the previous revision.
