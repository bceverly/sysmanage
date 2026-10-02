# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2 reconnect admission control.

Every SYSTEM_INFO (each agent connect) did a host upsert, full package
ingestion, an audit record and a logging-config push inline; after a server
restart, every agent at once.  Now: registrations are admitted at a steady
rate, the config is pushed only when the agent does not already run it, and
packages inside SYSTEM_INFO go through the queue.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.persistence.models import Host, MessageQueue
from backend.services import logging_config_service as svc
from backend.websocket.admission import MAX_WAIT_SECONDS, AdmissionGate

# The agent pins the same value (sysmanage-agent tests/test_logging_digest.py):
# if the two ever disagree, every reconnect pushes again.
SAMPLE = {"log_level": "INFO", "native_enabled": True, "native_target": "syslog"}
SAMPLE_DIGEST = "560e87ee45f64103171ff86cc6d4a4bfcb10087ddcb909f5ae6b30a0ba676791"


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# -- the admission gate ------------------------------------------------------------


def test_a_burst_goes_straight_through():
    gate = AdmissionGate(rate=10, burst=5, clock=_Clock())
    assert [gate.reserve() for _ in range(5)] == [0.0] * 5


def test_beyond_the_burst_slots_are_handed_out_at_the_rate():
    gate = AdmissionGate(rate=10, burst=5, clock=_Clock())
    for _ in range(5):
        gate.reserve()
    waits = [gate.reserve() for _ in range(20)]
    assert waits == sorted(waits)  # in order: nobody jumps the queue
    assert abs(waits[-1] - 2.0) < 1e-9  # 20 more at 10/s: the last waits 2 s
    assert gate.waited == 20


def test_once_the_queue_has_drained_the_burst_is_back():
    clock = _Clock()
    gate = AdmissionGate(rate=10, burst=5, clock=clock)
    for _ in range(25):
        gate.reserve()
    clock.now += 60
    assert gate.reserve() == 0.0


def test_no_reply_is_held_forever():
    gate = AdmissionGate(rate=0.1, burst=1, clock=_Clock())
    gate.reserve()
    assert max(gate.reserve() for _ in range(1000)) == MAX_WAIT_SECONDS


def test_bad_settings_fall_back_to_safe_values():
    gate = AdmissionGate(rate=0, burst=0, clock=_Clock())
    assert gate.rate == 0.1 and gate.burst == 1.0


# -- the logging push --------------------------------------------------------------


def test_the_server_digest_matches_the_agents():
    assert svc.config_digest(SAMPLE) == SAMPLE_DIGEST
    assert svc.config_digest({}) is None


def _approved_host():
    host = MagicMock()
    host.approval_status = "approved"
    host.id = uuid4()
    host.platform = "Linux"
    return host


def _push(agent_digest):
    with (
        patch.object(svc, "resolve_agent_logging", return_value=object()),
        patch.object(svc, "_agent_payload", return_value=SAMPLE),
        patch.object(svc, "_main_session", return_value=MagicMock()),
        patch.object(svc, "_enqueue_logging_update") as enqueue,
    ):
        pushed = svc.push_logging_to_host(MagicMock(), _approved_host(), agent_digest)
    return pushed, enqueue.called


def test_an_agent_already_running_the_config_is_not_pushed_again():
    assert _push(SAMPLE_DIGEST) == (False, False)


def test_a_changed_config_or_an_older_agent_is_pushed():
    assert _push("something-else") == (True, True)
    assert _push(None) == (True, True)  # agents before 22.2 report nothing


# -- packages inside SYSTEM_INFO ---------------------------------------------------


def test_system_info_packages_go_through_the_queue(session):
    from backend.api import message_handlers_core as core  # noqa: PLC0415

    host = Host(id=uuid4(), fqdn="pkgs.example.com", active=True,
                approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    with patch("backend.api.handlers.handle_software_update") as inline:
        core._queue_software_packages(  # pylint: disable=protected-access
            session, host, [{"package_name": "nginx", "version": "1.24"}]
        )
    inline.assert_not_called()
    row = session.query(MessageQueue).filter_by(host_id=host.id).one()
    assert row.message_type == "software_inventory_update"
    assert row.direction == "inbound"
