# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_federation_schema

Phase 12.6: multi-site federation database schema.

Creates 13 tables — 9 coordinator-side, 4 site-side — that together
form the data model for the federation Phase 12 deliverables.  Both
sets of tables are created on every SysManage instance regardless of
deployment role; the unused half stays empty (under a KB of dead
schema).  Role-specific gating happens at the API layer in Phase
12.1 / 12.2.

Idempotent: re-runnable on a database that already has any subset of
the tables / indexes / unique constraints.  Type choices avoid
PostgreSQL-only types (INET, NUMERIC(p,s)) so the same migration
runs on SQLite — matching the pattern established by the Phase 12.7
geo migration.

Revision ID: m1fedschema
Revises: l0geo10
Create Date: 2026-05-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "m1fedschema"
down_revision: Union[str, None] = "l0geo10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------
# Helper: portable UUID column type.
#
# We can't import ``backend.persistence.models.core.GUID`` here
# because Alembic runs migrations against a bare engine where the
# application package may not be on sys.path.  Instead we replicate
# the ``GUID`` shape inline:  PostgreSQL UUID column, String(36) on
# everything else (SQLite, etc.).  This matches the runtime type
# decorator exactly.
# ---------------------------------------------------------------------


def _guid_type():
    """Return a UUID-typed Column type for the current dialect."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


# ---------------------------------------------------------------------
# Table definitions (data-driven so upgrade/downgrade stay short).
#
# Each entry is (table_name, [Column factories], [Index factories],
# [UniqueConstraint factories]).  The Column factories take no args
# so the GUID type is resolved at upgrade() time against the live
# dialect.
# ---------------------------------------------------------------------


def _coordinator_tables():
    """Coordinator-side table definitions, in FK dependency order.

    ``federation_sites`` is created first because four other tables
    have FKs into it.
    """
    guid = _guid_type()
    return [
        # ------------------------------------------------------------
        # federation_sites
        # ------------------------------------------------------------
        {
            "name": "federation_sites",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("name", sa.String(255), nullable=False, unique=True),
                sa.Column("location_label", sa.String(255), nullable=True),
                sa.Column("url", sa.String(512), nullable=False),
                sa.Column("tls_cert_pem", sa.Text(), nullable=True),
                sa.Column(
                    "enrollment_token_hash", sa.String(128), nullable=True
                ),
                sa.Column(
                    "status",
                    sa.String(32),
                    nullable=False,
                    server_default="enrolled",
                ),
                sa.Column(
                    "host_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("last_sync_at", sa.DateTime(), nullable=True),
                sa.Column("last_sync_status", sa.String(32), nullable=True),
                sa.Column(
                    "sync_interval_seconds",
                    sa.Integer(),
                    nullable=False,
                    server_default="300",
                ),
                sa.Column("agent_version_min", sa.String(32), nullable=True),
                sa.Column("geo_latitude", sa.Float(), nullable=True),
                sa.Column("geo_longitude", sa.Float(), nullable=True),
                sa.Column("geo_country_code", sa.String(2), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
            ],
            "indexes": [
                ("ix_federation_sites_status", ["status"]),
                ("ix_federation_sites_last_sync_at", ["last_sync_at"]),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_host_directory
        # ------------------------------------------------------------
        {
            "name": "federation_host_directory",
            "columns": [
                sa.Column("host_id", guid, primary_key=True),
                sa.Column(
                    "site_id",
                    guid,
                    sa.ForeignKey(
                        "federation_sites.id", ondelete="CASCADE"
                    ),
                    nullable=False,
                ),
                sa.Column("fqdn", sa.String(255), nullable=False),
                sa.Column("ipv4", sa.String(45), nullable=True),
                sa.Column("ipv6", sa.String(45), nullable=True),
                sa.Column("public_ip", sa.String(45), nullable=True),
                sa.Column("os_family", sa.String(64), nullable=True),
                sa.Column("os_version", sa.String(64), nullable=True),
                sa.Column("platform", sa.String(64), nullable=True),
                sa.Column("status", sa.String(32), nullable=True),
                sa.Column("last_seen", sa.DateTime(), nullable=True),
                sa.Column("tags_json", sa.Text(), nullable=True),
                sa.Column("geo_country_code", sa.String(2), nullable=True),
                sa.Column("geo_subdivision_code", sa.String(10), nullable=True),
                sa.Column("geo_city", sa.String(200), nullable=True),
                sa.Column("geo_latitude", sa.Float(), nullable=True),
                sa.Column("geo_longitude", sa.Float(), nullable=True),
                sa.Column("mtime", sa.DateTime(), nullable=False),
            ],
            "indexes": [
                (
                    "ix_federation_host_directory_site_fqdn",
                    ["site_id", "fqdn"],
                ),
                (
                    "ix_federation_host_directory_site_status",
                    ["site_id", "status"],
                ),
                (
                    "ix_federation_host_directory_geo_country",
                    ["geo_country_code", "geo_subdivision_code"],
                ),
                ("ix_federation_host_directory_last_seen", ["last_seen"]),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_host_rollup
        # ------------------------------------------------------------
        {
            "name": "federation_host_rollup",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column(
                    "site_id",
                    guid,
                    sa.ForeignKey(
                        "federation_sites.id", ondelete="CASCADE"
                    ),
                    nullable=False,
                ),
                sa.Column("snapshot_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "host_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "active_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("os_breakdown_json", sa.Text(), nullable=True),
                sa.Column("status_breakdown_json", sa.Text(), nullable=True),
            ],
            "indexes": [
                (
                    "ix_federation_host_rollup_site_snapshot",
                    ["site_id", "snapshot_at"],
                ),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_compliance_rollup
        # ------------------------------------------------------------
        {
            "name": "federation_compliance_rollup",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column(
                    "site_id",
                    guid,
                    sa.ForeignKey(
                        "federation_sites.id", ondelete="CASCADE"
                    ),
                    nullable=False,
                ),
                sa.Column("baseline", sa.String(64), nullable=False),
                sa.Column("snapshot_at", sa.DateTime(), nullable=False),
                sa.Column("score_percent", sa.Float(), nullable=True),
                sa.Column(
                    "hosts_in_scope",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "hosts_compliant",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "hosts_noncompliant",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            ],
            "indexes": [
                (
                    "ix_federation_compliance_rollup_site_baseline_snapshot",
                    ["site_id", "baseline", "snapshot_at"],
                ),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_vulnerability_rollup
        # ------------------------------------------------------------
        {
            "name": "federation_vulnerability_rollup",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column(
                    "site_id",
                    guid,
                    sa.ForeignKey(
                        "federation_sites.id", ondelete="CASCADE"
                    ),
                    nullable=False,
                ),
                sa.Column("snapshot_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "critical_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "high_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "medium_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "low_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "affected_host_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("top_cve_ids_json", sa.Text(), nullable=True),
            ],
            "indexes": [
                (
                    "ix_federation_vulnerability_rollup_site_snapshot",
                    ["site_id", "snapshot_at"],
                ),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_policies
        # ------------------------------------------------------------
        {
            "name": "federation_policies",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("policy_type", sa.String(64), nullable=False),
                sa.Column("name", sa.String(255), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("definition_json", sa.Text(), nullable=False),
                sa.Column(
                    "version",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                ),
                sa.Column("created_by", sa.String(255), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "is_active",
                    sa.Boolean(),
                    nullable=False,
                    # ``sa.true()`` emits ``TRUE`` on PostgreSQL and ``1``
                    # on SQLite — a literal ``"1"`` works on SQLite but
                    # raises ``DatatypeMismatch`` on PG where BOOLEAN is
                    # a real type rather than an aliased integer.
                    server_default=sa.true(),
                ),
            ],
            "indexes": [
                (
                    "ix_federation_policies_type_active",
                    ["policy_type", "is_active"],
                ),
            ],
            "unique_constraints": [
                ("uq_federation_policies_type_name", ["policy_type", "name"]),
            ],
        },
        # ------------------------------------------------------------
        # federation_policy_assignments  (composite PK)
        # ------------------------------------------------------------
        {
            "name": "federation_policy_assignments",
            "columns": [
                sa.Column(
                    "policy_id",
                    guid,
                    sa.ForeignKey(
                        "federation_policies.id", ondelete="CASCADE"
                    ),
                    primary_key=True,
                ),
                sa.Column(
                    "site_id",
                    guid,
                    sa.ForeignKey(
                        "federation_sites.id", ondelete="CASCADE"
                    ),
                    primary_key=True,
                ),
                sa.Column("assigned_at", sa.DateTime(), nullable=False),
                sa.Column("assigned_by", sa.String(255), nullable=True),
                sa.Column(
                    "push_status",
                    sa.String(32),
                    nullable=False,
                    server_default="pending",
                ),
                sa.Column("last_push_attempt_at", sa.DateTime(), nullable=True),
                sa.Column("last_push_error", sa.Text(), nullable=True),
                sa.Column("pushed_version", sa.Integer(), nullable=True),
            ],
            "indexes": [
                (
                    "ix_federation_policy_assignments_status",
                    ["push_status"],
                ),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_dispatched_commands
        # ------------------------------------------------------------
        {
            "name": "federation_dispatched_commands",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("command_type", sa.String(64), nullable=False),
                sa.Column("parameters_json", sa.Text(), nullable=True),
                sa.Column(
                    "target_site_id",
                    guid,
                    sa.ForeignKey(
                        "federation_sites.id", ondelete="CASCADE"
                    ),
                    nullable=False,
                ),
                sa.Column("target_host_ids_json", sa.Text(), nullable=True),
                sa.Column("dispatched_by", sa.String(255), nullable=True),
                sa.Column("dispatched_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "status",
                    sa.String(32),
                    nullable=False,
                    server_default="queued_at_site",
                ),
                sa.Column("result_summary", sa.Text(), nullable=True),
                sa.Column("completed_at", sa.DateTime(), nullable=True),
            ],
            "indexes": [
                (
                    "ix_federation_dispatched_commands_site_status",
                    ["target_site_id", "status"],
                ),
                (
                    "ix_federation_dispatched_commands_dispatched_at",
                    ["dispatched_at"],
                ),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_audit_log
        # ------------------------------------------------------------
        {
            "name": "federation_audit_log",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("operation", sa.String(64), nullable=False),
                sa.Column("actor_userid", sa.String(255), nullable=True),
                sa.Column("target_site_id", guid, nullable=True),
                sa.Column("target_host_id", guid, nullable=True),
                sa.Column("details_json", sa.Text(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
            ],
            "indexes": [
                ("ix_federation_audit_log_created_at", ["created_at"]),
                (
                    "ix_federation_audit_log_operation_created",
                    ["operation", "created_at"],
                ),
                (
                    "ix_federation_audit_log_target_site",
                    ["target_site_id", "created_at"],
                ),
            ],
            "unique_constraints": [],
        },
    ]


def _site_tables():
    """Site-side table definitions, in FK dependency order."""
    guid = _guid_type()
    return [
        # ------------------------------------------------------------
        # federation_coordinator  (singleton)
        # ------------------------------------------------------------
        {
            "name": "federation_coordinator",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("coordinator_url", sa.String(512), nullable=True),
                sa.Column(
                    "coordinator_tls_cert_pem", sa.Text(), nullable=True
                ),
                sa.Column("site_id", guid, nullable=True),
                sa.Column("site_tls_cert_pem", sa.Text(), nullable=True),
                sa.Column(
                    "enrollment_status",
                    sa.String(32),
                    nullable=False,
                    server_default="pending",
                ),
                sa.Column("enrolled_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "sync_interval_seconds",
                    sa.Integer(),
                    nullable=False,
                    server_default="300",
                ),
                sa.Column("last_sync_at", sa.DateTime(), nullable=True),
                sa.Column("last_sync_status", sa.String(32), nullable=True),
                sa.Column("last_sync_error", sa.Text(), nullable=True),
            ],
            "indexes": [],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_sync_queue
        # ------------------------------------------------------------
        {
            "name": "federation_sync_queue",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("payload_type", sa.String(64), nullable=False),
                sa.Column("payload_json", sa.Text(), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "attempts",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
                sa.Column("last_error", sa.Text(), nullable=True),
                sa.Column("dedup_key", sa.String(255), nullable=True),
            ],
            "indexes": [
                ("ix_federation_sync_queue_created_at", ["created_at"]),
                (
                    "ix_federation_sync_queue_payload_type",
                    ["payload_type"],
                ),
                ("ix_federation_sync_queue_dedup_key", ["dedup_key"]),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_received_policies
        # ------------------------------------------------------------
        {
            "name": "federation_received_policies",
            "columns": [
                sa.Column("policy_id", guid, primary_key=True),
                sa.Column("policy_type", sa.String(64), nullable=False),
                sa.Column("name", sa.String(255), nullable=False),
                sa.Column("definition_json", sa.Text(), nullable=False),
                sa.Column(
                    "version",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                ),
                sa.Column("received_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "applied",
                    sa.Boolean(),
                    nullable=False,
                    # Portable: PG ``FALSE`` / SQLite ``0``.
                    server_default=sa.false(),
                ),
                sa.Column("applied_at", sa.DateTime(), nullable=True),
                sa.Column("apply_error", sa.Text(), nullable=True),
            ],
            "indexes": [
                (
                    "ix_federation_received_policies_type_applied",
                    ["policy_type", "applied"],
                ),
            ],
            "unique_constraints": [],
        },
        # ------------------------------------------------------------
        # federation_received_commands
        # ------------------------------------------------------------
        {
            "name": "federation_received_commands",
            "columns": [
                sa.Column("id", guid, primary_key=True),
                sa.Column("command_type", sa.String(64), nullable=False),
                sa.Column("parameters_json", sa.Text(), nullable=True),
                sa.Column(
                    "target_host_ids_json", sa.Text(), nullable=True
                ),
                sa.Column("received_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "status",
                    sa.String(32),
                    nullable=False,
                    server_default="queued",
                ),
                sa.Column("result_json", sa.Text(), nullable=True),
                sa.Column("completed_at", sa.DateTime(), nullable=True),
            ],
            "indexes": [
                (
                    "ix_federation_received_commands_status",
                    ["status", "received_at"],
                ),
            ],
            "unique_constraints": [],
        },
    ]


def _all_tables():
    """All federation tables in creation order (FK dependencies respected)."""
    return _coordinator_tables() + _site_tables()


# ---------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------


def upgrade() -> None:
    """Create all federation tables + their indexes + unique constraints.

    Idempotent: if a table / index / unique constraint already exists
    (from a prior partial run) it is skipped rather than re-created.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table_def in _all_tables():
        table_name = table_def["name"]
        if table_name not in existing_tables:
            uniques = [
                sa.UniqueConstraint(*cols, name=name)
                for name, cols in table_def["unique_constraints"]
            ]
            op.create_table(table_name, *table_def["columns"], *uniques)
            existing_tables.add(table_name)

        # Indexes — checked separately so re-runs after a partial
        # CREATE TABLE pick up missing indexes.
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes(table_name)
        }
        for index_name, index_cols in table_def["indexes"]:
            if index_name not in existing_indexes:
                op.create_index(
                    index_name,
                    table_name,
                    list(index_cols),
                    unique=False,
                )


def downgrade() -> None:
    """Drop the federation tables in reverse FK dependency order.

    Each step is guarded by an existence check so a partial-upgrade
    rollback (or a re-run of an already-applied downgrade) doesn't
    error out.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Reverse order: site tables first (they don't depend on coordinator
    # tables in this schema), then coordinator tables.  Within
    # coordinator tables we drop FK-dependents before the parent.
    for table_def in reversed(_all_tables()):
        table_name = table_def["name"]
        if table_name not in existing_tables:
            continue

        # Drop indexes first — most engines drop them automatically
        # with the table but being explicit makes the downgrade safe
        # to re-run.
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes(table_name)
        }
        for index_name, _ in table_def["indexes"]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name)

        op.drop_table(table_name)
