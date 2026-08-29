# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Routing a command result back to the handler that wants it.

WHY THIS FILE EXISTS
--------------------
Every config-profile handler test called ``handle_config_profile_result``
DIRECTLY, so none of them exercised the decision of whether it gets called at
all. Against a real agent on 2026-08-28 it never did: agents do not echo
``command_type`` on a result, so every config-profile result was marked
completed and dropped -- no run row, no drift finding, no error anywhere.

The shape below is the shape a live agent actually sends. That is the whole
point of the file: a fixture invented from the handler's signature would have
had ``command_type`` in it and proved nothing.
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from backend.api import message_handlers as mh


def outbound_row(command_type="apply_config_profile", message_id=None):
    """An outbound queue row as the dispatcher writes it."""
    return SimpleNamespace(
        message_id=str(message_id or uuid.uuid4()),
        message_data=json.dumps(
            {
                "message_type": "command",
                "data": {"command_type": command_type, "parameters": {}},
            }
        ),
    )


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def query(self, _entity):
        return _Query(self._rows)


class TestCommandTypeOf:
    def test_reads_a_top_level_command_type(self):
        assert mh.command_type_of({"command_type": "x"}) == "x"

    def test_reads_a_nested_command_type(self):
        assert mh.command_type_of({"data": {"command_type": "y"}}) == "y"

    def test_a_real_agent_result_has_neither(self):
        # Verified against a live agent: this is what actually arrives.
        agent_result = {
            "command_id": str(uuid.uuid4()),
            "success": True,
            "result": {"changed": True, "tasks": [], "profile_id": "p1"},
        }
        assert mh.command_type_of(agent_result) is None


class TestCorrelationByCommandId:
    def test_recovers_the_type_from_the_command_we_sent(self):
        # The agent echoes command_id -- the outbound row's message_id -- so
        # the type is recoverable without upgrading every deployed agent.
        row = outbound_row()
        got = mh.command_type_from_queue(
            _Session([row]), {"command_id": row.message_id}
        )
        assert got == "apply_config_profile"

    def test_a_result_with_no_command_id_correlates_to_nothing(self):
        assert mh.command_type_from_queue(_Session([outbound_row()]), {}) is None

    def test_an_unknown_command_id_is_not_an_error(self):
        # The command may have been pruned. Dropping the correlation is fine;
        # failing the queue processor is not.
        assert mh.command_type_from_queue(_Session([]), {"command_id": "nope"}) is None

    def test_a_malformed_stored_command_is_tolerated(self):
        bad = SimpleNamespace(message_id="m1", message_data="{not json")
        assert mh.command_type_from_queue(_Session([bad]), {"command_id": "m1"}) is None

    def test_a_row_with_no_payload_is_tolerated(self):
        empty = SimpleNamespace(message_id="m1", message_data=None)
        assert (
            mh.command_type_from_queue(_Session([empty]), {"command_id": "m1"}) is None
        )

    def test_a_db_failure_does_not_propagate(self):
        class Exploding:
            def query(self, _entity):
                raise RuntimeError("db is down")

        assert mh.command_type_from_queue(Exploding(), {"command_id": "m1"}) is None

    def test_another_command_type_is_reported_as_itself(self):
        row = outbound_row(command_type="execute_script")
        got = mh.command_type_from_queue(
            _Session([row]), {"command_id": row.message_id}
        )
        assert got == "execute_script"
