"""
Integration tests for the tenant data-mover (Phase 13.1).

Uses two in-memory databases: the bootstrap/source (the test engine) and a
separate per-tenant target engine (patched in for ``get_request_engine``).
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import host_tenant_index, tenant_data_mover


@pytest.fixture
def target_engine():
    """A second in-memory DB standing in for a provisioned tenant database."""
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


def _tenant(db_session, slug="mover-co"):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    t = RegistryTenant(name="Mover Co", slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(t)
    db_session.commit()
    return t


def _host(db_session, fqdn="h1.example.com"):
    h = models.Host(fqdn=fqdn, active=True, approval_status="approved")
    db_session.add(h)
    db_session.commit()
    return h


def test_move_copies_bound_host_to_tenant_and_deletes_source(db_session, target_engine):
    tenant = _tenant(db_session)
    host = _host(db_session)
    host_tenant_index.bind_host_to_tenant(host.id, tenant.id)
    host_id = host.id

    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch(
        "backend.persistence.partitions.get_request_engine", return_value=target_engine
    ):
        report = tenant_data_mover.move_all(apply=True, delete_source=True)

    assert report["host"]["moved"] == 1
    # Present in the tenant DB...
    tgt = sessionmaker(bind=target_engine)()
    assert tgt.get(models.Host, host_id) is not None
    tgt.close()
    # ...and gone from the bootstrap DB.
    db_session.expire_all()
    assert (
        db_session.query(models.Host).filter(models.Host.id == host_id).first() is None
    )


def test_unassigned_host_is_left_in_place(db_session, target_engine):
    _tenant(db_session)
    host = _host(db_session)  # NOT bound to a tenant
    host_id = host.id

    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch(
        "backend.persistence.partitions.get_request_engine", return_value=target_engine
    ):
        report = tenant_data_mover.move_all(apply=True, delete_source=True)

    assert report["host"]["skipped_unassigned"] == 1
    assert report["host"]["moved"] == 0
    db_session.expire_all()
    # Still in the bootstrap DB (couldn't be placed).
    assert (
        db_session.query(models.Host).filter(models.Host.id == host_id).first()
        is not None
    )


def test_idempotent_rerun_skips_present(db_session, target_engine):
    tenant = _tenant(db_session)
    host = _host(db_session)
    host_tenant_index.bind_host_to_tenant(host.id, tenant.id)

    with patch(
        "backend.config.config.is_multitenancy_enabled", return_value=True
    ), patch(
        "backend.persistence.partitions.get_request_engine", return_value=target_engine
    ):
        # First: copy only (leave source).
        first = tenant_data_mover.move_all(apply=True, delete_source=False)
        # Second run: already present in target → skipped, not duplicated.
        second = tenant_data_mover.move_all(apply=True, delete_source=False)

    assert first["host"]["moved"] == 1
    assert second["host"]["moved"] == 0
    assert second["host"]["skipped_present"] == 1


def test_noop_when_multitenancy_disabled(db_session):
    with patch("backend.config.config.is_multitenancy_enabled", return_value=False):
        report = tenant_data_mover.move_all(apply=True)
    assert report == {"_enabled": False}


def test_verify_source_drained_reports_remaining(db_session, target_engine):
    tenant = _tenant(db_session)
    bound = _host(db_session, "bound.example.com")
    _host(db_session, "loose.example.com")  # unassigned
    host_tenant_index.bind_host_to_tenant(bound.id, tenant.id)

    status = tenant_data_mover.verify_source_drained()
    # Two hosts remain in the bootstrap DB; one is unassigned.
    assert status["host"]["remaining"] == 2
    assert status["host"]["unassigned"] == 1
