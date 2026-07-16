# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Unit tests for the recent-child-host-deletion tombstone module."""

import time
from unittest.mock import patch

import pytest

from backend.api import recent_host_deletions


@pytest.fixture(autouse=True)
def _reset_store():
    recent_host_deletions._reset_for_tests()
    yield
    recent_host_deletions._reset_for_tests()


def test_empty_store_returns_false():
    assert (
        recent_host_deletions.is_recent_child_host_deletion("a.b.c", "1.2.3.4") is False
    )


def test_record_then_match_by_fqdn_and_ip():
    recent_host_deletions.record_recent_child_host_deletion("vm.localhost", "10.0.0.1")
    assert (
        recent_host_deletions.is_recent_child_host_deletion("vm.localhost", "10.0.0.1")
        is True
    )


def test_match_is_case_insensitive_on_fqdn():
    recent_host_deletions.record_recent_child_host_deletion("VM.LocalHost", "10.0.0.1")
    assert (
        recent_host_deletions.is_recent_child_host_deletion("vm.localhost", "10.0.0.1")
        is True
    )


def test_fqdn_match_falls_back_when_ip_differs():
    recent_host_deletions.record_recent_child_host_deletion("vm.localhost", "10.0.0.1")
    assert (
        recent_host_deletions.is_recent_child_host_deletion("vm.localhost", "10.0.0.99")
        is True
    )


def test_different_fqdn_does_not_match():
    recent_host_deletions.record_recent_child_host_deletion("vm.localhost", "10.0.0.1")
    assert (
        recent_host_deletions.is_recent_child_host_deletion(
            "other.localhost", "10.0.0.1"
        )
        is False
    )


def test_empty_fqdn_inputs_are_noops():
    recent_host_deletions.record_recent_child_host_deletion("", "10.0.0.1")
    assert recent_host_deletions.is_recent_child_host_deletion("", "10.0.0.1") is False


def test_missing_ip_treated_as_empty_string():
    recent_host_deletions.record_recent_child_host_deletion("vm.localhost", None)
    # Either exact-match-with-None or fqdn-fallback should hit.
    assert (
        recent_host_deletions.is_recent_child_host_deletion("vm.localhost", None)
        is True
    )
    assert (
        recent_host_deletions.is_recent_child_host_deletion("vm.localhost", "1.2.3.4")
        is True
    )


def test_expires_after_ttl():
    # Pin time so we can advance past TTL deterministically.
    base = 1_000_000.0
    with patch.object(time, "monotonic", return_value=base):
        recent_host_deletions.record_recent_child_host_deletion(
            "vm.localhost", "10.0.0.1"
        )
        assert recent_host_deletions.is_recent_child_host_deletion(
            "vm.localhost", "10.0.0.1"
        )
    with patch.object(
        time, "monotonic", return_value=base + recent_host_deletions.TTL_SECONDS + 1
    ):
        assert (
            recent_host_deletions.is_recent_child_host_deletion(
                "vm.localhost", "10.0.0.1"
            )
            is False
        )


def test_prune_removes_expired_entries():
    base = 1_000_000.0
    with patch.object(time, "monotonic", return_value=base):
        recent_host_deletions.record_recent_child_host_deletion(
            "stale.localhost", "10.0.0.1"
        )
    with patch.object(
        time, "monotonic", return_value=base + recent_host_deletions.TTL_SECONDS + 1
    ):
        # A new record at the later time prunes the stale entry.
        recent_host_deletions.record_recent_child_host_deletion(
            "fresh.localhost", "10.0.0.2"
        )
        assert (
            "stale.localhost",
            "10.0.0.1",
        ) not in recent_host_deletions._TOMBSTONES
        assert (
            "fresh.localhost",
            "10.0.0.2",
        ) in recent_host_deletions._TOMBSTONES
