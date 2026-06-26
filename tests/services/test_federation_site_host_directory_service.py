"""Tests for the federation site-side host-directory producer:

* ``collect_host_directory`` snapshots only active hosts with the
  coordinator's entry shape.
* ``enqueue_host_directory`` is a no-op when unenrolled, otherwise queues a
  single ``host_directory`` payload of ``{"entries": [...]}``.
"""

import json

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.core import Host
from backend.services import federation_coordinator_service as csvc
from backend.services import federation_site_host_directory_service as hsvc
from backend.services import federation_sync_queue_service as qsvc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Base.metadata.tables["federation_coordinator"],
                Base.metadata.tables["federation_sync_queue"],
                Base.metadata.tables["host"],
            ],
        )
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as sess:
            yield sess
    finally:
        engine.dispose()


def _enroll(session):
    csvc.start_enrollment(
        session, coordinator_url="https://c", coordinator_tls_cert_pem="c"
    )
    csvc.mark_enrolled(
        session,
        site_id="22222222-2222-2222-2222-222222222222",
        site_tls_cert_pem="site-cert",
    )
    session.commit()


def _add_hosts(session):
    session.add_all(
        [
            Host(
                active=True,
                fqdn="a.example.com",
                ipv4="10.0.0.1",
                platform="Linux",
                platform_release="Ubuntu 24.04",
                status="up",
            ),
            Host(
                active=True, fqdn="b.example.com", ipv4="10.0.0.2", platform="Windows"
            ),
            Host(active=False, fqdn="dead.example.com", platform="Linux"),
        ]
    )
    session.commit()


class TestCollect:
    def test_collects_only_active_hosts_in_entry_shape(self, session):
        _add_hosts(session)
        entries = hsvc.collect_host_directory(session)
        assert {e["fqdn"] for e in entries} == {"a.example.com", "b.example.com"}
        host_a = next(e for e in entries if e["fqdn"] == "a.example.com")
        assert host_a["ipv4"] == "10.0.0.1"
        assert host_a["os_family"] == "Linux"
        assert host_a["os_version"] == "Ubuntu 24.04"
        assert host_a["host_id"]  # coordinator requires host_id + fqdn


class TestEnqueue:
    def test_noop_when_unenrolled(self, session):
        _add_hosts(session)
        assert hsvc.enqueue_host_directory(session) is None
        assert qsvc.queue_depth(session) == 0

    def test_enqueues_one_host_directory_payload(self, session):
        _enroll(session)
        _add_hosts(session)
        entry = hsvc.enqueue_host_directory(session)
        session.commit()
        assert entry is not None
        assert entry.payload_type == hsvc.HOST_DIRECTORY_PAYLOAD_TYPE
        payload = json.loads(entry.payload_json)
        assert len(payload["entries"]) == 2  # active only
