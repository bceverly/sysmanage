# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Results of work the server sent are accepted late (2026-11-17).

An agent cut off from the server mid-job keeps its result and sends it on
reconnect.  Over 30 minutes later it was rejected as "Message timestamp too
old", so an automatic update run sat "queued" for 12 hours and stalled its
rollout.  Results skip only the age limit; everything else is checked.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from backend.security.communication_security import (
    LATE_RESULT_TYPES,
    WebSocketSecurityManager,
)

MESSAGE_ID = "late-result-12345-abcdef-67890"


@pytest.fixture(name="manager")
def _manager():
    manager = WebSocketSecurityManager()
    manager.active_connections["conn"] = {
        "authenticated": True,
        "last_activity": int(time.time()),
    }
    return manager


def _message(message_type, age=timedelta(hours=1), **kw):
    stamp = (datetime.now(timezone.utc) - age).isoformat().replace("+00:00", "Z")
    message = {"message_type": message_type, "message_id": MESSAGE_ID,
               "timestamp": stamp, "data": {}}  # fmt: skip
    message.update(kw)
    return message


@pytest.mark.parametrize(
    "message_type",
    ["update_apply_result", "command_result", "backup_result", "cloud_backup_result"],
)
def test_a_result_an_hour_late_is_accepted(manager, message_type):
    assert message_type in LATE_RESULT_TYPES
    ok, error = manager.validate_message_integrity(_message(message_type), "conn")
    assert ok, error


@pytest.mark.parametrize(
    "message_type", ["heartbeat", "system_info", "package_updates"]
)
def test_any_other_old_message_is_still_refused(manager, message_type):
    ok, error = manager.validate_message_integrity(_message(message_type), "conn")
    assert not ok and "timestamp too old" in error


def test_a_late_result_still_needs_a_timestamp_that_parses(manager):
    message = _message("update_apply_result", timestamp="yesterday-ish")
    ok, error = manager.validate_message_integrity(message, "conn")
    assert not ok and "Invalid timestamp format" in error


def test_a_late_result_still_needs_its_fields(manager):
    message = _message("update_apply_result")
    del message["timestamp"]
    ok, error = manager.validate_message_integrity(message, "conn")
    assert not ok and "timestamp" in error
    message = _message("update_apply_result", message_id="short")
    ok, error = manager.validate_message_integrity(message, "conn")
    assert not ok and "message_id" in error


def test_a_fresh_message_is_unchanged(manager):
    ok, _error = manager.validate_message_integrity(
        _message("heartbeat", age=timedelta(seconds=5)), "conn"
    )
    assert ok
