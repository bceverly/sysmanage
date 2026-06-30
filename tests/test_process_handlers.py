"""Tests for backend/api/handlers/process_handlers.py (Phase 13.3)."""

from unittest.mock import Mock, patch

import pytest

from backend.api.handlers.process_handlers import handle_process_status_update
from backend.persistence import models

HOST_ID = "550e8400-e29b-41d4-a716-446655440099"


@pytest.fixture
def mock_connection():
    connection = Mock()
    connection.host_id = HOST_ID
    connection.hostname = "test-host"
    return connection


@pytest.fixture
def sample_host(session):
    host = models.Host(
        id=HOST_ID,
        fqdn="proc-host.example.com",
        ipv4="192.168.1.50",
        active=True,
        platform="Ubuntu",
        platform_release="22.04",
        approval_status="approved",
    )
    session.add(host)
    session.commit()
    return host


def _msg(procs):
    return {
        "host_id": HOST_ID,
        "hostname": "test-host",
        "processes": procs,
        "process_count": len(procs),
        "collected_at": "2026-06-30T12:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_stores_snapshot(session, mock_connection, sample_host):
    msg = _msg(
        [
            {
                "pid": 1234,
                "parent_pid": 1,
                "name": "python3",
                "username": "root",
                "status": "running",
                "cpu_percent": 12.5,
                "memory_percent": 3.2,
                "memory_rss_bytes": 104857600,
                "command_line": "python3 /app/main.py",
                "started_at": "2026-06-30T11:00:00+00:00",
            },
            {
                "pid": 5678,
                "name": "nginx",
                "username": "www-data",
                "cpu_percent": 0.1,
                "memory_percent": 0.5,
            },
        ]
    )
    with patch("backend.utils.host_validation.validate_host_id"):
        result = await handle_process_status_update(session, mock_connection, msg)

    assert result["message_type"] == "process_status_update_ack"
    rows = session.query(models.HostProcess).filter_by(host_id=HOST_ID).all()
    assert len(rows) == 2
    py = next(r for r in rows if r.pid == 1234)
    assert py.process_name == "python3"
    assert py.username == "root"
    assert py.cpu_percent == 12.5
    assert py.memory_rss_bytes == 104857600
    assert py.started_at is not None
    assert py.collected_at is not None


@pytest.mark.asyncio
async def test_replaces_prior_snapshot(session, mock_connection, sample_host):
    with patch("backend.utils.host_validation.validate_host_id"):
        await handle_process_status_update(
            session, mock_connection, _msg([{"pid": 1, "name": "old"}])
        )
        await handle_process_status_update(
            session,
            mock_connection,
            _msg([{"pid": 2, "name": "new"}, {"pid": 3, "name": "new2"}]),
        )

    rows = session.query(models.HostProcess).filter_by(host_id=HOST_ID).all()
    assert {r.pid for r in rows} == {2, 3}  # old snapshot fully replaced


@pytest.mark.asyncio
async def test_skips_rows_without_pid(session, mock_connection, sample_host):
    msg = _msg([{"name": "no-pid"}, {"pid": 42, "name": "ok"}])
    with patch("backend.utils.host_validation.validate_host_id"):
        await handle_process_status_update(session, mock_connection, msg)
    rows = session.query(models.HostProcess).filter_by(host_id=HOST_ID).all()
    assert len(rows) == 1
    assert rows[0].pid == 42


@pytest.mark.asyncio
async def test_no_host_id_errors(session):
    connection = Mock()
    connection.host_id = None
    msg = {"processes": [{"pid": 1, "name": "x"}]}
    with patch("backend.utils.host_validation.validate_host_id"):
        result = await handle_process_status_update(session, connection, msg)
    assert result["message_type"] == "error"


@pytest.mark.asyncio
async def test_invalid_agent_host_id_errors(session, mock_connection):
    msg = {"host_id": "not-a-real-host", "processes": []}
    with patch(
        "backend.utils.host_validation.validate_host_id",
        return_value=False,
    ):
        result = await handle_process_status_update(session, mock_connection, msg)
    assert result["message_type"] == "error"
    assert result["error_type"] == "host_not_registered"
