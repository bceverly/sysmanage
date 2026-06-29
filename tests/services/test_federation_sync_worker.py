"""
End-to-end integration tests for the Phase 12.10 Slice 2 site-side
sync worker.

The worker lives in the Pro+ ``federation_site_engine`` Cython
module (``module-source/federation_site_engine/federation_site_engine.pyx``);
these tests import the compiled ``.so`` directly from the Pro+ repo's
``storage/modules/`` tree, drive its private ``_drain_once`` coroutine
against a real in-memory SQLite + a mocked ``httpx.AsyncClient``, and
assert end-to-end behaviour:

  * Idle when not enrolled or missing bearer.
  * URL composition and ``Authorization: Bearer`` header.
  * Endpoint routing per payload_type matches the Slice 1 ingest
    contract.
  * Failure modes: 4xx, network exception, unknown payload_type.
  * ``record_sync_attempt`` rolls the batch into the singleton's
    ``last_sync_*`` columns.

Skipped automatically when the engine ``.so`` isn't on disk — that's
the expected state in a fresh OSS-only checkout.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access,redefined-outer-name

import json
import logging
import uuid
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from backend.persistence.db import Base
from backend.persistence.models.federation import FederationSyncQueue
from backend.services import federation_coordinator_service as csvc
from backend.services import federation_sync_queue_service as qsvc


@pytest.fixture(scope="module")
def engine():
    """The real compiled federation_site_engine (see tests/_engine_loader).

    Skips only on an OSS-only run (no Pro+ checkout); fails loudly if the
    engine is present but won't load for this platform/interpreter.
    """
    from tests._engine_loader import require_engine

    return require_engine("federation_site_engine")


# ---------------------------------------------------------------------------
# In-memory federation DB
# ---------------------------------------------------------------------------


_FEDERATION_TABLE_NAMES = [
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
def fed_db():
    sa_engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        sa_engine,
        tables=[Base.metadata.tables[t] for t in _FEDERATION_TABLE_NAMES],
    )
    try:
        yield sa_engine
    finally:
        # ``engine.dispose()`` closes the underlying sqlite3
        # connections so they don't linger in pytest's
        # unraisable-exception handler as ResourceWarnings.
        sa_engine.dispose()


@pytest.fixture
def db_maker(fed_db):
    """A ``get_db``-style generator factory the worker can call."""
    Session = sessionmaker(bind=fed_db, expire_on_commit=False)

    def factory():
        sess = Session()
        try:
            yield sess
        finally:
            sess.close()

    return factory


def _seed_enrolled_coordinator(db_maker, bearer="test-bearer-abc"):
    """Insert a ``federation_coordinator`` row in ``enrolled`` state.

    Returns the assigned ``site_id`` so callers can match it against
    URL composition in the mocked httpx call list.
    """
    site_id = uuid.uuid4()
    db_gen = db_maker()
    sess = next(db_gen)
    try:
        csvc.start_enrollment(
            sess,
            coordinator_url="https://coord.example.com/",
            coordinator_tls_cert_pem="cert",
        )
        csvc.mark_enrolled(
            sess,
            site_id=site_id,
            site_tls_cert_pem="sc",
            sync_bearer_token=bearer,
        )
        sess.commit()
    finally:
        next(db_gen, None)
    return site_id


def _enqueue(db_maker, payload_type, payload):
    db_gen = db_maker()
    sess = next(db_gen)
    try:
        entry = qsvc.enqueue(sess, payload_type=payload_type, payload=payload)
        sess.commit()
        return entry.id
    finally:
        next(db_gen, None)


def _queue_depth(db_maker):
    db_gen = db_maker()
    sess = next(db_gen)
    try:
        return qsvc.queue_depth(sess)
    finally:
        next(db_gen, None)


def _make_response(status_code, text=""):
    resp = AsyncMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drain_once_idle_when_not_enrolled(engine, db_maker):
    client = AsyncMock()
    counts = await engine._drain_once(db_maker, client, logging.getLogger("test"))
    assert counts == {"sent": 0, "failed": 0, "skipped": 0}
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_drain_once_idle_when_bearer_missing(engine, db_maker):
    """Enrolled-but-no-bearer should idle, not error."""
    db_gen = db_maker()
    sess = next(db_gen)
    try:
        csvc.start_enrollment(
            sess,
            coordinator_url="https://coord.x/",
            coordinator_tls_cert_pem="c",
        )
        csvc.mark_enrolled(sess, site_id=uuid.uuid4(), site_tls_cert_pem="sc")
        sess.commit()
    finally:
        next(db_gen, None)

    client = AsyncMock()
    counts = await engine._drain_once(db_maker, client, logging.getLogger("test"))
    assert counts == {"sent": 0, "failed": 0, "skipped": 0}
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_drain_once_posts_with_bearer_and_marks_sent(engine, db_maker):
    site_id = _seed_enrolled_coordinator(db_maker, bearer="secret-xyz")
    _enqueue(db_maker, "host_rollup", {"host_count": 5, "active_count": 4})
    assert _queue_depth(db_maker) == 1

    client = AsyncMock()
    client.post.return_value = _make_response(200, '{"licensed":true}')

    counts = await engine._drain_once(db_maker, client, logging.getLogger("test"))
    assert counts == {"sent": 1, "failed": 0, "skipped": 0}
    assert client.post.call_count == 1

    call = client.post.call_args
    assert call.args[0] == (
        f"https://coord.example.com/api/v1/federation/sites/{site_id}/rollups/hosts"
    )
    headers = call.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-xyz"
    assert headers["Content-Type"] == "application/json"
    # Worker now sends the exact JSON bytes via ``content=`` (to sign them),
    # not ``json=``.
    assert json.loads(call.kwargs["content"]) == {"host_count": 5, "active_count": 4}
    assert _queue_depth(db_maker) == 0


@pytest.mark.asyncio
async def test_drain_once_routes_each_payload_type_to_correct_endpoint(
    engine, db_maker
):
    site_id = _seed_enrolled_coordinator(db_maker)
    payloads = [
        ("host_rollup", "/rollups/hosts"),
        ("compliance_rollup", "/rollups/compliance"),
        ("vulnerability_rollup", "/rollups/vulnerabilities"),
        ("host_directory", "/host-directory"),
        ("command_result", "/command-results"),
    ]
    for ptype, _suffix in payloads:
        _enqueue(db_maker, ptype, {"placeholder": True})

    client = AsyncMock()
    client.post.return_value = _make_response(200)

    counts = await engine._drain_once(db_maker, client, logging.getLogger("test"))
    assert counts == {"sent": 5, "failed": 0, "skipped": 0}

    actual_urls = sorted(c.args[0] for c in client.post.call_args_list)
    expected_urls = sorted(
        f"https://coord.example.com/api/v1/federation/sites/{site_id}{suffix}"
        for _ptype, suffix in payloads
    )
    assert actual_urls == expected_urls


@pytest.mark.asyncio
async def test_drain_once_marks_failed_on_4xx(engine, fed_db, db_maker):
    _seed_enrolled_coordinator(db_maker)
    _enqueue(db_maker, "host_rollup", {"host_count": 1, "active_count": 1})

    client = AsyncMock()
    client.post.return_value = _make_response(
        403, '{"detail":"Bearer token does not match"}'
    )

    counts = await engine._drain_once(db_maker, client, logging.getLogger("test"))
    assert counts["failed"] == 1
    assert counts["sent"] == 0

    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        entries = sess.query(FederationSyncQueue).all()
        assert len(entries) == 1
        assert entries[0].attempts == 1
        assert "HTTP 403" in (entries[0].last_error or "")


@pytest.mark.asyncio
async def test_drain_once_marks_failed_on_network_error(engine, fed_db, db_maker):
    _seed_enrolled_coordinator(db_maker)
    _enqueue(db_maker, "host_rollup", {"host_count": 1, "active_count": 1})

    client = AsyncMock()
    client.post.side_effect = ConnectionError("coordinator unreachable")

    counts = await engine._drain_once(db_maker, client, logging.getLogger("test"))
    assert counts["failed"] == 1

    Session = sessionmaker(bind=fed_db, expire_on_commit=False)
    with Session() as sess:
        entry = sess.query(FederationSyncQueue).first()
        assert "http error" in (entry.last_error or "")
        assert "coordinator unreachable" in (entry.last_error or "")


@pytest.mark.asyncio
async def test_drain_once_skips_unknown_payload_type(engine, db_maker):
    _seed_enrolled_coordinator(db_maker)
    _enqueue(db_maker, "mystery_payload", {"x": 1})

    client = AsyncMock()
    counts = await engine._drain_once(db_maker, client, logging.getLogger("test"))
    assert counts == {"sent": 0, "failed": 0, "skipped": 1}
    assert client.post.call_count == 0


@pytest.mark.asyncio
async def test_drain_once_records_sync_attempt_on_success(engine, db_maker):
    _seed_enrolled_coordinator(db_maker)
    _enqueue(db_maker, "host_rollup", {"host_count": 1, "active_count": 1})

    client = AsyncMock()
    client.post.return_value = _make_response(200)

    await engine._drain_once(db_maker, client, logging.getLogger("test"))

    db_gen = db_maker()
    sess = next(db_gen)
    try:
        coord = csvc.get_coordinator(sess)
        assert coord.last_sync_at is not None
        assert coord.last_sync_status == "success"
        assert coord.last_sync_error is None
    finally:
        next(db_gen, None)


@pytest.mark.asyncio
async def test_drain_once_records_sync_attempt_on_failure(engine, db_maker):
    _seed_enrolled_coordinator(db_maker)
    _enqueue(db_maker, "host_rollup", {"host_count": 1, "active_count": 1})

    client = AsyncMock()
    client.post.return_value = _make_response(500, "internal error")

    await engine._drain_once(db_maker, client, logging.getLogger("test"))

    db_gen = db_maker()
    sess = next(db_gen)
    try:
        coord = csvc.get_coordinator(sess)
        assert coord.last_sync_status != "success"
        assert coord.last_sync_error is not None
    finally:
        next(db_gen, None)
