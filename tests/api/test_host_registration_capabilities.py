# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The registration payload the AGENT actually sends must validate.

``HostRegistration`` sets ``extra = "forbid"``.  Phase 19 taught the agent to
advertise ``agent_capabilities`` in its registration body, but the field was
only ever added to the SYSTEM_INFO ingest path -- so the server rejected every
capability-aware agent with

    422 {"type": "extra_forbidden", "loc": ["body", "agent_capabilities"]}

An agent and a server built from the SAME commit could not talk to each other,
and nothing caught it: the two live in different repositories, every server
test constructs its own payload by hand, and no test in either repo asserts
that what one sends is what the other accepts.

These tests pin the contract at the model, which is where it broke.  The
payload below is copied from a real agent 3.5.1.9 registration attempt.
"""

import pytest
from pydantic import ValidationError

from backend.api.host import HostRegistration

# Trimmed from an actual agent log line, keeping the shape (schema_version,
# capabilities, commands, unavailable, partial) rather than the full lists.
AGENT_CAPABILITIES = {
    "schema_version": 1,
    "capabilities": ["packages", "services", "shell"],
    "commands": ["install_package", "restart_service", "execute_shell"],
    "unavailable": {},
    "partial": {},
}

BASE_PAYLOAD = {
    "message_type": "registration_request",
    "message_id": "2c0f3ed8-4f91-47b9-b166-999d03bad453",
    "timestamp": "2026-08-11T13:59:18.101229+00:00",
    "active": True,
    "fqdn": "freebsd.theeverlys.com",
    "hostname": "freebsd.theeverlys.com",
    "ipv4": "192.168.4.212",
    "ipv6": None,
    "script_execution_enabled": True,
    "is_privileged": False,
    "enabled_shells": ["bash", "sh"],
    "agent_version": "3.5.1.9",
}


def test_registration_accepts_agent_capabilities():
    """The exact shape a capability-aware agent sends must validate."""
    model = HostRegistration(**BASE_PAYLOAD, agent_capabilities=AGENT_CAPABILITIES)
    assert model.agent_capabilities == AGENT_CAPABILITIES


def test_registration_still_valid_without_capabilities():
    """Older agents send no capabilities at all; they must keep registering."""
    model = HostRegistration(**BASE_PAYLOAD)
    assert model.agent_capabilities is None


def test_registration_still_forbids_genuinely_unknown_fields():
    """extra="forbid" is deliberate -- widening it would defeat the point.

    The fix was to DECLARE the field, not to stop rejecting unknown ones.
    """
    with pytest.raises(ValidationError) as excinfo:
        HostRegistration(**BASE_PAYLOAD, something_nobody_declared=1)
    assert "extra_forbidden" in str(excinfo.value)


def test_capability_report_survives_a_round_trip_through_the_service():
    """What registration stores is what the read path returns."""
    from backend.services.agent_capability_service import (
        apply_capability_report,
        get_capability_report,
    )

    class _Host:  # minimal stand-in; the service only touches attributes
        agent_capabilities = None
        agent_capabilities_schema = None
        agent_capabilities_limited = None
        agent_capabilities_updated_at = None

    host = _Host()
    assert apply_capability_report(host, AGENT_CAPABILITIES) is True
    report = get_capability_report(host)
    assert report is not None
    assert "packages" in report["capabilities"]
    assert "install_package" in report["commands"]


def test_absent_capabilities_do_not_erase_a_previous_advertisement():
    """A re-registration without capabilities must not un-gate the host.

    ``_refresh_existing_host`` calls the same helper on every re-registration,
    so a payload from an older agent has to leave the stored set alone rather
    than flipping the host back to "unknown".
    """
    from backend.services.agent_capability_service import (
        apply_capability_report,
        get_capability_report,
    )

    class _Host:
        agent_capabilities = None
        agent_capabilities_schema = None
        agent_capabilities_limited = None
        agent_capabilities_updated_at = None

    host = _Host()
    apply_capability_report(host, AGENT_CAPABILITIES)
    assert apply_capability_report(host, None) is False
    assert get_capability_report(host) is not None
