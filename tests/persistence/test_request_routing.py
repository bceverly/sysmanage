"""
Tests for the data-plane request routing seam (Phase 13.1).

``get_request_engine`` is the single chokepoint that routes a request's
queries to the active tenant's database (or the main engine in single-tenant /
server scope).
"""

from unittest.mock import MagicMock, patch

from backend.persistence import partitions, tenant_context


def test_main_engine_when_multitenancy_disabled():
    main = MagicMock(name="main-engine")
    with patch.object(
        partitions.config, "is_multitenancy_enabled", return_value=False
    ), patch.object(partitions.db, "get_engine", return_value=main):
        # Even an explicit tenant_id is ignored when MT is off.
        assert partitions.get_request_engine("t-1") is main


def test_main_engine_when_no_active_tenant():
    main = MagicMock(name="main-engine")
    with patch.object(
        partitions.config, "is_multitenancy_enabled", return_value=True
    ), patch.object(partitions.db, "get_engine", return_value=main), patch.object(
        partitions, "resolve_engine"
    ) as resolve:
        assert partitions.get_request_engine() is main
        resolve.assert_not_called()


def test_tenant_engine_with_explicit_id():
    tenant_engine = MagicMock(name="tenant-engine")
    with patch.object(
        partitions.config, "is_multitenancy_enabled", return_value=True
    ), patch.object(
        partitions, "resolve_engine", return_value=tenant_engine
    ) as resolve:
        assert partitions.get_request_engine("t-9") is tenant_engine
    resolve.assert_called_once_with(
        partition=partitions.PARTITION_TENANT, tenant_id="t-9"
    )


def test_tenant_engine_from_contextvar():
    tenant_engine = MagicMock(name="tenant-engine")
    token = tenant_context.set_active_tenant("t-ctx")
    try:
        with patch.object(
            partitions.config, "is_multitenancy_enabled", return_value=True
        ), patch.object(
            partitions, "resolve_engine", return_value=tenant_engine
        ) as resolve:
            assert partitions.get_request_engine() is tenant_engine
        resolve.assert_called_once_with(
            partition=partitions.PARTITION_TENANT, tenant_id="t-ctx"
        )
    finally:
        tenant_context.reset_active_tenant(token)


def test_request_sessionmaker_binds_request_engine():
    main = MagicMock(name="main-engine")
    with patch.object(
        partitions.config, "is_multitenancy_enabled", return_value=False
    ), patch.object(partitions.db, "get_engine", return_value=main):
        maker = partitions.request_sessionmaker()
    assert maker.kw["bind"] is main
