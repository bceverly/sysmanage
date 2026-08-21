# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for agent capability ingest + the dispatch gate — ROADMAP Phase 19.

The behaviour these pin down is mostly about the THREE-VALUED state, because
collapsing it to two is the failure mode that would hurt real fleets:

    advertised-and-supported / advertised-and-NOT-supported / UNKNOWN

"Unknown" is every agent that has not upgraded yet.  Treating it as limited
lights up the whole fleet with false badges; treating it as unsupported stops
dispatching to hosts that work perfectly.  Both are worse than the problem this
feature solves, so unknown is never flagged and never gated.
"""

import json

import pytest

from backend.services.agent_capability_service import (
    MAX_SUPPORTED_SCHEMA_VERSION,
    UnsupportedCapabilityError,
    apply_capability_report,
    assert_host_supports,
    capability_update_values,
    get_capability_report,
    host_supports,
    normalize_report,
)


class _Host:
    """Stand-in for the ORM row — the service only touches these attributes."""

    def __init__(self, fqdn="host.example.com"):
        self.fqdn = fqdn
        self.agent_capabilities = None
        self.agent_capabilities_limited = False
        self.agent_capabilities_updated_at = None


def _report(commands, unavailable=None, partial=None, version=None):
    return {
        "schema_version": version or MAX_SUPPORTED_SCHEMA_VERSION,
        "capabilities": ["packages"],
        "commands": list(commands),
        "unavailable": unavailable or {},
        "partial": partial or {},
    }


# --------------------------------------------------------------- normalization


def test_a_report_from_a_newer_schema_is_rejected_whole():
    """Not half-read.  A partially understood capability set is
    indistinguishable from a limited agent, and would silently gate commands
    the host can actually run."""
    assert (
        normalize_report(_report(["x"], version=MAX_SUPPORTED_SCHEMA_VERSION + 1))
        is None
    )


def test_unknown_keys_from_a_newer_agent_are_dropped_not_fatal():
    """Forward compatibility: a newer agent must be able to add fields without
    a server change.  Same contract federation uses for site metadata."""
    report = _report(["install_package"])
    report["some_future_field"] = {"anything": True}
    normalized = normalize_report(report)
    assert normalized is not None
    assert "some_future_field" not in normalized


def test_a_report_with_no_commands_is_rejected():
    """Not a limited agent — a broken report.  An agent that can run nothing
    could not have sent it, and storing it would gate every command."""
    assert normalize_report(_report([])) is None


@pytest.mark.parametrize("bad", [None, "string", 42, [], {"schema_version": "1"}])
def test_malformed_reports_are_rejected(bad):
    assert normalize_report(bad) is None


# -------------------------------------------------------------------- ingestion


def test_a_full_agent_is_not_limited():
    host = _Host()
    assert apply_capability_report(host, _report(["install_package"])) is True
    assert host.agent_capabilities_limited is False
    assert host.agent_capabilities_updated_at is not None


def test_an_agent_missing_a_group_is_limited():
    host = _Host()
    apply_capability_report(
        host, _report(["install_package"], unavailable={"virtualization": "no_handler"})
    )
    assert host.agent_capabilities_limited is True


def test_partial_support_also_counts_as_limited():
    """A build missing some of a group's commands is not a full agent."""
    host = _Host()
    apply_capability_report(
        host,
        _report(["install_package"], partial={"virtualization": ["initialize_kvm"]}),
    )
    assert host.agent_capabilities_limited is True


def test_a_bad_report_does_not_erase_what_we_already_knew():
    """Flipping a known host back to unknown would silently un-gate it."""
    host = _Host()
    apply_capability_report(host, _report(["install_package"]))
    before = host.agent_capabilities
    assert apply_capability_report(host, {"garbage": True}) is False
    assert host.agent_capabilities == before


def test_stored_form_is_stable():
    """Sorted keys so an unchanged advertisement does not look like a change."""
    host = _Host()
    apply_capability_report(host, _report(["b_cmd", "a_cmd"]))
    stored = json.loads(host.agent_capabilities)
    assert stored["commands"] == ["a_cmd", "b_cmd"]
    assert host.agent_capabilities == json.dumps(stored, sort_keys=True)


# ------------------------------------------------------------------- the gate


def test_supported_command_is_allowed():
    host = _Host()
    apply_capability_report(host, _report(["install_package"]))
    assert host_supports(host, "install_package") is True
    assert_host_supports(host, "install_package")  # must not raise


