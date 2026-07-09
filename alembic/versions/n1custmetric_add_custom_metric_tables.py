"""create custom_metric tables and seed 'Manage Custom Metrics' role

Custom Metrics & Graphs (Slice 1 — OSS schema foundation).

Landscape "Custom Graphs" parity: an operator defines a named custom metric =
a small script emitting ONE numeric value, targeted by HOST TAG.  The agent
runs it on a cadence and returns the number; samples are stored as a
time-series for graphing + alerting.

This is a Pro+ capability whose LOGIC lives in the ``observability_engine``.
Only the SCHEMA + role belong in OSS (moat model).

* ``custom_metric`` — the metric definition (script body, interpreter, unit,
  cadence, enabled).
* ``custom_metric_tag`` — targeting association (metric → host tag).  ``tags``
  lives in the tenant partition (same as ``host``), so a REAL FK to ``tags.id``
  is used.
* ``custom_metric_sample`` — time-series samples (value nullable when errored),
  indexed on ``(custom_metric_id, host_id, collected_at)`` for time-series
  reads.
* Seeds the ``Manage Custom Metrics`` security role in the Host group.

Tenant-partition tables: names are UNPREFIXED (no registry_/shared_ prefix).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: n1custmetric
Revises: m1gpgkeys
"""

import uuid
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "n1custmetric"
down_revision: Union[str, None] = "m1gpgkeys"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_CUSTOM_METRIC = "custom_metric"
_CUSTOM_METRIC_TAG = "custom_metric_tag"
_CUSTOM_METRIC_SAMPLE = "custom_metric_sample"

_ROLE_NAME = "Manage Custom Metrics"
_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table(_CUSTOM_METRIC):
        op.create_table(
            _CUSTOM_METRIC,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("script", sa.Text(), nullable=False),
            sa.Column(
                "interpreter",
                sa.String(length=50),
                nullable=False,
                server_default="sh",
            ),
            sa.Column("unit", sa.String(length=50), nullable=True),
            sa.Column(
                "cadence_seconds",
                sa.Integer(),
                nullable=False,
                server_default="300",
            ),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("created_by", GUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("name", name="uq_custom_metric_name"),
        )
        op.create_index("ix_custom_metric_name", _CUSTOM_METRIC, ["name"])

    if not insp.has_table(_CUSTOM_METRIC_TAG):
        op.create_table(
            _CUSTOM_METRIC_TAG,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("custom_metric_id", GUID(), nullable=False),
            sa.Column("tag_id", GUID(), nullable=False),
            sa.ForeignKeyConstraint(
                ["custom_metric_id"], ["custom_metric.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        )
        op.create_index(
            "ix_custom_metric_tag_custom_metric_id",
            _CUSTOM_METRIC_TAG,
            ["custom_metric_id"],
        )
        op.create_index(
            "ix_custom_metric_tag_tag_id", _CUSTOM_METRIC_TAG, ["tag_id"]
        )

    if not insp.has_table(_CUSTOM_METRIC_SAMPLE):
        op.create_table(
            _CUSTOM_METRIC_SAMPLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("custom_metric_id", GUID(), nullable=False),
            sa.Column("host_id", GUID(), nullable=False),
            sa.Column("value", sa.Float(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="ok",
            ),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["custom_metric_id"], ["custom_metric.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["host_id"], ["host.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_custom_metric_sample_custom_metric_id",
            _CUSTOM_METRIC_SAMPLE,
            ["custom_metric_id"],
        )
        op.create_index(
            "ix_custom_metric_sample_host_id",
            _CUSTOM_METRIC_SAMPLE,
            ["host_id"],
        )
        op.create_index(
            "ix_custom_metric_sample_metric_host_collected",
            _CUSTOM_METRIC_SAMPLE,
            ["custom_metric_id", "host_id", "collected_at"],
        )

    _seed_role(bind)


def _seed_role(bind) -> None:
    """Idempotently seed the 'Manage Custom Metrics' role (Host group)."""
    insp = inspect(bind)
    if "security_roles" not in insp.get_table_names():
        return

    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM security_roles WHERE name = :name"),
        {"name": _ROLE_NAME},
    ).scalar()
    if existing:
        return

    # ``id``/``group_id`` are uuid columns on PostgreSQL, plain TEXT on SQLite.
    is_sqlite = bind.dialect.name == "sqlite"
    id_ph = ":id" if is_sqlite else "CAST(:id AS uuid)"
    gid_ph = ":group_id" if is_sqlite else "CAST(:group_id AS uuid)"
    op.execute(
        sa.text(
            "INSERT INTO security_roles (id, name, description, group_id) "
            f"VALUES ({id_ph}, :name, :description, {gid_ph})"
        ).bindparams(
            id=str(uuid.uuid4()),
            name=_ROLE_NAME,
            description="Manage custom metrics, their tag targeting and samples",
            group_id=_HOST_GROUP_ID,
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "security_roles" in insp.get_table_names():
        op.execute(
            sa.text("DELETE FROM security_roles WHERE name = :name").bindparams(
                name=_ROLE_NAME
            )
        )

    # Drop children (they FK the metric table) before the parent.
    if insp.has_table(_CUSTOM_METRIC_SAMPLE):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_CUSTOM_METRIC_SAMPLE)
    if insp.has_table(_CUSTOM_METRIC_TAG):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_CUSTOM_METRIC_TAG)
    if insp.has_table(_CUSTOM_METRIC):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_CUSTOM_METRIC)
