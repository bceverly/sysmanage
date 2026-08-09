# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The dispatch gate must be WIRED, not merely implemented — ROADMAP Phase 19.

`assert_host_supports()` is unit-tested in test_agent_capability_service.py, but
that proves only that the function works. The feature spent its first day fully
implemented and completely inert because nothing CALLED the ingest path; the
gate is the same shape of risk. If the check in `QueueOperations.enqueue_message`
is ever moved, guarded differently, or dropped, every service test stays green
while unsupported commands sail through to hosts that cannot run them.

These call the real `enqueue_message` with a fake session.
"""

import json
from unittest.mock import MagicMock

import pytest

from backend.persistence.models import Host
from backend.services.agent_capability_service import UnsupportedCapabilityError
from backend.websocket.queue_operations import QueueOperations


class _Host:
    def __init__(self, commands=None):
        self.id = "host-1"
        self.fqdn = "gate-test-01"
        self.agent_capabilities_limited = bool(commands is not None)
        self.agent_capabilities_updated_at = None
        self.agent_capabilities = (
            json.dumps({"schema_version": 1, "commands": list(commands)})
            if commands is not None
            else None
        )


class _Sentinel(Exception):
    """Raised by the fake session the moment the code gets PAST the gate."""


def _db_returning(host):
    """A session that answers the Host lookup and nothing else.

    Model-aware on purpose: enqueue_message also runs a duplicate-command
    lookup, and a mock that returns the Host for EVERY query hands a Host to
    code expecting a MessageQueue row — which fails with an AttributeError that
    looks like a gate failure but is only the fake being too eager.
    """
    db = MagicMock()

    def _query(model, *_a, **_k):
        q = MagicMock()
        q.filter.return_value = q  # chained .filter(...).filter(...)
        q.order_by.return_value = q
        q.first.return_value = host if model is Host else None
        q.all.return_value = []
        return q

    db.query.side_effect = _query
    # Anything that reaches a write has cleared the gate — that is what we
    # want to observe, without standing up a real queue table.
    db.add.side_effect = _Sentinel()
    return db


def _enqueue(host, command_type):
    return QueueOperations().enqueue_message(
        message_type="command",
        message_data={"command_type": command_type},
        direction="outbound",
        host_id=host.id,
        db=_db_returning(host),
    )


def test_an_unsupported_command_is_refused_at_enqueue():
    """The point of the feature: fail before the message is written, so the
    operator gets an immediate answer instead of a command that sits pending
    and comes back 'Unknown command type' minutes later."""
    host = _Host(commands=["install_package"])
    with pytest.raises(UnsupportedCapabilityError) as excinfo:
        _enqueue(host, "initialize_kvm")
    assert excinfo.value.command_type == "initialize_kvm"
    assert excinfo.value.hostname == "gate-test-01"


def test_a_supported_command_passes_the_gate():
    """Reaching the write proves the gate allowed it through."""
    host = _Host(commands=["install_package"])
    with pytest.raises(_Sentinel):
        _enqueue(host, "install_package")


def test_a_host_that_never_advertised_is_not_gated():
    """The one that would break a live fleet. Every agent that has not upgraded
    reports nothing; refusing their commands is worse than the problem this
    feature solves."""
    host = _Host(commands=None)
    with pytest.raises(_Sentinel):
        _enqueue(host, "initialize_kvm")


def test_non_command_messages_are_never_gated():
    """Not every queued message is a routed command — data messages must flow
    regardless of what the agent advertises."""
    host = _Host(commands=["install_package"])
    with pytest.raises(_Sentinel):
        QueueOperations().enqueue_message(
            message_type="data",
            message_data={"command_type": "initialize_kvm"},
            direction="outbound",
            host_id=host.id,
            db=_db_returning(host),
        )


def test_inbound_messages_are_never_gated():
    """The gate is about what WE dispatch. An inbound message from the agent is
    evidence of what it did, not a request for it to do something."""
    host = _Host(commands=["install_package"])
    with pytest.raises(_Sentinel):
        QueueOperations().enqueue_message(
            message_type="command",
            message_data={"command_type": "initialize_kvm"},
            direction="inbound",
            host_id=host.id,
            db=_db_returning(host),
        )