def test_unsupported_command_is_refused_with_the_host_named():
    # The fqdn here is deliberately NOT domain-shaped.  Asserting
    # `"trimmed.example.com" in str(...)` is the exact shape CodeQL flags as
    # incomplete URL substring sanitization (py/incomplete-url-substring-
    # sanitization) — harmless in a test, but a real finding in the queue is a
    # finding nobody reads.  The structured attribute is the better assertion
    # anyway: it pins the contract instead of the phrasing.
    host = _Host("trimmed-host-01")
    apply_capability_report(host, _report(["install_package"]))
    assert host_supports(host, "initialize_kvm") is False
    with pytest.raises(UnsupportedCapabilityError) as excinfo:
        assert_host_supports(host, "initialize_kvm")
    assert excinfo.value.command_type == "initialize_kvm"
    assert excinfo.value.hostname == "trimmed-host-01"
    # The message must still name the host — that is the whole point of the
    # error — but check it via the attribute the message is built from.
    assert excinfo.value.hostname in str(excinfo.value)


def test_an_unknown_host_is_never_gated():
    """The important one.  Every agent that has not upgraded reports nothing,
    and refusing their commands would break a working fleet."""
    host = _Host()
    assert host.agent_capabilities is None
    assert host_supports(host, "initialize_kvm") is None
    assert_host_supports(host, "initialize_kvm")  # must not raise


def test_a_message_with_no_command_type_is_not_gated():
    """Not every queued message is a routed command."""
    host = _Host()
    apply_capability_report(host, _report(["install_package"]))
    assert_host_supports(host, None)


def test_corrupt_stored_json_reads_as_unknown_not_unsupported():
    """A storage problem must not start refusing commands."""
    host = _Host()
    host.agent_capabilities = "{not json"
    assert get_capability_report(host) is None
    assert host_supports(host, "install_package") is None
    assert_host_supports(host, "install_package")  # must not raise


# ------------------------------------------------- the UPDATE-payload shape


def test_update_values_carry_the_same_decision_as_apply():
    """The dict and object forms must agree.  They are used by different call
    sites (SYSTEM_INFO builds an UPDATE payload; host creation mutates an ORM
    object), and deriving 'limited' twice is how the two would drift."""
    report = _report(["install_package"], unavailable={"virtualization": "no_handler"})
    values = capability_update_values(report)
    host = _Host()
    apply_capability_report(host, report)
    assert values["agent_capabilities"] == host.agent_capabilities
    assert (
        values["agent_capabilities_limited"] == host.agent_capabilities_limited is True
    )


def test_update_values_are_empty_for_an_unusable_report():
    """Empty means callers can update() unconditionally without erasing a
    previous advertisement — the SYSTEM_INFO handler relies on that."""
    assert capability_update_values(None) == {}
    assert capability_update_values({"garbage": True}) == {}
    assert capability_update_values(_report([])) == {}


def test_update_values_name_only_real_host_columns():
    """A typo here would silently do nothing on an UPDATE, or blow up the
    handler — neither is visible from the service's own tests."""
    from backend.persistence.models.core import Host

    for column in capability_update_values(_report(["install_package"])):
        assert hasattr(Host, column), f"Host has no column {column}"


# ----------------------------------------------------- OS applicability (P19)


def test_not_applicable_is_stored_but_never_makes_a_host_limited():
    """A Linux host is not degraded for lacking bhyve.

    The agent excludes OS-inapplicable groups from unavailable/partial and
    reports them separately; the limited rule must stay a TWO-term rule or the
    exclusion is undone here.  This is the server half of the fix that stopped
    every Linux host reading as partially-capable at virtualization.
    """
    report = _report(["install_package"])
    report["not_applicable"] = {"ubuntu_pro": "wrong_platform"}

    normalized = normalize_report(report)
    assert normalized["not_applicable"] == {"ubuntu_pro": "wrong_platform"}

    values = capability_update_values(report)
    assert values["agent_capabilities_limited"] is False


def test_not_applicable_does_not_mask_a_real_gap():
    """Applicability must not become a blanket excuse: a genuine
    unavailable/partial entry still flags the host."""
    report = _report(["install_package"], unavailable={"packages": "missing_tool"})
    report["not_applicable"] = {"ubuntu_pro": "wrong_platform"}
    assert capability_update_values(report)["agent_capabilities_limited"] is True


def test_a_report_without_not_applicable_still_normalizes():
    """Agents older than Phase 19 never send the key."""
    normalized = normalize_report(_report(["install_package"]))
    assert normalized["not_applicable"] == {}
