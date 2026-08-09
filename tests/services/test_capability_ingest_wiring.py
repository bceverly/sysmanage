# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SYSTEM_INFO handler must actually INGEST the capability advertisement.

Why this file exists separately from the service tests: every piece of Phase 19
was implemented and unit-tested — the agent built the report and sent it, the
service normalized it, the migration added the columns, and the dispatch gate
called host_supports() — and the feature was still completely inert, because
nothing connected the payload to the service.  The column stayed NULL, so
host_supports() answered "unknown" for every host and the gate never fired.

Green service tests could not have caught that.  These pin the WIRING.
"""

from backend.api.message_handlers_core import _build_system_info_update_values
from backend.services.agent_capability_service import (
    MAX_SUPPORTED_SCHEMA_VERSION,
    get_capability_report,
)


class _Conn:
    is_mock_connection = True


class _Host:
    approval_status = "approved"


def _report(commands, unavailable=None):
    return {
        "schema_version": MAX_SUPPORTED_SCHEMA_VERSION,
        "capabilities": ["packages"],
        "commands": list(commands),
        "unavailable": unavailable or {},
        "partial": {},
    }


def _values(message_data):
    values, _ = _build_system_info_update_values(
        message_data, _Conn(), _Host(), "Linux"
    )
    return values


def test_system_info_ingests_the_advertisement():
    """The whole point: a SYSTEM_INFO carrying agent_capabilities must land in
    the column.  This is the connection that was missing."""
    values = _values({"agent_capabilities": _report(["install_package"])})
    assert "agent_capabilities" in values
    assert values["agent_capabilities_limited"] is False
    assert values["agent_capabilities_updated_at"] is not None


def test_a_limited_agent_is_flagged_through_the_handler():
    values = _values(
        {
            "agent_capabilities": _report(
                ["install_package"], unavailable={"virtualization": "no_handler"}
            )
        }
    )
    assert values["agent_capabilities_limited"] is True


def test_the_stored_form_round_trips_back_out():
    """What the handler writes must be readable by the gate — otherwise the
    column is populated and host_supports() still answers 'unknown'."""
    values = _values({"agent_capabilities": _report(["install_package", "reboot"])})

    class _Stored:
        agent_capabilities = values["agent_capabilities"]

    report = get_capability_report(_Stored())
    assert report is not None
    assert report["commands"] == ["install_package", "reboot"]


def test_a_message_without_capabilities_touches_no_capability_column():
    """Older agents send no advertisement.  The handler must not write NULLs
    over an existing one, nor invent an empty set that would read as limited."""
    values = _values({"agent_version": "1.2.3"})
    assert not [k for k in values if k.startswith("agent_capabilities")]


def test_an_unusable_advertisement_touches_no_capability_column():
    """A malformed report is not evidence the host lost capabilities."""
    values = _values({"agent_capabilities": {"garbage": True}})
    assert not [k for k in values if k.startswith("agent_capabilities")]


# --------------------------------------------------- the API-shape conversion


def test_limited_flag_is_three_valued():
    """The API must not present an agent that never advertised as 'full'.

    `bool(host.agent_capabilities_limited)` reads NULL as False, which is how a
    fleet mid-rollout would appear fully capable. Written and caught during
    Phase 19; pinned here so it cannot come back through any of the three
    serializers that now share this one function.
    """
    from backend.services.agent_capability_service import limited_flag

    class _H:
        agent_capabilities = None
        agent_capabilities_limited = False

    never = _H()
    assert limited_flag(never) is None

    full = _H()
    full.agent_capabilities = '{"commands": ["x"]}'
    assert limited_flag(full) is False

    lim = _H()
    lim.agent_capabilities = '{"commands": ["x"]}'
    lim.agent_capabilities_limited = True
    assert limited_flag(lim) is True


def test_limited_flag_ignores_a_stale_true_with_no_report():
    """Defence in depth: if the boolean column were somehow set while the JSON
    is absent, 'unknown' still wins — we cannot describe what was never sent."""
    from backend.services.agent_capability_service import limited_flag

    class _H:
        agent_capabilities = None
        agent_capabilities_limited = True

    assert limited_flag(_H()) is None
