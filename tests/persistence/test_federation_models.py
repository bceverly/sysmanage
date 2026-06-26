"""
Smoke tests for the Phase 12.6 federation schema.

Covers:
  * All 13 federation model classes import + register on ``Base.metadata``.
  * ``Base.metadata.create_all`` builds every table on a fresh SQLite
    engine without error (catches schema-definition typos).
  * The Alembic ``upgrade()`` is idempotent: a second invocation on
    the same engine succeeds without raising and produces the same
    set of tables.
  * ``downgrade()`` is also idempotent.
  * The singleton row id constant is the expected UUID shape — it's
    a load-bearing contract for site-side code that upserts by PK.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from backend.persistence.db import Base
from backend.persistence.models.federation import (
    SINGLETON_FEDERATION_COORDINATOR_ID,
    FederationAuditLog,
    FederationComplianceRollup,
    FederationCoordinator,
    FederationDispatchedCommand,
    FederationHostDirectory,
    FederationHostRollup,
    FederationPolicy,
    FederationPolicyAssignment,
    FederationReceivedCommand,
    FederationReceivedPolicy,
    FederationSite,
    FederationSyncQueue,
    FederationVulnerabilityRollup,
)

# All 13 tables this migration creates.  Coordinator-side first
# (matching the FK dependency order in the migration), then site-side.
EXPECTED_TABLES = [
    "federation_sites",
    "federation_host_directory",
    "federation_host_rollup",
    "federation_compliance_rollup",
    "federation_vulnerability_rollup",
    "federation_policies",
    "federation_policy_assignments",
    "federation_dispatched_commands",
    "federation_audit_log",
    "federation_coordinator",
    "federation_sync_queue",
    "federation_received_policies",
    "federation_received_commands",
]


# All 13 ORM classes (kept in lockstep with EXPECTED_TABLES via tablename).
ORM_CLASSES = [
    FederationSite,
    FederationHostDirectory,
    FederationHostRollup,
    FederationComplianceRollup,
    FederationVulnerabilityRollup,
    FederationPolicy,
    FederationPolicyAssignment,
    FederationDispatchedCommand,
    FederationAuditLog,
    FederationCoordinator,
    FederationSyncQueue,
    FederationReceivedPolicy,
    FederationReceivedCommand,
]


# ---------------------------------------------------------------------
# Model definition / metadata sanity
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "orm_class, expected_table", list(zip(ORM_CLASSES, EXPECTED_TABLES))
)
def test_orm_class_tablename(orm_class, expected_table):
    assert orm_class.__tablename__ == expected_table


def test_singleton_uuid_is_well_formed():
    """The singleton id must be a UUID — site code upserts by this PK
    without a SELECT, so a typo here would create extra rows instead
    of replacing the one we expect."""
    assert isinstance(SINGLETON_FEDERATION_COORDINATOR_ID, uuid.UUID)
    assert str(SINGLETON_FEDERATION_COORDINATOR_ID) == (
        "00000000-0000-0000-0000-00000000fed0"
    )


def test_all_tables_registered_on_base_metadata():
    """``Base.metadata`` must know about every federation table after
    the package imports — otherwise ``create_all`` will silently
    skip them."""
    registered = set(Base.metadata.tables.keys())
    missing = [name for name in EXPECTED_TABLES if name not in registered]
    assert not missing, f"Missing from Base.metadata: {missing}"


# ---------------------------------------------------------------------
# Alembic upgrade / downgrade idempotency
# ---------------------------------------------------------------------


def _run_alembic_func(engine, func_name):
    """Run the migration's ``upgrade()`` / ``downgrade()`` against an
    explicit engine.  Done by hand (rather than via Alembic CLI) so the
    test is hermetic — no alembic.ini parsing, no migration history
    table, no env.py wiring."""
    # Import locally because Alembic versions are file paths, not
    # module names — we import via importlib.
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "m1fedschema_add_federation_schema.py"
    )
    spec = importlib.util.spec_from_file_location(
        "m1fedschema_test_load", str(migration_path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        # ``Operations.context`` installs/removes the global ``op``
        # proxy that the migration's ``op.<x>`` calls resolve through.
        with Operations.context(ctx):
            getattr(module, func_name)()


def test_upgrade_creates_all_tables_idempotently():
    """First upgrade creates all 13 tables; second upgrade is a no-op
    (no exception raised, same table set)."""
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        _run_alembic_func(engine, "upgrade")
        inspector = sa.inspect(engine)
        tables_after_first = set(inspector.get_table_names())
        for name in EXPECTED_TABLES:
            assert name in tables_after_first, f"Missing after upgrade: {name}"

        # Second upgrade must not raise and must produce the same set.
        _run_alembic_func(engine, "upgrade")
        inspector = sa.inspect(engine)
        tables_after_second = set(inspector.get_table_names())
        assert tables_after_second == tables_after_first
    finally:
        engine.dispose()


def test_downgrade_drops_all_tables_idempotently():
    """After upgrade then downgrade, every federation table is gone.
    A second downgrade is a no-op."""
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        _run_alembic_func(engine, "upgrade")
        _run_alembic_func(engine, "downgrade")
        inspector = sa.inspect(engine)
        remaining = set(inspector.get_table_names())
        for name in EXPECTED_TABLES:
            assert name not in remaining, f"Still present after downgrade: {name}"

        # Second downgrade must not raise.
        _run_alembic_func(engine, "downgrade")
    finally:
        engine.dispose()


# ---------------------------------------------------------------------
# Insert smoke test — verify the schema actually accepts a row
# ---------------------------------------------------------------------


def test_round_trip_through_orm():
    """End-to-end ORM round trip on the federation_sites table.

    Catches column-definition typos (default factories, server_default
    interactions, etc.) that ``create_all`` alone wouldn't surface."""
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in EXPECTED_TABLES]
        )

        Session = sessionmaker(bind=engine)
        with Session() as session:
            site = FederationSite(
                name="Site-Cleveland",
                location_label="Cleveland DC1",
                url="https://sysmanage.cle.example.com",
            )
            session.add(site)
            session.commit()
            assert site.id is not None
            assert site.status == "enrolled"  # column default
            assert site.host_count == 0
            assert site.sync_interval_seconds == 300
            assert site.created_at is not None
            assert site.updated_at is not None
    finally:
        engine.dispose()
