# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What a host can answer -- Phase 21.1 S6.

The reader every consumer shares. Its whole job is keeping four states apart
where a boolean would keep two, and the state that matters most is the one
that is easiest to get wrong: a host that has NOT ADVERTISED is not a host
that has said no.
"""

import json


from backend.services import host_facts


class FakeHost:
    def __init__(self, facts=None, advertised=True):
        report = {"schema_version": 1, "commands": ["get_system_info"]}
        if advertised:
            report["facts"] = facts
        self.agent_capabilities = json.dumps(report)


def host_with(served=None, unsupported=None, not_applicable=None, version=1):
    return FakeHost(
        {
            "contract_version": version,
            "served": served or {},
            "unsupported": unsupported or {},
            "not_applicable": not_applicable or {},
        }
    )


class TestFourStates:
    def test_a_served_table_names_its_provider(self):
        host = host_with(served={"users": "osquery"})
        assert host_facts.table_state(host, "users") == (host_facts.SERVED, "osquery")

    def test_not_applicable_carries_the_agents_own_reason(self):
        """'wrong_platform' and 'insufficient_privilege' send an operator to
        different places; a generic 'unavailable' sends them to neither."""
        host = host_with(not_applicable={"mounts": "wrong_platform"})
        assert host_facts.table_state(host, "mounts") == (
            host_facts.NOT_APPLICABLE,
            "wrong_platform",
        )

    def test_unsupported_is_distinct_from_not_applicable(self):
        """One is a fact about the platform, the other is fixable -- an
        unprivileged agent can be given privilege."""
        host = host_with(unsupported={"listening_ports": "insufficient_privilege"})
        assert host_facts.table_state(host, "listening_ports") == (
            host_facts.UNSUPPORTED,
            "insufficient_privilege",
        )


class TestUnknownIsNotDenial:
    """THE test. Every host in a fleet is pre-21.1 until it is upgraded."""

    def test_a_host_that_never_advertised_is_unknown(self):
        host = FakeHost(advertised=False)
        assert host_facts.table_state(host, "users")[0] == host_facts.UNKNOWN

    def test_unknown_hosts_remain_answerable(self):
        """A consumer that read unknown as 'not covered' would switch itself
        off for the whole estate the day this shipped -- while looking like it
        was working."""
        host = FakeHost(advertised=False)
        assert host_facts.answerable(host, "users") is True
        assert host_facts.explain(host, "users") is None

    def test_a_table_in_no_bucket_is_unknown_not_a_denial(self):
        """An agent speaking a contract this server does not know. Not an
        advertisement of absence."""
        host = host_with(served={"users": "native"})
        assert host_facts.table_state(host, "some_future_table")[0] == (
            host_facts.UNKNOWN
        )
        assert host_facts.answerable(host, "some_future_table") is True


class TestConsumerHelpers:
    def test_answerable_is_false_only_on_a_positive_denial(self):
        host = host_with(
            served={"users": "native"},
            not_applicable={"mounts": "wrong_platform"},
            unsupported={"processes": "insufficient_privilege"},
        )
        assert host_facts.answerable(host, "users") is True
        assert host_facts.answerable(host, "mounts") is False
        assert host_facts.answerable(host, "processes") is False

    def test_explain_is_shaped_for_attaching_to_a_result(self):
        host = host_with(not_applicable={"mounts": "wrong_platform"})
        assert host_facts.explain(host, "mounts") == {
            "table": "mounts",
            "state": host_facts.NOT_APPLICABLE,
            "reason": "wrong_platform",
        }

    def test_missing_tables_reports_only_the_unanswerable_ones(self):
        host = host_with(
            served={"users": "native"}, not_applicable={"mounts": "wrong_platform"}
        )
        missing = host_facts.missing_tables(host, ["users", "mounts", "groups"])
        assert set(missing) == {"mounts"}

    def test_the_contract_version_travels(self):
        """A fleet upgrades gradually; comparing across hosts can silently
        compare different contracts."""
        assert host_facts.contract_version(host_with(version=1)) == 1
        assert host_facts.contract_version(FakeHost(advertised=False)) is None


class TestServesIsStricterThanAnswerable:
    """Phase 21.1 S7 added a second predicate, and picking the wrong one is a
    live defect rather than a style choice.

    ``answerable`` lets UNKNOWN through so consumers that existed before 21.1
    keep working against agents that have not upgraded. ``serves`` refuses it,
    for consumers that are brand new and would otherwise compare nothing
    against nothing and report a clean result.
    """

    def test_served_satisfies_both(self):
        host = host_with(served={"sysmanage_file_state": "native"})
        assert host_facts.answerable(host, "sysmanage_file_state") is True
        assert host_facts.serves(host, "sysmanage_file_state") is True

    def test_unknown_is_answerable_but_not_served(self):
        """The whole reason the second predicate exists. An agent older than
        the table proceeds for legacy consumers and is refused by new ones."""
        host = host_with(served={"users": "native"})
        assert host_facts.answerable(host, "sysmanage_file_state") is True
        assert host_facts.serves(host, "sysmanage_file_state") is False

    def test_a_host_that_never_advertised_is_not_served(self):
        host = FakeHost(advertised=False)
        assert host_facts.answerable(host, "users") is True
        assert host_facts.serves(host, "users") is False

    def test_a_positive_denial_fails_both(self):
        host = host_with(unsupported={"listening_ports": "insufficient_privilege"})
        assert host_facts.answerable(host, "listening_ports") is False
        assert host_facts.serves(host, "listening_ports") is False

    def test_why_not_served_reports_unknown_where_explain_stays_silent(self):
        """``explain`` deliberately says nothing about UNKNOWN -- for the old
        consumers it is not a denial. For the new ones it is the commonest
        answer, so it needs a reason an operator can act on."""
        host = host_with(served={"users": "native"})
        assert host_facts.explain(host, "sysmanage_file_state") is None
        assert host_facts.why_not_served(host, "sysmanage_file_state") == {
            "table": "sysmanage_file_state",
            "state": host_facts.UNKNOWN,
            "reason": host_facts.UNKNOWN,
        }

    def test_why_not_served_is_silent_when_the_table_is_served(self):
        host = host_with(served={"sysmanage_file_state": "native"})
        assert host_facts.why_not_served(host, "sysmanage_file_state") is None
