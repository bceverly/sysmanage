"""Scale / performance harness for the federation coordinator read paths.

The coordinator is the federation choke point: every site pushes its full
host directory up, and the Hosts / Sites / Reports pages then query the
*aggregate* directory tier (potentially 100 sites x 10k hosts = 1M rows).
This harness seeds that tier at a configurable scale and times the hot
read paths — paginated search, the count/group-by aggregates, and the
cross-site report — so a regression that turns one of them into a table
scan shows up as a wall-clock blow-up instead of a silent slowdown in
production.

It is **tiny by default** (5 sites x 200 hosts = 1,000 rows, sub-second)
so it can ride along in the normal suite as a shape-level smoke of the
query paths.  Crank it to the real target with environment variables:

    FED_PERF_SITES=100 FED_PERF_HOSTS_PER_SITE=10000 \
        .venv/bin/python -m pytest tests/performance/test_federation_scale.py -s -m performance

Knobs (all optional):
    FED_PERF_SITES            sites to seed                      (default 5)
    FED_PERF_HOSTS_PER_SITE   host-directory rows per site       (default 200)
    FED_PERF_PAGE_LIMIT       page size for the search path      (default 50)
    FED_PERF_DB_URL           SQLAlchemy URL; point at Postgres
                              for realistic 1M-row numbers       (default
                              in-memory sqlite)
    FED_PERF_ASSERT_MS        if set, every timed read must finish
                              under this many ms or the test fails
                              (CI gate; unset = measure-and-log only)

Run with ``-s`` to see the timing lines.
"""

# pylint: disable=redefined-outer-name

import os
import time
import uuid
from contextlib import contextmanager

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.persistence import models  # noqa: F401  # register all models
from backend.persistence.db import Base
from backend.persistence.models.federation import (
    FederationHostDirectory,
    FederationSite,
)
from backend.services import federation_host_directory_service as dir_svc
from backend.services import federation_rollup_service as rollup_svc

pytestmark = pytest.mark.performance

_SITES = int(os.environ.get("FED_PERF_SITES", "5"))
_HOSTS_PER_SITE = int(os.environ.get("FED_PERF_HOSTS_PER_SITE", "200"))
_PAGE_LIMIT = int(os.environ.get("FED_PERF_PAGE_LIMIT", "50"))
_DB_URL = os.environ.get("FED_PERF_DB_URL", "sqlite:///:memory:")
_ASSERT_MS = (
    float(os.environ["FED_PERF_ASSERT_MS"])
    if os.environ.get("FED_PERF_ASSERT_MS")
    else None
)
_TOTAL_HOSTS = _SITES * _HOSTS_PER_SITE
_INSERT_BATCH = 5000

# Spread rows across a handful of distinct values so the GROUP BY / filter
# paths have real cardinality to chew on (not one giant bucket).
_OS_FAMILIES = ("Linux", "Windows", "Darwin", "FreeBSD")
_PLATFORMS = ("Ubuntu", "RHEL", "Windows Server", "macOS", "OpenBSD")
_STATUSES = ("up", "down", "unknown")
_COUNTRIES = ("US", "GB", "DE", "JP", "BR", "IN")


@contextmanager
def _timed(label: str):
    start = time.perf_counter()
    box = {}
    yield box
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    box["ms"] = elapsed_ms
    print(
        f"[fed-perf] {label}: {elapsed_ms:8.1f} ms "
        f"({_SITES} sites x {_HOSTS_PER_SITE} = {_TOTAL_HOSTS:,} hosts, db={_DB_URL})"
    )
    if _ASSERT_MS is not None:
        assert elapsed_ms <= _ASSERT_MS, (
            f"{label} took {elapsed_ms:.1f} ms, over the "
            f"FED_PERF_ASSERT_MS={_ASSERT_MS} ms budget"
        )


