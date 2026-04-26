"""
Tests for backend.api.handlers.hostname_handler.handle_hostname_changed.

The handler is fire-and-forget — it returns None and writes side effects.
The tests therefore inspect what was written to the mocked DB / connection
rather than a return value.
"""

from unittest.mock import MagicMock

import pytest

from backend.api.handlers.hostname_handler import handle_hostname_changed


def _connection(host_id="conn-host-id"):
    c = MagicMock()
    c.host_id = host_id
    return c


@pytest.mark.asyncio
async def test_no_host_id_is_a_noop():
    db = MagicMock()
    # spec=[] makes getattr(connection, "host_id", None) return None.
    connection = MagicMock(spec=[])
    await handle_hostname_changed(db, connection, {"new_hostname": "x"})
    db.query.assert_not_called()


@pytest.mark.asyncio
async def test_failure_message_is_logged_and_skipped():
    db = MagicMock()
    await handle_hostname_changed(
        db,
        _connection(),
        {"data": {"success": False, "error": "permission denied"}},
    )
    # No DB mutation when success=False.
    db.query.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_missing_new_hostname_is_skipped():
    db = MagicMock()
    await handle_hostname_changed(
        db,
        _connection(),
        {"data": {"success": True}},  # success but no new_hostname
    )
    db.query.assert_not_called()


@pytest.mark.asyncio
async def test_host_not_found_is_skipped():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    await handle_hostname_changed(
        db,
        _connection(),
        {"data": {"success": True, "new_hostname": "new.example"}},
    )
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_happy_path_updates_fqdn_and_commits():
    db = MagicMock()
    host = MagicMock(fqdn="old.example")
    db.query.return_value.filter.return_value.first.return_value = host
    await handle_hostname_changed(
        db,
        _connection(),
        {"data": {"success": True, "new_hostname": "new.example"}},
    )
    assert host.fqdn == "new.example"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_message_data_at_top_level_when_no_data_envelope():
    """Some agents send the fields at the top level instead of under .data."""
    db = MagicMock()
    host = MagicMock(fqdn="old.example")
    db.query.return_value.filter.return_value.first.return_value = host
    await handle_hostname_changed(
        db,
        _connection(),
        {"success": True, "new_hostname": "new.example"},
    )
    assert host.fqdn == "new.example"


@pytest.mark.asyncio
async def test_db_failure_rolls_back():
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")
    # Must not raise — exceptions are logged and swallowed.
    await handle_hostname_changed(
        db,
        _connection(),
        {"data": {"success": True, "new_hostname": "new.example"}},
    )
    db.rollback.assert_called_once()
