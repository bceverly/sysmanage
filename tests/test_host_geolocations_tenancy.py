# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The host map reads the ACTIVE TENANT's hosts.

``/hosts/geolocations`` read the bootstrap database, which holds no hosts once
multi-tenancy is on, so the map was empty while the tenant database had the
coordinates (production, 2026-10-16).  The handler also runs its query in a
thread-pool executor, which the active-tenant ContextVar does not reach, so it
must hand the tenant over explicitly."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import host as host_api
from backend.persistence import models
from backend.persistence.db import Base


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _host(engine, fqdn, lat=40.0, lon=-75.0):
    with sessionmaker(bind=engine)() as db:
        db.add(
            models.Host(
                id=uuid.uuid4(),
                fqdn=fqdn,
                active=True,
                status="up",
                platform="Linux",
                approval_status="approved",
                geo_country_code="US",
                geo_latitude=lat,
                geo_longitude=lon,
            )
        )
        db.commit()


@pytest.fixture
def engines():
    bootstrap, tenant = _engine(), _engine()
    _host(tenant, "nas")
    _host(tenant, "beast")
    yield {"bootstrap": bootstrap, "t1": tenant}
    bootstrap.dispose()
    tenant.dispose()


def _routed(engines):
    def request_sessionmaker(tenant_id=None):
        return sessionmaker(bind=engines["t1" if tenant_id == "t1" else "bootstrap"])

    return patch(
        "backend.persistence.partitions.request_sessionmaker",
        side_effect=request_sessionmaker,
    )


def test_the_tenant_hosts_are_returned(engines):
    with _routed(engines):
        rows = host_api._get_host_geolocations_sync("t1")
    assert sorted(r["fqdn"] for r in rows) == ["beast", "nas"]


def test_server_scope_reads_the_bootstrap_database(engines):
    with _routed(engines):
        assert host_api._get_host_geolocations_sync(None) == []


@pytest.mark.asyncio
async def test_the_handler_hands_the_active_tenant_to_the_worker_thread(engines):
    with _routed(engines), patch(
        "backend.persistence.tenant_context.get_active_tenant", return_value="t1"
    ):
        rows = await host_api.get_host_geolocations()
    assert sorted(r["fqdn"] for r in rows) == ["beast", "nas"]
