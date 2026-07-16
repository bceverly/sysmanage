# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 12.5 site-side secret-lease request/inbox service:
upstream request enqueue (dedup-keyed, queue-everything) and the inbox that
records the coordinator's result echo for delivery to the host.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import json

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.services import federation_secret_request_service as rsvc
from backend.services import federation_sync_queue_service as qsvc


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Base.metadata.tables["federation_sync_queue"],
                Base.metadata.tables["federation_received_secret_lease"],
            ],
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as s:
            yield s
    finally:
        engine.dispose()


def _req(session, **kw):
    defaults = dict(
        host_id="host-1",
        secret_name="db-readonly",
        backend_role="readonly",
        kind="database",
        ttl_seconds=3600,
    )
    defaults.update(kw)
    key = rsvc.enqueue_lease_request(session, **defaults)
    session.commit()
    return key


class TestEnqueue:
    def test_enqueues_one_request_payload(self, session):
        key = _req(session)
        assert qsvc.queue_depth(session) == 1
        assert key

    def test_requeue_same_key_replaces(self, session):
        key = _req(session)
        _req(session, correlation_key=key)
        assert qsvc.queue_depth(session) == 1

    def test_payload_carries_request_fields(self, session):
        _req(session, host_id="h9", secret_name="ssh-cert")
        batch = qsvc.peek_batch(session, limit=10)
        payload = json.loads(batch[0].payload_json)
        assert payload["host_id"] == "h9"
        assert payload["secret_name"] == "ssh-cert"
        assert payload["correlation_key"]

    def test_missing_fields_raise(self, session):
        with pytest.raises(ValueError):
            rsvc.enqueue_lease_request(
                session,
                host_id="",
                secret_name="x",
                backend_role="r",
                kind="database",
            )


class TestInbox:
    def test_record_then_deliver(self, session):
        row = rsvc.record_received_lease(
            session,
            correlation_key="k1",
            host_id="h1",
            secret_name="db",
            status="issued",
            secret_metadata={"username": "u"},
        )
        session.commit()
        assert len(rsvc.list_undelivered(session)) == 1
        rsvc.mark_delivered(session, row.id)
        session.commit()
        assert rsvc.list_undelivered(session) == []

    def test_record_is_idempotent_on_key(self, session):
        rsvc.record_received_lease(
            session,
            correlation_key="k1",
            host_id="h1",
            secret_name="db",
            status="issued",
        )
        rsvc.record_received_lease(
            session,
            correlation_key="k1",
            host_id="h1",
            secret_name="db",
            status="revoked",
        )
        session.commit()
        rows = rsvc.list_undelivered(session)
        assert len(rows) == 1
        assert rows[0].status == "revoked"

    def test_failed_echo_records_error(self, session):
        rsvc.record_received_lease(
            session,
            correlation_key="k2",
            host_id="h1",
            secret_name="db",
            status="failed",
            error="vault down",
        )
        session.commit()
        rows = rsvc.list_undelivered(session)
        assert rows[0].last_error == "vault down"
