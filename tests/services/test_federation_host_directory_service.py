# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.1.E cross-site host directory search.

Covers:
  * Filter composition (site_ids, fqdn_contains, os_family, status,
    geo_country_code, last_seen window, free_text OR).
  * Pagination (limit + offset) returns the right slice + total count.
  * Order-by whitelist rejects unknown columns.
  * Status / country breakdowns roll up correctly with NULL-bucket
    semantics ("unknown" for NULL status, ``""`` for NULL country).
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.services import federation_host_directory_service as hsvc
from backend.services import federation_rollup_service as rsvc
from backend.services import federation_site_service as ssvc
from tests.federation_crypto import quick_enroll

FEDERATION_TABLE_NAMES = [
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


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in FEDERATION_TABLE_NAMES]
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


def _make_site(session, name):
    """Helper: enrolled site with one line."""
    site = quick_enroll(session, name=name, url=f"https://{name}.x")
    session.commit()
    return site


def _add_host(session, site, **kwargs):
    host_id = uuid.uuid4()
    rsvc.upsert_host_directory_entry(
        session, site_id=site.id, host_id=host_id, **kwargs
    )
    return host_id


@pytest.fixture
def fleet(session):
    """Two sites, six hosts spread across them with a mix of states."""
    cle = _make_site(session, "Cleveland")
    pit = _make_site(session, "Pittsburgh")
    _add_host(
        session,
        cle,
        fqdn="web1.cle.example.com",
        ipv4="10.0.0.10",
        os_family="ubuntu",
        status="up",
        geo_country_code="US",
        geo_subdivision_code="US-OH",
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    _add_host(
        session,
        cle,
        fqdn="web2.cle.example.com",
        ipv4="10.0.0.11",
        os_family="ubuntu",
        status="down",
        geo_country_code="US",
        geo_subdivision_code="US-OH",
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2),
    )
    _add_host(
        session,
        cle,
        fqdn="db1.cle.example.com",
        ipv4="10.0.1.5",
        os_family="debian",
        status="up",
        geo_country_code="US",
        geo_subdivision_code="US-OH",
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    _add_host(
        session,
        pit,
        fqdn="web1.pit.example.com",
        ipv4="10.1.0.10",
        os_family="rhel",
        status="up",
        geo_country_code="US",
        geo_subdivision_code="US-PA",
        last_seen=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    _add_host(
        session,
        pit,
        fqdn="web2.pit.example.com",
        ipv4="10.1.0.11",
        os_family="rhel",
        status="unknown",
        geo_country_code="US",
        geo_subdivision_code="US-PA",
    )
    _add_host(
        session,
        pit,
        fqdn="dev1.pit.example.com",
        ipv4="10.1.1.5",
        os_family="ubuntu",
        # NULL status + NULL country to exercise the unknown-bucket branches
        last_seen=None,
    )
    session.commit()
    return {"cle": cle, "pit": pit}


# ---------------------------------------------------------------------
# search_hosts
# ---------------------------------------------------------------------


class TestSearchHosts:
    def test_no_filters_returns_all(self, session, fleet):
        rows, total = hsvc.search_hosts(session)
        assert total == 6
        assert len(rows) == 6

    def test_site_filter(self, session, fleet):
        rows, total = hsvc.search_hosts(session, site_ids=[fleet["cle"].id])
        assert total == 3
        assert all(r.site_id == fleet["cle"].id for r in rows)

    def test_multi_site_filter(self, session, fleet):
        rows, total = hsvc.search_hosts(
            session, site_ids=[fleet["cle"].id, fleet["pit"].id]
        )
        assert total == 6

    def test_os_family_filter(self, session, fleet):
        rows, total = hsvc.search_hosts(session, os_family="ubuntu")
        assert total == 3
        assert all(r.os_family == "ubuntu" for r in rows)

    def test_status_filter(self, session, fleet):
        rows, total = hsvc.search_hosts(session, status="up")
        assert total == 3

    def test_fqdn_contains(self, session, fleet):
        rows, total = hsvc.search_hosts(session, fqdn_contains="web")
        assert total == 4
        assert all("web" in r.fqdn for r in rows)

    def test_ipv4_contains(self, session, fleet):
        rows, total = hsvc.search_hosts(session, ipv4_contains="10.0.")
        # 10.0.0.10, 10.0.0.11, 10.0.1.5 — the Cleveland /16.
        assert total == 3

    def test_geo_country_filter(self, session, fleet):
        rows, total = hsvc.search_hosts(session, geo_country_code="US")
        assert total == 5  # one host has NULL country

    def test_geo_subdivision_filter(self, session, fleet):
        rows, total = hsvc.search_hosts(session, geo_subdivision_code="US-OH")
        assert total == 3

    def test_last_seen_after(self, session, fleet):
        # Anything within the last hour.
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        rows, total = hsvc.search_hosts(session, last_seen_after=cutoff)
        # web1.cle, db1.cle, web1.pit — three "current" hosts.
        assert total == 3

    def test_free_text_or(self, session, fleet):
        # Single ``free_text`` should match across fqdn OR ipv4 OR public_ip.
        # "10.1.0" matches the two pit web hosts' ipv4 column.
        rows, total = hsvc.search_hosts(session, free_text="10.1.0")
        assert total == 2

    def test_filters_compose_with_and(self, session, fleet):
        rows, total = hsvc.search_hosts(
            session,
            site_ids=[fleet["cle"].id],
            os_family="ubuntu",
            status="up",
        )
        assert total == 1
        assert rows[0].fqdn == "web1.cle.example.com"

    def test_pagination(self, session, fleet):
        page1, total = hsvc.search_hosts(session, limit=2, offset=0)
        page2, _ = hsvc.search_hosts(session, limit=2, offset=2)
        page3, _ = hsvc.search_hosts(session, limit=2, offset=4)
        assert total == 6
        assert len(page1) == 2 and len(page2) == 2 and len(page3) == 2
        # Pages don't overlap.
        all_ids = {r.host_id for r in page1 + page2 + page3}
        assert len(all_ids) == 6

    def test_order_by_status(self, session, fleet):
        rows, _ = hsvc.search_hosts(session, order_by="status", limit=100)
        # ``down`` < ``unknown`` < ``up`` lexically, with NULL first
        # (varies by dialect — but at minimum the call must succeed).
        assert len(rows) == 6

    def test_invalid_order_by_raises(self, session, fleet):
        with pytest.raises(ValueError):
            hsvc.search_hosts(session, order_by="ipv4")  # not whitelisted

    def test_negative_offset_raises(self, session, fleet):
        with pytest.raises(ValueError):
            hsvc.search_hosts(session, offset=-1)

    def test_limit_zero_raises(self, session, fleet):
        with pytest.raises(ValueError):
            hsvc.search_hosts(session, limit=0)

    def test_limit_above_cap_raises(self, session, fleet):
        with pytest.raises(ValueError):
            hsvc.search_hosts(session, limit=hsvc.MAX_PAGE_LIMIT + 1)


# ---------------------------------------------------------------------
# count_hosts
# ---------------------------------------------------------------------


class TestCountHosts:
    def test_count_no_filters(self, session, fleet):
        assert hsvc.count_hosts(session) == 6

    def test_count_with_filter(self, session, fleet):
        assert hsvc.count_hosts(session, os_family="ubuntu") == 3

    def test_count_no_match(self, session, fleet):
        assert hsvc.count_hosts(session, os_family="aix") == 0


# ---------------------------------------------------------------------
# Breakdowns
# ---------------------------------------------------------------------


class TestStatusBreakdown:
    def test_unknown_bucket_for_null_status(self, session, fleet):
        result = hsvc.status_breakdown(session)
        # 3 up, 1 down, 1 "unknown" (string), 1 NULL (also bucketed
        # under "unknown" by the service per its contract).
        assert result["up"] == 3
        assert result["down"] == 1
        assert result["unknown"] == 2

    def test_breakdown_filtered_by_site(self, session, fleet):
        result = hsvc.status_breakdown(session, site_ids=[fleet["cle"].id])
        assert sum(result.values()) == 3


class TestCountryBreakdown:
    def test_empty_string_bucket_for_null_country(self, session, fleet):
        result = hsvc.country_breakdown(session)
        # 5 US + 1 NULL (-> "").
        assert result["US"] == 5
        assert result[""] == 1

    def test_country_breakdown_filtered_by_site(self, session, fleet):
        result = hsvc.country_breakdown(session, site_ids=[fleet["pit"].id])
        # Pit hosts: 2 US-PA + 1 NULL.
        assert result.get("US") == 2
        assert result.get("") == 1
