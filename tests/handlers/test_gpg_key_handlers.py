# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for backend.api.handlers.gpg_key_handlers (GPG Key Management Slice 3b).

Covers the install/remove command-result -> gpg_key_assignment.status flip:
  * install success   -> installed
  * install failure   -> failed
  * remove success (row present) -> row deleted
  * remove failure (row present) -> failed
  * remove (row already gone) -> graceful no-op
plus the routing branch in handle_command_result.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from backend.api.handlers.gpg_key_handlers import handle_gpg_key_command_result
from backend.api.message_handlers import handle_command_result
from backend.persistence.models.core import Host
from backend.persistence.models.gpg_key import (
    ASSIGNMENT_FAILED,
    ASSIGNMENT_INSTALLED,
    ASSIGNMENT_PENDING,
    ASSIGNMENT_REMOVING,
    GpgKey,
    GpgKeyAssignment,
)


def _connection(host_id):
    conn = MagicMock()
    conn.host_id = host_id
    conn.hostname = "gpg-test-host.example.com"
    return conn


def _seed_host(db):
    host = Host(id=uuid.uuid4(), fqdn="gpg-test-host.example.com", active=True)
    db.add(host)
    db.commit()
    return host


def _seed_key(db):
    key = GpgKey(
        id=uuid.uuid4(),
        name="release-signing-key",
        key_type="public",
        openbao_secret_id="vault/path/ref",
    )
    db.add(key)
    db.commit()
    return key


def _seed_assignment(db, key_id, host_id, target_username, status=ASSIGNMENT_PENDING):
    assignment = GpgKeyAssignment(
        id=uuid.uuid4(),
        gpg_key_id=key_id,
        host_id=host_id,
        target_username=target_username,
        status=status,
    )
    db.add(assignment)
    db.commit()
    return assignment


@pytest.mark.asyncio
async def test_install_success_sets_installed(db_session):
    host = _seed_host(db_session)
    key = _seed_key(db_session)
    assignment = _seed_assignment(db_session, key.id, host.id, None)

    result = await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {
            "command_type": "install_gpg_key",
            "success": True,
            "result": {"key_id": str(key.id), "target_username": None},
        },
    )

    db_session.refresh(assignment)
    assert assignment.status == ASSIGNMENT_INSTALLED
    assert result["message_type"] == "command_result_ack"


@pytest.mark.asyncio
async def test_install_failure_sets_failed(db_session):
    host = _seed_host(db_session)
    key = _seed_key(db_session)
    assignment = _seed_assignment(db_session, key.id, host.id, "alice")

    await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {
            "command_type": "install_gpg_key",
            "success": False,
            "result": {"key_id": str(key.id), "target_username": "alice"},
        },
    )

    db_session.refresh(assignment)
    assert assignment.status == ASSIGNMENT_FAILED


@pytest.mark.asyncio
async def test_install_prefers_pending_assignment(db_session):
    """When a terminal row and a pending row both match, the pending one flips."""
    host = _seed_host(db_session)
    key = _seed_key(db_session)
    _seed_assignment(db_session, key.id, host.id, None, status=ASSIGNMENT_FAILED)
    pending = _seed_assignment(
        db_session, key.id, host.id, None, status=ASSIGNMENT_PENDING
    )

    await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {
            "command_type": "install_gpg_key",
            "success": True,
            "result": {"key_id": str(key.id), "target_username": None},
        },
    )

    db_session.refresh(pending)
    assert pending.status == ASSIGNMENT_INSTALLED


@pytest.mark.asyncio
async def test_remove_success_deletes_row(db_session):
    """On a successful removal the assignment row is dropped entirely (the key
    is truly gone from the host, so the assignment should disappear too)."""
    host = _seed_host(db_session)
    key = _seed_key(db_session)
    assignment = _seed_assignment(
        db_session, key.id, host.id, None, status=ASSIGNMENT_REMOVING
    )
    assignment_id = assignment.id

    result = await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {
            "command_type": "remove_gpg_key",
            "success": True,
            "result": {"key_id": str(key.id), "target_username": None},
        },
    )

    assert result["message_type"] == "command_result_ack"
    assert (
        db_session.query(GpgKeyAssignment)
        .filter(GpgKeyAssignment.id == assignment_id)
        .first()
        is None
    )


@pytest.mark.asyncio
async def test_remove_failure_sets_failed(db_session):
    host = _seed_host(db_session)
    key = _seed_key(db_session)
    assignment = _seed_assignment(
        db_session, key.id, host.id, None, status=ASSIGNMENT_REMOVING
    )

    await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {
            "command_type": "remove_gpg_key",
            "success": False,
            "result": {"key_id": str(key.id), "target_username": None},
        },
    )

    db_session.refresh(assignment)
    assert assignment.status == ASSIGNMENT_FAILED


@pytest.mark.asyncio
async def test_remove_when_row_already_gone_is_graceful_noop(db_session):
    """If no assignment row is present (e.g. a duplicate removal result), the
    handler must no-op gracefully rather than raise."""
    host = _seed_host(db_session)
    key = _seed_key(db_session)
    # No assignment row seeded.

    result = await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {
            "command_type": "remove_gpg_key",
            "success": True,
            "result": {"key_id": str(key.id), "target_username": None},
        },
    )

    assert result["message_type"] == "command_result_ack"


@pytest.mark.asyncio
async def test_install_missing_assignment_is_graceful(db_session):
    host = _seed_host(db_session)
    key = _seed_key(db_session)

    result = await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {
            "command_type": "install_gpg_key",
            "success": True,
            "result": {"key_id": str(key.id), "target_username": None},
        },
    )

    assert result["message_type"] == "command_result_ack"


@pytest.mark.asyncio
async def test_missing_host_id_returns_error(db_session):
    result = await handle_gpg_key_command_result(
        db_session,
        _connection(None),
        {
            "command_type": "install_gpg_key",
            "success": True,
            "result": {"key_id": str(uuid.uuid4())},
        },
    )
    assert result["error_type"] == "host_not_registered"


@pytest.mark.asyncio
async def test_missing_key_id_is_graceful(db_session):
    host = _seed_host(db_session)
    result = await handle_gpg_key_command_result(
        db_session,
        _connection(host.id),
        {"command_type": "install_gpg_key", "success": True, "result": {}},
    )
    assert result["message_type"] == "command_result_ack"


@pytest.mark.asyncio
async def test_command_result_routes_to_gpg_handler(db_session):
    """handle_command_result dispatches install/remove to the GPG handler."""
    host = _seed_host(db_session)
    key = _seed_key(db_session)
    assignment = _seed_assignment(db_session, key.id, host.id, None)

    await handle_command_result(
        db_session,
        _connection(host.id),
        {
            "message_type": "command_result",
            "command_type": "install_gpg_key",
            "success": True,
            "result": {"key_id": str(key.id), "target_username": None},
        },
    )

    db_session.refresh(assignment)
    assert assignment.status == ASSIGNMENT_INSTALLED