def _make_engine():
    if _DB_URL.startswith("sqlite") and ":memory:" in _DB_URL:
        # One shared connection so the seeded rows are visible to every query
        # (a fresh in-memory connection would be an empty database).
        return sa.create_engine(
            _DB_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return sa.create_engine(_DB_URL)


def _seed(session, site_ids):
    """Bulk-insert sites + host-directory rows via core executemany batches.

    Uses ``insert()`` rather than the ORM upsert so seeding 1M rows is an
    I/O-bound bulk load, not 1M flush cycles."""
    session.execute(
        sa.insert(FederationSite.__table__),
        [
            {
                "id": sid,
                "name": f"site-{i:04d}",
                "url": f"https://site-{i:04d}.example.com",
                "status": "enrolled",
                "host_count": _HOSTS_PER_SITE,
                "sync_interval_seconds": 300,
            }
            for i, sid in enumerate(site_ids)
        ],
    )

    batch = []
    n = 0
    for site_idx, sid in enumerate(site_ids):
        for h in range(_HOSTS_PER_SITE):
            batch.append(
                {
                    "host_id": uuid.uuid4(),
                    "site_id": sid,
                    "fqdn": f"host-{site_idx:04d}-{h:06d}.example.com",
                    "ipv4": f"10.{site_idx % 256}.{(h >> 8) & 255}.{h & 255}",
                    "os_family": _OS_FAMILIES[n % len(_OS_FAMILIES)],
                    "platform": _PLATFORMS[n % len(_PLATFORMS)],
                    "status": _STATUSES[n % len(_STATUSES)],
                    "geo_country_code": _COUNTRIES[n % len(_COUNTRIES)],
                }
            )
            n += 1
            if len(batch) >= _INSERT_BATCH:
                session.execute(sa.insert(FederationHostDirectory.__table__), batch)
                batch = []
    if batch:
        session.execute(sa.insert(FederationHostDirectory.__table__), batch)
    session.commit()


@pytest.fixture(scope="module")
def seeded():
    engine = _make_engine()
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    site_ids = [uuid.uuid4() for _ in range(_SITES)]
    session = session_factory()
    try:
        with _timed("seed"):
            _seed(session, site_ids)
        yield session, site_ids
    finally:
        session.close()
        engine.dispose()


def test_seed_row_counts(seeded):
    """Sanity: the harness actually loaded the configured scale."""
    session, _site_ids = seeded
    assert dir_svc.count_hosts(session) == _TOTAL_HOSTS


def test_search_hosts_paginated(seeded):
    """First page of an ordered, filtered cross-site search — the Hosts page
    hot path.  Must page (not materialize the whole tier) at any scale."""
    session, _site_ids = seeded
    with _timed("search_hosts (page 1, status=up, ordered)"):
        rows, total = dir_svc.search_hosts(
            session,
            status="up",
            order_by="fqdn",
            limit=_PAGE_LIMIT,
            offset=0,
        )
    assert len(rows) <= _PAGE_LIMIT
    # 'up' is every 3rd row by construction; the page must never exceed the
    # match total and the total must be a sane fraction of the fleet.
    assert 0 < total <= _TOTAL_HOSTS
    assert len(rows) == min(_PAGE_LIMIT, total)


def test_search_hosts_free_text(seeded):
    """Free-text search box (ORs fqdn / ipv4 / public_ip)."""
    session, _site_ids = seeded
    with _timed("search_hosts (free_text)"):
        rows, total = dir_svc.search_hosts(
            session,
            free_text="host-0000-",
            limit=_PAGE_LIMIT,
            offset=0,
        )
    assert total >= 0
    assert len(rows) <= _PAGE_LIMIT


def test_count_and_breakdowns(seeded):
    """Aggregates that power the dashboard tiles — full-tier GROUP BY."""
    session, _site_ids = seeded
    with _timed("count_hosts (all)"):
        total = dir_svc.count_hosts(session)
    assert total == _TOTAL_HOSTS

    with _timed("status_breakdown"):
        statuses = dir_svc.status_breakdown(session)
    assert sum(statuses.values()) == _TOTAL_HOSTS

    with _timed("country_breakdown"):
        countries = dir_svc.country_breakdown(session)
    assert sum(countries.values()) == _TOTAL_HOSTS


def test_cross_site_report(seeded):
    """Cross-site Reports facet — one aggregate row per enrolled site."""
    session, _site_ids = seeded
    with _timed("get_cross_site_report"):
        report = rollup_svc.get_cross_site_report(session)
    assert report["totals"]["site_count"] == _SITES
    assert len(report["sites"]) == _SITES
