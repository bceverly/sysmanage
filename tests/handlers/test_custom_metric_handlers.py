# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for backend.api.handlers.custom_metric_handlers (Custom Metrics & Graphs
Slice 3b): ingest of the agent's ``custom_metric_samples`` message into the OSS
``custom_metric_sample`` tenant table.

Covers:
  * a valid batch inserts N rows for the right host
  * an unknown metric_id is skipped
  * an error sample stores a NULL value + status="error"
  * a missing collected_at falls back to server now()
  * a wholly-dropped batch is a graceful (loud-logged) no-op
  * missing host_id returns host_not_registered
plus the routing branch in route_inbound_message.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from backend.api.handlers.custom_metric_handlers import handle_custom_metric_samples
from backend.persistence.models.core import Host
from backend.persistence.models.custom_metric import (
    SAMPLE_STATUS_ERROR,
    SAMPLE_STATUS_OK,
    CustomMetric,
    CustomMetricSample,
)
from backend.websocket.message_router import route_inbound_message
from backend.websocket.messages import MessageType


def _connection(host_id):
    conn = MagicMock()
    conn.host_id = host_id
    conn.hostname = "metric-test-host.example.com"
    return conn


def _seed_host(db):
    host = Host(id=uuid.uuid4(), fqdn="metric-test-host.example.com", active=True)
    db.add(host)
    db.commit()
    return host


def _seed_metric(db, name="disk-free"):
    metric = CustomMetric(
        id=uuid.uuid4(),
        name=name,
        script="echo 42",
        interpreter="sh",
    )
    db.add(metric)
    db.commit()
    return metric


def _samples_for(db, host_id):
    return (
        db.query(CustomMetricSample).filter(CustomMetricSample.host_id == host_id).all()
    )


@pytest.mark.asyncio
async def test_valid_batch_inserts_rows_for_host(db_session):
    host = _seed_host(db_session)
    m1 = _seed_metric(db_session, "disk-free")
    m2 = _seed_metric(db_session, "load-avg")

    result = await handle_custom_metric_samples(
        db_session,
        _connection(host.id),
        {
            "samples": [
                {
                    "metric_id": str(m1.id),
                    "value": 12.5,
                    "status": "ok",
                    "error_detail": None,
                    "collected_at": "2026-07-09T10:00:00+00:00",
                },
                {
                    "metric_id": str(m2.id),
                    "value": 0.75,
                    "status": "ok",
                    "error_detail": None,
                    "collected_at": "2026-07-09T10:00:00Z",
                },
            ]
        },
    )

    assert result["message_type"] == "custom_metric_samples_ack"
    rows = _samples_for(db_session, host.id)
    assert len(rows) == 2
    assert all(r.host_id == host.id for r in rows)
    values = sorted(r.value for r in rows)
    assert values == [0.75, 12.5]


@pytest.mark.asyncio
async def test_unknown_metric_id_is_skipped(db_session):
    host = _seed_host(db_session)
    known = _seed_metric(db_session)

    await handle_custom_metric_samples(
        db_session,
        _connection(host.id),
        {
            "samples": [
                {
                    "metric_id": str(known.id),
                    "value": 1.0,
                    "status": "ok",
                    "collected_at": "2026-07-09T10:00:00+00:00",
                },
                {
                    # never-seen metric id -> skipped
                    "metric_id": str(uuid.uuid4()),
                    "value": 2.0,
                    "status": "ok",
                    "collected_at": "2026-07-09T10:00:00+00:00",
                },
            ]
        },
    )

    rows = _samples_for(db_session, host.id)
    assert len(rows) == 1
    assert rows[0].custom_metric_id == known.id


@pytest.mark.asyncio
async def test_error_sample_stores_null_value_and_status(db_session):
    host = _seed_host(db_session)
    metric = _seed_metric(db_session)

    await handle_custom_metric_samples(
        db_session,
        _connection(host.id),
        {
            "samples": [
                {
                    "metric_id": str(metric.id),
                    # value present but must be dropped because status=error
                    "value": 99.0,
                    "status": "error",
                    "error_detail": "script exited 1",
                    "collected_at": "2026-07-09T10:00:00+00:00",
                }
            ]
        },
    )

    rows = _samples_for(db_session, host.id)
    assert len(rows) == 1
    assert rows[0].status == SAMPLE_STATUS_ERROR
    assert rows[0].value is None
    assert rows[0].error_detail == "script exited 1"


@pytest.mark.asyncio
async def test_missing_collected_at_falls_back_to_now(db_session):
    host = _seed_host(db_session)
    metric = _seed_metric(db_session)

    before = datetime.now(timezone.utc)
    await handle_custom_metric_samples(
        db_session,
        _connection(host.id),
        {
            "samples": [
                {
                    "metric_id": str(metric.id),
                    "value": 3.0,
                    "status": "ok",
                    # no collected_at
                }
            ]
        },
    )
    after = datetime.now(timezone.utc)

    rows = _samples_for(db_session, host.id)
    assert len(rows) == 1
    collected = rows[0].collected_at
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=timezone.utc)
    assert before <= collected <= after


@pytest.mark.asyncio
async def test_unparseable_collected_at_falls_back_to_now(db_session):
    host = _seed_host(db_session)
    metric = _seed_metric(db_session)

    before = datetime.now(timezone.utc)
    await handle_custom_metric_samples(
        db_session,
        _connection(host.id),
        {
            "samples": [
                {
                    "metric_id": str(metric.id),
                    "value": 3.0,
                    "status": "ok",
                    "collected_at": "not-a-timestamp",
                }
            ]
        },
    )
    after = datetime.now(timezone.utc)

    rows = _samples_for(db_session, host.id)
    assert len(rows) == 1
    collected = rows[0].collected_at
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=timezone.utc)
    assert before <= collected <= after


@pytest.mark.asyncio
async def test_wholly_unknown_batch_is_graceful_noop(db_session):
    host = _seed_host(db_session)
    # No metric seeded -> every metric_id is unknown.

    result = await handle_custom_metric_samples(
        db_session,
        _connection(host.id),
        {
            "samples": [
                {"metric_id": str(uuid.uuid4()), "value": 1.0, "status": "ok"},
            ]
        },
    )

    assert result["message_type"] == "custom_metric_samples_ack"
    assert _samples_for(db_session, host.id) == []


@pytest.mark.asyncio
async def test_empty_batch_is_graceful(db_session):
    host = _seed_host(db_session)
    result = await handle_custom_metric_samples(
        db_session, _connection(host.id), {"samples": []}
    )
    assert result["message_type"] == "custom_metric_samples_ack"


@pytest.mark.asyncio
async def test_missing_host_id_returns_error(db_session):
    result = await handle_custom_metric_samples(
        db_session,
        _connection(None),
        {"samples": [{"metric_id": str(uuid.uuid4())}]},
    )
    assert result["error_type"] == "host_not_registered"


@pytest.mark.asyncio
async def test_router_dispatches_custom_metric_samples():
    """route_inbound_message routes CUSTOM_METRIC_SAMPLES to the handler."""
    mock_db = Mock()
    conn = Mock()
    conn.host_id = "test-host-id"
    conn.hostname = "test-host"
    message_data = {"samples": []}

    with patch(
        "backend.websocket.message_router.handle_custom_metric_samples",
        new_callable=AsyncMock,
    ) as mock_handler:
        result = await route_inbound_message(
            MessageType.CUSTOM_METRIC_SAMPLES, mock_db, conn, message_data
        )

    assert result is True
    mock_handler.assert_called_once_with(mock_db, conn, message_data)
