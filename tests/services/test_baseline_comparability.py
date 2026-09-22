# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Golden-host drift must not fabricate divergence — Phase 21.1 S6.

THE DEFECT THIS FIXES, which was live
-------------------------------------
``compare_category`` had no notion of "this host cannot report this". A host
with zero rows for a category put EVERY reference row into ``missing``, so a
Windows box compared against a Linux one read as "missing every mount" rather
than "does not have mounts".

That is a fabricated divergence in a feature whose entire job is reporting
real ones — and it is the "not covered is not empty" confusion arriving in a
shipped surface.
"""

import json

from backend.services import config_mgmt_baseline as baseline


class FakeHost:
    def __init__(self, facts=None, advertised=True):
        report = {"schema_version": 1, "commands": ["get_system_info"]}
        if advertised:
            report["facts"] = facts
        self.agent_capabilities = json.dumps(report)
        self.fqdn = "host.example"


def linux_host():
    return FakeHost(
        {
            "contract_version": 1,
            "served": {
                "users": "native",
                "groups": "native",
                "mounts": "native",
                "interface_addresses": "native",
                "certificates": "native",
            },
            "unsupported": {},
            "not_applicable": {},
        }
    )


def windows_host():
    return FakeHost(
        {
            "contract_version": 1,
            "served": {"users": "native", "groups": "native"},
            "unsupported": {},
            # Windows has no mounts table in the contract.
            "not_applicable": {"mounts": "wrong_platform"},
        }
    )


class TestNotComparable:
    def test_a_category_the_target_cannot_report_is_not_drift(self):
        """THE regression. Windows does not have mounts; it is not missing
        every mount the Linux reference has."""
        blocked = baseline.comparability(linux_host(), windows_host(), "storage")
        assert blocked is not None
        assert blocked["comparable"] is False
        assert blocked["not_comparable"]["side"] == "target"
        assert blocked["not_comparable"]["reason"] == "wrong_platform"

    def test_a_blocked_category_contributes_no_differences(self):
        blocked = baseline.comparability(linux_host(), windows_host(), "storage")
        assert blocked["counts"]["missing"] == 0
        assert blocked["missing"] == []

    def test_it_is_shaped_like_a_real_comparison(self):
        """Same keys, so callers and the UI read ONE shape; `comparable` is
        the discriminator. An empty comparison would be indistinguishable
        from 'these hosts agree', which is the opposite of true."""
        blocked = baseline.comparability(linux_host(), windows_host(), "storage")
        real = {"missing", "extra", "different", "counts", "truncated", "comparable"}
        assert real <= set(blocked)

    def test_a_category_both_hosts_serve_compares_normally(self):
        assert baseline.comparability(linux_host(), windows_host(), "users") is None

    def test_the_target_is_blamed_first(self):
        """It is the host the operator is trying to fix, so 'your host cannot
        report this' is the more useful answer when neither can."""
        blocked = baseline.comparability(windows_host(), windows_host(), "storage")
        assert blocked["not_comparable"]["side"] == "target"

    def test_the_reference_can_also_block(self):
        blocked = baseline.comparability(windows_host(), linux_host(), "storage")
        assert blocked["not_comparable"]["side"] == "reference"


class TestUnknownHostsStillCompare:
    def test_a_pre_21_1_agent_compares_exactly_as_before(self):
        """Every host is pre-21.1 until upgraded. Reading unknown as 'not
        covered' would switch drift comparison off for the whole estate.

        Scoped to the categories that EXISTED before 21.1: that is what
        "exactly as before" means, and it is the property being protected.
        Categories added later have no prior behavior to preserve -- see
        TestCategoriesAddedAfterS1.
        """
        legacy = FakeHost(advertised=False)
        legacy_categories = [
            c for c in baseline.CATEGORIES if c not in baseline._SERVES_REQUIRED
        ]
        assert legacy_categories, "the legacy set must not be empty"
        for category in legacy_categories:
            assert baseline.comparability(legacy, legacy, category) is None


class TestCategoriesAddedAfterS1:
    """The rule inverts for a category that did not exist before the substrate.

    "Unknown means proceed as before" protects consumers with a BEFORE. A new
    category has none: letting unknown through means comparing zero rows
    against zero rows and reporting the hosts identical -- a clean verdict from
    a comparison that never ran.
    """

    def test_files_refuses_a_pre_21_1_agent(self):
        legacy = FakeHost(advertised=False)
        blocked = baseline.comparability(legacy, legacy, "files")
        assert blocked is not None
        assert blocked["comparable"] is False
        assert blocked["not_comparable"]["reason"] == "unknown"

    def test_files_refuses_an_agent_too_old_for_the_table(self):
        """Advertised, but on a contract that predates sysmanage_file_state."""
        old = FakeHost(
            {
                "contract_version": 1,
                "served": {"users": "native"},
                "unsupported": {},
                "not_applicable": {},
            }
        )
        assert baseline.comparability(old, old, "files") is not None

    def test_files_compares_between_two_current_agents(self):
        current = FakeHost(
            {
                "contract_version": 2,
                "served": {"sysmanage_file_state": "native"},
                "unsupported": {},
                "not_applicable": {},
            }
        )
        assert baseline.comparability(current, current, "files") is None


class TestCategoriesWithoutAFactTable:
    def test_they_always_compare(self):
        """Repositories and firewall have no fact-table counterpart; they
        must behave exactly as they did before this slice."""
        for category in ("repositories", "firewall", "packages"):
            assert (
                baseline.comparability(linux_host(), windows_host(), category) is None
            )
